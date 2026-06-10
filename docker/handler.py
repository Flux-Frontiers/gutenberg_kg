# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
KGRAG handler — GutenbergKG corpus.

Serves semantic search over the full Project Gutenberg corpus baked into this
image at /workspace/gutenberg/:
  .dockg/            — consolidated DocKG (245 books, 18 genres, 696K nodes)
  diaries/*/diarykg/ — 4 DiaryKG temporal indices (Pepys, Evelyn, Boswell)

Implements the RunPod serverless API (--rp_serve_api) so it can be driven by
the chat.py Streamlit UI, curl, or any compatible HTTP client.

Volume layout (baked in at build time)
---------------------------------------
  /workspace/gutenberg/
    .dockg/
      graph.sqlite
      lancedb/
      catalog.json
    diaries/
      <name>/.diarykg/
        graph.sqlite
        lancedb/

Environment variables
---------------------
GUTENBERG_ROOT     Root of the baked-in bundle.   Default: /workspace/gutenberg
EMBED_MODEL        Sentence-transformer model ID.  Default: BAAI/bge-small-en-v1.5
HANDLER_SECRET     Optional shared secret.  Requests must include {"secret": "<value>"}.
VLLM_ENDPOINT_URL  Optional OpenAI-compatible endpoint for synthesis (oMLX/Ollama/vLLM).
VLLM_API_KEY       Bearer token for the synthesis endpoint.  Omit for Ollama.
VLLM_MODEL         Model ID.  Default: Qwen3-8B-MLX-4bit
SYNTH_MAX_K        Max snippets fed to synthesis.  Default: 12

Request schema
--------------
{
  "query":          str   — natural-language query (required)
  "secret":         str   — required when HANDLER_SECRET is set
  "corpus":         str   — "all" | "gutenberg" | "diary" | <genre>  (default: "all")
                            <genre> is any genre name, e.g. "philosophy", "sacred-texts"
  "k":              int   — top-k hits  (default: 8)
  "min_score":      float — drop hits below this score  (default: 0.0)
  "semantic_floor": float — discard KG if best hit is below this  (default: 0.0)
  "synthesize":     bool  — call vLLM for a generated answer  (default: false)
  "model":          str   — override VLLM_MODEL for this request
  "op":             str   — "models" returns {"models": [...], "default": ...}
}
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from kg_utils.retrieval import attach_content_by_sqlite
from kg_utils.synthesis import (
    image_synth_for_backend,
    image_synthesizer_from_env,
    text_synth_for_backend,
    text_synthesizer_from_env,
)
from kg_utils.worker import handle_aux_ops

import runpod

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GUTENBERG_ROOT = Path(os.environ.get("GUTENBERG_ROOT", "/workspace/gutenberg"))
REGISTRY_PATH = Path("/tmp/gutenberg_worker/registry.sqlite")
SYNTH_MAX_K = int(os.environ.get("SYNTH_MAX_K", "12"))
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
HANDLER_SECRET = os.environ.get("HANDLER_SECRET", "")

_DOCKG_SQLITE = GUTENBERG_ROOT / ".dockg" / "graph.sqlite"
_DOCKG_LANCEDB = GUTENBERG_ROOT / ".dockg" / "lancedb"
_CATALOG_PATH = GUTENBERG_ROOT / ".dockg" / "catalog.json"
_DIARIES_ROOT = GUTENBERG_ROOT / "diaries"

# Valid genre names (must match corpus/ subdirectory names).
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

# Populated at startup: kg_name → sqlite path (for _attach_content lookups).
_KG_SQLITE: dict[str, Path] = {}

# Populated at startup: the consolidated DocKG LanceDB table, used by the
# semantic-first retrieval path (pure cosine ranking, no graph-hop expansion).
_DOCKG_TABLE = None

# Populated at startup: diary slug → its DiaryKG LanceDB table, so diaries share
# the same true-cosine scoring as the books (no orchestrator hop-expansion).
_DIARY_TABLES: dict = {}

# Populated at startup: "<genre>/<book>" → {title, author, genre, ...}
_catalog: dict[str, dict] = {}

# Static metadata for diary KGs (not in catalog.json, which covers prose/verse only).
_DIARY_META: dict[str, dict] = {
    "pepys-complete": {
        "author": "Samuel Pepys",
        "title": "The Diary of Samuel Pepys — Complete",
        "genre": "diaries",
    },
    "evelyn-volume-1": {
        "author": "John Evelyn",
        "title": "The Diary of John Evelyn — Volume 1",
        "genre": "diaries",
    },
    "evelyn-volume-2": {
        "author": "John Evelyn",
        "title": "The Diary of John Evelyn — Volume 2",
        "genre": "diaries",
    },
    "johnson": {
        "author": "James Boswell",
        "title": "The Journal of a Tour to the Hebrides with Samuel Johnson",
        "genre": "diaries",
    },
}

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def _source_file_for(diary_dir: Path) -> str:
    config = diary_dir / ".diarykg" / "config.json"
    if config.exists():
        return json.loads(config.read_text()).get("source_file", "")
    return ""


def _bootstrap_registry():
    from kg_rag.corpus_registry import CorpusRegistry
    from kg_rag.primitives import CorpusEntry, KGEntry, KGKind
    from kg_rag.registry import KGRegistry

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    reg = KGRegistry(db_path=REGISTRY_PATH)
    corp_reg = CorpusRegistry(db_path=REGISTRY_PATH)

    # --- DocKG (consolidated prose + verse) ---
    if not _DOCKG_SQLITE.exists():
        print(f"[bootstrap] WARNING: DocKG not found at {_DOCKG_SQLITE}")
        print("[bootstrap]   Run 'gutenkg build-corpus' then rebuild the image.")
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

    # --- DiaryKG indices (one per diary) ---
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
            # Slug: "The Diary of Samuel Pepys — Complete" → "pepys-complete"
            slug = (
                diary_dir.name.lower()
                .replace("the diary of ", "")
                .replace("the journal of a tour to the hebrides with ", "")
                .replace("samuel pepys", "pepys")
                .replace("john evelyn", "evelyn")
                .replace("samuel johnson", "johnson")
                .replace("—", "")
                .replace("  ", " ")
                .strip()
                .replace(" ", "-")
            )
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
            # Open the diary's vector table for semantic-first cosine search.
            if lancedb.exists():
                import lancedb as _ldb

                try:
                    _DIARY_TABLES[slug] = _ldb.connect(str(lancedb)).open_table("dockg_nodes")
                except Exception as exc:  # noqa: BLE001
                    print(f"[bootstrap] WARNING: could not open diary table {slug}: {exc}")
            n_diaries += 1
            print(f"[bootstrap] registered diary: {slug}")
    else:
        print("[bootstrap] no diaries/ directory found")
    print(f"[bootstrap] diaries corpus: {n_diaries} KG(s)")

    return reg


def _open_dockg_table() -> None:
    """Open the consolidated DocKG LanceDB table for semantic-first search."""
    global _DOCKG_TABLE
    if not _DOCKG_LANCEDB.exists():
        print(f"[startup] WARNING: DocKG lancedb not found at {_DOCKG_LANCEDB}")
        return
    import lancedb

    db = lancedb.connect(str(_DOCKG_LANCEDB))
    names = list(db.table_names())
    table = "dockg_nodes" if "dockg_nodes" in names else (names[0] if names else None)
    if table is None:
        print(f"[startup] WARNING: no lancedb table found in {_DOCKG_LANCEDB}")
        return
    _DOCKG_TABLE = db.open_table(table)
    print(f"[startup] opened DocKG vector table: {table} ({_DOCKG_TABLE.count_rows()} rows)")


def _load_catalog() -> None:
    if _CATALOG_PATH.exists():
        with open(_CATALOG_PATH, encoding="utf-8") as f:
            _catalog.update(json.load(f))
        print(f"[startup] loaded catalog: {len(_catalog)} books")
    else:
        print(f"[startup] WARNING: catalog.json not found at {_CATALOG_PATH}")


def _make_embedder():
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

print("[startup] initialising synthesis backends ...")
_text_synth = text_synthesizer_from_env()
_image_synth = image_synthesizer_from_env()
print("[startup] ready")


# ---------------------------------------------------------------------------
# Per-request backend factory
# ---------------------------------------------------------------------------


def _synth_for_backend(backend_str: str):
    return text_synth_for_backend(backend_str, _text_synth)


def _image_for_backend(backend_str: str):
    return image_synth_for_backend(backend_str, _image_synth)


# ---------------------------------------------------------------------------
# Hit serialisation
# ---------------------------------------------------------------------------


def _attach_content(hits: list[dict]) -> None:
    """Fetch full node text from the appropriate SQLite for each hit."""
    attach_content_by_sqlite(hits, _KG_SQLITE)


def _table_search(table, qvec, where: str, k: int) -> list[dict]:
    """Run a cosine kNN search with a pre-filter and return raw LanceDB rows."""
    return table.search(qvec).metric("cosine").where(where, prefilter=True).limit(k).to_list()


def _rows_to_hits(rows: list[dict], kg_name: str, kg_kind: str, min_score: float) -> list[dict]:
    """Shape LanceDB rows into hit dicts (clean content hydrated separately).

    The LanceDB ``text`` column holds the structured *embed-text* (``KIND:/TITLE:/
    FILE:/TEXT:`` prefixed), not the clean passage — so ``content``/``summary`` are
    left empty here and filled from SQLite by ``_attach_content`` / ``_attach_diary_fields``.
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
    """Hydrate clean passage text and temporal ``timestamp`` from diary SQLite."""
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
            continue
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
    """Pure dense (cosine) search over the consolidated DocKG vector table.

    Ranks every chunk/section by its *own* semantic distance to the query — no
    graph-hop expansion, so a query that names a book surfaces that book's
    passages on top instead of letting them inherit a flat seed score from a few
    graph-expanded neighbours.  Content-kind and genre filters are pushed into
    LanceDB as a pre-filter so the top-k is computed over the eligible subset.

    :param query: Natural-language query string.
    :param k: Number of hits to return.
    :param min_score: Drop hits whose cosine similarity is below this.
    :param semantic_floor: If the best hit is below this, discard the whole set.
    :param genre_filter: Restrict to a single genre subtree (e.g. ``sacred-texts``).
    :returns: Hit dictionaries ranked best-first, shaped like ``hit_to_dict``.
    """
    if _DOCKG_TABLE is None:
        return []
    qvec = _embedder.embed_texts([query])[0]
    where = "kind IN ('chunk', 'section') AND file_path NOT LIKE '%reference.md'"
    if genre_filter:
        # genre_filter is validated against _ALL_GENRES before this call.
        where += f" AND file_path LIKE '{genre_filter}/%'"
    rows = _table_search(_DOCKG_TABLE, qvec, where, k)
    hits = _rows_to_hits(rows, "gutenberg", "KGKind.GUTENBERG", min_score)
    _attach_content(hits)  # clean passage text from SQLite
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
    """Pure cosine search across the DiaryKG vector tables, merged by score.

    Gives diaries the same true-cosine scoring as the books, so a unified
    (``all``) query ranks both corpora on one comparable scale instead of letting
    the diaries' graph-expanded plateau scores dominate.

    :param query: Natural-language query string.
    :param k: Number of hits to return across all diaries.
    :param min_score: Drop hits whose cosine similarity is below this.
    :param semantic_floor: If the best hit is below this, discard the whole set.
    :returns: Hit dictionaries ranked best-first across all diary KGs.
    """
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
    _attach_diary_fields(hits)  # clean text + timestamp from each diary's SQLite
    if semantic_floor > 0.0 and hits and hits[0]["score"] < semantic_floor:
        return []
    return hits


def _enrich_catalog(hits: list[dict]) -> None:
    """Join author/title/genre from catalog.json onto DocKG hits."""
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
        # Diary hits: fall back to static map keyed by slug.
        diary = _DIARY_META.get(h.get("kg_name", ""))
        if diary and not h.get("author"):
            h["genre"] = diary["genre"]
            h["title"] = diary["title"]
            h["author"] = diary["author"]


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handler(job: dict) -> dict:
    inp = job.get("input", {})

    if HANDLER_SECRET and inp.get("secret") != HANDLER_SECRET:
        return {"error": "unauthorized"}

    aux_result = handle_aux_ops(inp, _synth_for_backend, _image_for_backend)
    if aux_result is not None:
        return aux_result

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
        # Diaries only — semantic-first across the DiaryKG vector tables.
        hits = _semantic_search_diaries(
            query, k=k, min_score=min_score, semantic_floor=semantic_floor
        )
        _enrich_catalog(hits)
        kgs_queried = len(_DIARY_TABLES)
    else:
        # Semantic-first: rank chunks by their own cosine distance (no graph-hop
        # expansion), so a query that names a book surfaces that book on top.
        hits = _semantic_search(
            query,
            k=k,
            min_score=min_score,
            semantic_floor=semantic_floor,
            genre_filter=genre_filter,
        )
        _enrich_catalog(hits)
        kgs_queried = 1  # the consolidated 'gutenberg' DocKG
        if corpus == "all":
            # Fold in the diaries on the *same* true-cosine scale, then re-rank
            # the merged set by score so neither corpus's scoring dominates.
            dhits = _semantic_search_diaries(
                query, k=k, min_score=min_score, semantic_floor=semantic_floor
            )
            _enrich_catalog(dhits)
            hits = sorted(hits + dhits, key=lambda h: h.get("score", 0.0), reverse=True)[:k]
            kgs_queried += len(_DIARY_TABLES)

    search_ms = (time.perf_counter() - t0_search) * 1000
    print(f"[query] {len(hits)} matching results found in {search_ms:.0f}ms")

    synthesis = None
    synthesis_ms: float | None = None
    active_synth = _synth_for_backend(inp.get("backend", ""))
    if synthesize:
        t0_synth = time.perf_counter()
        synthesis = active_synth.synthesize_rag(query, hits, model=model, max_k=SYNTH_MAX_K)
        synthesis_ms = (time.perf_counter() - t0_synth) * 1000
        print(f"[query] synthesis returned in {synthesis_ms:.0f}ms")

    return {
        "query": query,
        "corpus": corpus,
        "total_hits": len(hits),
        "kgs_queried": kgs_queried,
        "hits": hits,
        "search_ms": round(search_ms),
        "synthesis": synthesis,
        "synthesis_ms": round(synthesis_ms) if synthesis_ms is not None else None,
        "model": (model or active_synth._cfg.resolved_model()) if synthesize else None,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
