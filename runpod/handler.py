"""
RunPod serverless handler — GutenbergKG query service.

Serves semantic search over the Project Gutenberg literary corpus mounted
from a RunPod Network Volume.  Uses the same direct LanceDB cosine-search
path as docker/handler.py — no KGRAG orchestrator hop-expansion, which
avoids the flat-plateau scoring bug and hangs on large corpora.

Volume layout (populated by runpod/push_indices.sh)
-----------------------------------------------------
  /workspace/   (KG_VOLUME)
  └── gutenberg_kg/
      ├── .dockg/
      │   ├── graph.sqlite
      │   ├── lancedb/
      │   └── catalog.json
      └── diaries/
          └── <diary-name>/.diarykg/

Environment variables
---------------------
KG_VOLUME          Path where the Network Volume is mounted.  Default: /workspace
EMBED_MODEL        Sentence-transformer model ID.  Default: BAAI/bge-small-en-v1.5
HANDLER_SECRET     Optional shared secret.  Requests must include {"secret": "<value>"}.
VLLM_ENDPOINT_URL  Optional OpenAI-compatible endpoint for synthesis.
VLLM_API_KEY       Bearer token for the synthesis endpoint.
RUNPOD_API_KEY     Fallback token if VLLM_API_KEY is unset.
VLLM_MODEL         Default synthesis model.  Default: Qwen/Qwen3-8B-Instruct
SYNTH_MAX_K        Max passages fed to synthesis.  Default: 12

Request schema
--------------
{
  "query":          str   — natural-language query (required)
  "secret":         str   — required when HANDLER_SECRET is set
  "corpus":         str   — "all" | "gutenberg" | "diary" | <genre>  (default: "all")
  "k":              int   — top-k hits  (default: 8)
  "min_score":      float — drop hits below this score  (default: 0.0)
  "semantic_floor": float — discard KG if best hit is below this  (default: 0.0)
  "synthesize":     bool  — call vLLM endpoint for a generated answer  (default: false)
  "model":          str   — override VLLM_MODEL for this request
  "op":             str   — "models" returns available synthesis models
}

Note: image generation is not available in this worker (local FLUX only).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from kg_utils.retrieval import attach_content_by_sqlite

import runpod
from gutenberg_kg.diary_meta import DIARY_META as _DIARY_META
from gutenberg_kg.diary_meta import diary_slug as _diary_slug

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VOLUME = Path(os.environ.get("KG_VOLUME", "/workspace"))
GUTENBERG_ROOT = VOLUME / "gutenberg_kg"
REGISTRY_PATH = Path("/tmp/gutenkg_worker/registry.sqlite")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
HANDLER_SECRET = os.environ.get("HANDLER_SECRET", "")
VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT_URL", "")
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "") or os.environ.get("RUNPOD_API_KEY", "")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-8B-Instruct")
SYNTH_MAX_K = int(os.environ.get("SYNTH_MAX_K", "12"))

_DOCKG_SQLITE = GUTENBERG_ROOT / ".dockg" / "graph.sqlite"
_DOCKG_LANCEDB = GUTENBERG_ROOT / ".dockg" / "lancedb"
_DOCKG_VECTORS = GUTENBERG_ROOT / ".dockg" / "vectors.sqlite"
_CATALOG_PATH = GUTENBERG_ROOT / ".dockg" / "catalog.json"
# Metadata columns the sqlite-vec store carries (matches doc_kg's index).
_VEC_META = ("kind", "name", "title", "file_path")
_DIARIES_ROOT = GUTENBERG_ROOT / "diaries"

_ALL_GENRES = {
    "american-literature",
    "ancient-classical",
    "audel-electric",
    "biography",
    "drama",
    "english-literature",
    "french-literature",
    "german-literature",
    "letters",
    "natural-history",
    "philosophy",
    "russian-literature",
    "sacred-texts",
    "science-fiction",
    "shakespeare",
    "spanish",
    "travel",
    "world-literature",
}

_KG_SQLITE: dict[str, Path] = {}
_DOCKG_TABLE = None
_DIARY_TABLES: dict = {}
_catalog: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def _source_file_for(diary_dir: Path) -> str:
    config = diary_dir / ".diarykg" / "config.json"
    if config.exists():
        return json.loads(config.read_text()).get("source_file", "")
    return ""


def _bootstrap_registry():
    """Register the consolidated DocKG and all diary KGs into a fresh in-memory KGRAG registry.

    :return: The populated :class:`KGRegistry`.
    """
    from kg_rag.corpus_registry import CorpusRegistry
    from kg_rag.primitives import CorpusEntry, KGEntry, KGKind
    from kg_rag.registry import KGRegistry

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    reg = KGRegistry(db_path=REGISTRY_PATH)
    corp_reg = CorpusRegistry(db_path=REGISTRY_PATH)

    # --- DocKG (consolidated prose + verse) ---
    if not _DOCKG_SQLITE.exists():
        print(f"[bootstrap] WARNING: DocKG not found at {_DOCKG_SQLITE}")
        print("[bootstrap]   Run 'make build-corpus' then push_indices.sh.")
    else:
        entry = KGEntry(
            id=str(uuid.uuid4()),
            name="gutenberg",
            kind=KGKind.GUTENBERG,
            repo_path=GUTENBERG_ROOT,
            venv_path=Path("/usr"),
            sqlite_path=_DOCKG_SQLITE,
            lancedb_path=_DOCKG_LANCEDB,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        reg.register(entry)
        _KG_SQLITE["gutenberg"] = _DOCKG_SQLITE
        print(f"[bootstrap] registered gutenberg dockg ({_DOCKG_SQLITE})")

    # --- DiaryKG indices ---
    corp_reg.create(CorpusEntry(name="diaries", description="Project Gutenberg — diary corpora"))
    n_diaries = 0
    if _DIARIES_ROOT.exists():
        for diary_dir in sorted(_DIARIES_ROOT.iterdir()):
            if not diary_dir.is_dir() or diary_dir.name.startswith("."):
                continue
            diarykg_dir = diary_dir / ".diarykg"
            sqlite = diarykg_dir / "graph.sqlite"
            lancedb = diarykg_dir / "lancedb"
            if not sqlite.exists():
                print(f"[bootstrap] skipping {diary_dir.name} — no .diarykg/graph.sqlite")
                continue
            slug = _diary_slug(diary_dir.name)
            entry = KGEntry(
                id=str(uuid.uuid4()),
                name=slug,
                kind=KGKind.DIARY,
                repo_path=diary_dir,
                venv_path=Path("/usr"),
                sqlite_path=sqlite,
                lancedb_path=lancedb,
                metadata={"source_file": _source_file_for(diary_dir)},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            reg.register(entry)
            corp_reg.add_kg("diaries", entry.id)
            _KG_SQLITE[slug] = sqlite
            # Open the diary's vector store (sqlite-vec preferred, LanceDB fallback).
            try:
                src = _open_vector_source(diarykg_dir, label=f"diary {slug}")
                if src is not None:
                    _DIARY_TABLES[slug] = src
            except Exception as exc:  # noqa: BLE001
                print(f"[bootstrap] WARNING: could not open diary store {slug}: {exc}")
            n_diaries += 1
            print(f"[bootstrap] registered diary: {slug}")
    else:
        print("[bootstrap] no diaries/ directory found")
    print(f"[bootstrap] diaries corpus: {n_diaries} KG(s)")

    return reg


def _open_vector_source(dockg_dir, *, label: str):
    """Open a vector source for a ``.dockg`` dir — sqlite-vec if present, else LanceDB.

    Prefers the exact ``vectors.sqlite`` store; falls back to the LanceDB
    ``dockg_nodes`` table for un-converted corpora (transition safety).

    :param dockg_dir: The ``.dockg``/``.diarykg`` dir holding the vector store.
    :param label: Human label for startup logging.
    :returns: A ``SqliteVecBackend`` or an open LanceDB table, or ``None``.
    """
    vectors = dockg_dir / "vectors.sqlite"
    lancedb_dir = dockg_dir / "lancedb"
    if vectors.exists():
        from kg_utils.vector_backend import SqliteVecBackend

        be = SqliteVecBackend(vectors, dim=384, meta_columns=_VEC_META, check_same_thread=False)
        be.open(wipe=False)
        print(f"[startup] {label}: sqlite-vec store ({be.count()} vectors)")
        return be
    if lancedb_dir.exists():
        import lancedb

        db = lancedb.connect(str(lancedb_dir))
        names = list(db.table_names())
        table = "dockg_nodes" if "dockg_nodes" in names else (names[0] if names else None)
        if table is None:
            print(f"[startup] WARNING: no lancedb table in {lancedb_dir}")
            return None
        tbl = db.open_table(table)
        print(f"[startup] {label}: LanceDB table {table} ({tbl.count_rows()} rows)")
        return tbl
    print(f"[startup] WARNING: no vector store for {label} in {dockg_dir}")
    return None


def _open_dockg_table() -> None:
    """Open the consolidated DocKG vector store (sqlite-vec preferred)."""
    global _DOCKG_TABLE
    _DOCKG_TABLE = _open_vector_source(GUTENBERG_ROOT / ".dockg", label="DocKG")


def _load_catalog() -> None:
    """Load ``catalog.json`` (book genre/title/author metadata) into the module-level ``_catalog`` dict."""
    if _CATALOG_PATH.exists():
        with open(_CATALOG_PATH, encoding="utf-8") as f:
            _catalog.update(json.load(f))
        print(f"[startup] loaded catalog: {len(_catalog)} books")
    else:
        print(f"[startup] WARNING: catalog.json not found at {_CATALOG_PATH}")


def _make_embedder():
    """Load the configured sentence-transformer embedder and warm it up with a dummy embed call.

    :return: The ready-to-use embedder instance.
    """
    from kg_rag._embedders import SentenceTransformerEmbedder

    print(f"[startup] loading embedder: {EMBED_MODEL}")
    emb = SentenceTransformerEmbedder(EMBED_MODEL)
    emb.embed_texts(["warm up"])
    print("[startup] embedder ready")
    return emb


print("[startup] bootstrapping registry ...")
_registry = _bootstrap_registry()

print("[startup] loading catalog ...")
_load_catalog()

print("[startup] loading embedder ...")
_embedder = _make_embedder()

print("[startup] opening DocKG vector table ...")
_open_dockg_table()

print("[startup] ready")


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def _attach_content(hits: list[dict]) -> None:
    """Fill in each hit's ``content`` field by looking up its node in the per-KG sqlite DBs.

    :param hits: Hit dicts to update in place; each must have ``kg_name`` and ``node_id``.
    """
    attach_content_by_sqlite(hits, _KG_SQLITE)


def _table_search(table, qvec, where: str, k: int) -> list[dict]:
    """Run a cosine kNN search with a pre-filter; returns rows with ``_distance``.

    Dispatches on the store type. The sqlite-vec backend is exact (recall 1.0)
    and its ``where`` compiles to a true rowid-subquery prefilter. The LanceDB
    path keeps the ``nprobes(128)`` stopgap that lifts IvfFlat recall@10 from
    ~0.825 to ~0.99 (benchmarks/SQLITE_VEC_RESULTS.md).
    """
    from kg_utils.vector_backend import SqliteVecBackend

    if isinstance(table, SqliteVecBackend):
        return table.search(qvec, k, where=where)
    return (
        table.search(qvec)
        .metric("cosine")
        .where(where, prefilter=True)
        .nprobes(128)
        .limit(k)
        .to_list()
    )


def _rows_to_hits(rows: list[dict], kg_name: str, kg_kind: str, min_score: float) -> list[dict]:
    """Shape LanceDB rows into hit dicts (clean content hydrated separately).

    The LanceDB ``text`` column holds the structured *embed-text*, not the clean
    passage — so ``content``/``summary`` are left empty here and filled from
    SQLite by ``_attach_content`` / ``_attach_diary_fields``.
    """
    hits: list[dict] = []
    for row in rows:
        score = round(1.0 - float(row.get("_distance", 1.0)), 4)
        if score < min_score:
            continue
        hits.append(
            {
                "kg_name": kg_name,
                "kg_kind": kg_kind,
                "node_id": row.get("id"),
                "name": row.get("name") or row.get("title") or "",
                "kind": row.get("kind", "chunk"),
                "score": score,
                "summary": "",
                "source_path": row.get("file_path") or "",
                "content": "",
                "timestamp": None,
            }
        )
    return hits


def _attach_diary_fields(hits: list[dict]) -> None:
    by_kg: dict[str, list[dict]] = defaultdict(list)
    for h in hits:
        by_kg[h.get("kg_name", "")].append(h)
    for slug, kg_hits in by_kg.items():
        db_path = _KG_SQLITE.get(slug)
        if not db_path or not Path(db_path).exists():
            continue
        ids = [h["node_id"] for h in kg_hits if h.get("node_id")]
        if not ids:
            continue
        field_by_id: dict[str, tuple[str, str | None]] = {}
        try:
            with sqlite3.connect(str(db_path)) as con:
                placeholders = ",".join("?" * len(ids))
                rows = con.execute(
                    f"SELECT id, text, timestamp FROM nodes WHERE id IN ({placeholders})", ids
                )
                for nid, text, ts in rows:
                    field_by_id[nid] = (text or "", ts)
        except Exception:  # noqa: BLE001
            pass
        for h in kg_hits:
            text, ts = field_by_id.get(h.get("node_id"), ("", None))
            h["content"] = text
            h["summary"] = text
            h["timestamp"] = ts


def _semantic_search(
    query: str,
    k: int,
    min_score: float = 0.0,
    semantic_floor: float = 0.0,
    genre_filter: str | None = None,
) -> list[dict]:
    if _DOCKG_TABLE is None:
        return []
    qvec = _embedder.embed_texts([query])[0]
    where = "kind IN ('chunk', 'section') AND file_path NOT LIKE '%reference.md'"
    if genre_filter:
        where += f" AND file_path LIKE '{genre_filter}/%'"
    rows = _table_search(_DOCKG_TABLE, qvec, where, k)
    hits = _rows_to_hits(rows, "gutenberg", "KGKind.GUTENBERG", min_score)
    _attach_content(hits)
    for h in hits:
        h["summary"] = h.get("content", "")
    if semantic_floor > 0.0 and hits and hits[0]["score"] < semantic_floor:
        return []
    return hits


def _semantic_search_diaries(
    query: str,
    k: int,
    min_score: float = 0.0,
    semantic_floor: float = 0.0,
) -> list[dict]:
    if not _DIARY_TABLES:
        return []
    qvec = _embedder.embed_texts([query])[0]
    where = "kind IN ('chunk', 'section')"
    hits: list[dict] = []
    for slug, table in _DIARY_TABLES.items():
        rows = _table_search(table, qvec, where, k)
        hits.extend(_rows_to_hits(rows, slug, "KGKind.DIARY", min_score))
    hits.sort(key=lambda h: h["score"], reverse=True)
    hits = hits[:k]
    _attach_diary_fields(hits)
    if semantic_floor > 0.0 and hits and hits[0]["score"] < semantic_floor:
        return []
    return hits


def _enrich_catalog(hits: list[dict]) -> None:
    """Attach ``genre``/``title``/``author`` metadata to each hit from the book catalog or diary metadata.

    :param hits: Hit dicts to update in place.
    """
    for h in hits:
        if h.get("kg_kind") in ("KGKind.GUTENBERG", "gutenberg"):
            src = h.get("source_path", "")
            parts = src.split("/")
            if len(parts) >= 2:
                key = f"{parts[0]}/{parts[1]}"
                meta = _catalog.get(key, {})
                h["genre"] = meta.get("genre") or parts[0]
                h["title"] = meta.get("title") or parts[1]
                h["author"] = meta.get("author")
        diary = _DIARY_META.get(h.get("kg_name", ""))
        if diary and not h.get("author"):
            h["genre"] = diary["genre"]
            h["title"] = diary["title"]
            h["author"] = diary["author"]


# ---------------------------------------------------------------------------
# Synthesis (text only — no image generation on RunPod)
# ---------------------------------------------------------------------------


def _list_models() -> list[str]:
    """Query the vLLM endpoint's ``/v1/models`` for available synthesis model IDs.

    :return: List of model IDs, or an empty list if no endpoint is configured or the request fails.
    """
    if not VLLM_ENDPOINT:
        return []
    import httpx

    headers = {"Authorization": f"Bearer {VLLM_API_KEY}"} if VLLM_API_KEY else {}
    try:
        resp = httpx.get(
            f"{VLLM_ENDPOINT}/v1/models",
            headers=headers,
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
        )
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", []) if m.get("id")]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return []


def _synthesize(query: str, hits: list[dict], model: str | None = None) -> str | None:
    """Generate a text answer from the retrieved hits via the vLLM chat-completions endpoint.

    :param query: The original user query.
    :param hits: Retrieved hits; only those with non-empty ``content`` (up to ``SYNTH_MAX_K``) are used.
    :param model: Model ID to use; falls back to ``VLLM_MODEL`` when not given.
    :return: The synthesized answer text, or ``None`` if no endpoint, no usable hits, or the call fails.
    """
    if not VLLM_ENDPOINT:
        return None
    import httpx

    snippets = [h for h in hits[:SYNTH_MAX_K] if h.get("content")]
    if not snippets:
        return None

    ctx_parts = []
    for s in snippets:
        genre = s.get("genre", "")
        author = s.get("author") or ""
        title = s.get("title") or s.get("name") or ""
        header = " | ".join(x for x in [genre, author, title] if x)
        ctx_parts.append(f"[{header}]\n{s['content'].strip()}")
    ctx = "\n\n".join(ctx_parts)

    headers = {"Authorization": f"Bearer {VLLM_API_KEY}"} if VLLM_API_KEY else {}
    try:
        resp = httpx.post(
            f"{VLLM_ENDPOINT}/v1/chat/completions",
            headers=headers,
            json={
                "model": model or VLLM_MODEL,
                "think": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a literary guide to the Project Gutenberg corpus. "
                            "Answer using only the provided source passages. "
                            "If the answer is not in the passages, say so. "
                            "Be concise and cite author and work when relevant."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Source passages:\n{ctx}\n\nQuestion: {query}",
                    },
                ],
                "max_tokens": 2048,
            },
            timeout=httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0),
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return content or None
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handler(job: dict) -> dict:
    """RunPod serverless entry point: validate the request, run semantic search, and optionally synthesize an answer.

    :param job: RunPod job dict; ``job["input"]`` holds the request schema described in the module docstring.
    :return: Response dict with ``hits`` and, if requested, a ``synthesis`` answer (see module docstring for shape).
    """
    inp = job.get("input", {})

    if HANDLER_SECRET and inp.get("secret") != HANDLER_SECRET:
        return {"error": "unauthorized"}

    if inp.get("op") == "models":
        return {"models": _list_models(), "default": VLLM_MODEL}

    query = inp.get("query", "").strip()
    corpus = inp.get("corpus", "all")
    k = max(1, int(inp.get("k", 8)))
    min_score = float(inp.get("min_score", 0.0))
    semantic_floor = float(inp.get("semantic_floor", 0.0))
    synthesize = bool(inp.get("synthesize", False))
    model = (inp.get("model") or "").strip() or None

    if not query:
        return {"error": "query is required"}

    genre_filter: str | None = None
    if corpus in _ALL_GENRES:
        genre_filter = corpus
    elif corpus not in ("all", "diary", "gutenberg"):
        return {
            "error": (
                f"unknown corpus {corpus!r}; choose: all, gutenberg, diary, "
                f"or a genre name ({', '.join(sorted(_ALL_GENRES))})"
            )
        }

    t0_search = time.perf_counter()

    if corpus == "diary":
        hits = _semantic_search_diaries(
            query, k=k, min_score=min_score, semantic_floor=semantic_floor
        )
        _enrich_catalog(hits)
        kgs_queried = len(_DIARY_TABLES)
    else:
        hits = _semantic_search(
            query,
            k=k,
            min_score=min_score,
            semantic_floor=semantic_floor,
            genre_filter=genre_filter,
        )
        _enrich_catalog(hits)
        kgs_queried = 1
        if corpus == "all":
            dhits = _semantic_search_diaries(
                query, k=k, min_score=min_score, semantic_floor=semantic_floor
            )
            _enrich_catalog(dhits)
            hits = sorted(hits + dhits, key=lambda h: h.get("score", 0.0), reverse=True)[:k]
            kgs_queried += len(_DIARY_TABLES)

    search_ms = (time.perf_counter() - t0_search) * 1000
    print(f"[query] {len(hits)} hits in {search_ms:.0f}ms")

    synthesis = None
    synthesis_ms: float | None = None
    if synthesize:
        t0_synth = time.perf_counter()
        synthesis = _synthesize(query, hits, model)
        synthesis_ms = (time.perf_counter() - t0_synth) * 1000

    return {
        "query": query,
        "corpus": corpus,
        "total_hits": len(hits),
        "kgs_queried": kgs_queried,
        "hits": hits,
        "search_ms": round(search_ms),
        "synthesis": synthesis,
        "synthesis_ms": round(synthesis_ms) if synthesis_ms is not None else None,
        "model": (model or VLLM_MODEL) if synthesize else None,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})  # type: ignore[attr-defined]
