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
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import runpod

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GUTENBERG_ROOT = Path(os.environ.get("GUTENBERG_ROOT", "/workspace/gutenberg"))
REGISTRY_PATH = Path("/tmp/gutenberg_worker/registry.sqlite")
VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT_URL", "")
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "Qwen3-8B-MLX-4bit")
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

# Populated at startup: "<genre>/<book>" → {title, author, genre, ...}
_catalog: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def _bootstrap_registry():
    from kg_rag.primitives import KGEntry, KGKind
    from kg_rag.registry import KGRegistry

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    reg = KGRegistry(db_path=REGISTRY_PATH)

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
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            reg.register(entry)
            _KG_SQLITE[slug] = sqlite
            print(f"[bootstrap] registered diary: {slug}")
    else:
        print("[bootstrap] no diaries/ directory found")

    return reg


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

print("[startup] initialising KGRAG orchestrator ...")
from kg_rag.orchestrator import KGRAG  # noqa: E402

_kgrag = KGRAG(registry_path=REGISTRY_PATH, embedder=_embedder)
print("[startup] ready")


# ---------------------------------------------------------------------------
# Hit serialisation
# ---------------------------------------------------------------------------


def _hit_to_dict(hit) -> dict:
    return {
        "kg_name": hit.kg_name,
        "kg_kind": str(hit.kg_kind),
        "node_id": hit.node_id,
        "name": hit.name,
        "kind": hit.kind,
        "score": round(float(hit.score), 4),
        "summary": hit.summary,
        "source_path": hit.source_path,
    }


def _attach_content(hits: list[dict]) -> None:
    """Fetch full node text from the appropriate SQLite for each hit."""
    by_kg: dict[str, list[dict]] = defaultdict(list)
    for h in hits:
        by_kg[h.get("kg_name", "")].append(h)

    for kg_name, kg_hits in by_kg.items():
        db_path = _KG_SQLITE.get(kg_name)
        if not db_path or not db_path.exists():
            continue
        ids = [h["node_id"] for h in kg_hits if h.get("node_id")]
        if not ids:
            continue
        text_by_id: dict[str, str] = {}
        try:
            with sqlite3.connect(str(db_path)) as con:
                placeholders = ",".join("?" * len(ids))
                for nid, text in con.execute(
                    f"SELECT id, text FROM nodes WHERE id IN ({placeholders})", ids
                ):
                    text_by_id[nid] = text or ""
        except Exception:  # noqa: BLE001
            continue
        for h in kg_hits:
            h["content"] = text_by_id.get(h["node_id"], "")


def _enrich_catalog(hits: list[dict]) -> None:
    """Join author/title/genre from catalog.json onto DocKG hits."""
    for h in hits:
        if h.get("kg_kind") not in ("KGKind.GUTENBERG", "gutenberg"):
            continue
        src = h.get("source_path", "")
        parts = src.split("/")
        if len(parts) >= 2:
            key = f"{parts[0]}/{parts[1]}"
            meta = _catalog.get(key, {})
            h["genre"] = meta.get("genre") or parts[0]
            h["title"] = meta.get("title") or parts[1]
            h["author"] = meta.get("author")


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def _list_models() -> list[str]:
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
    except Exception:  # noqa: BLE001
        return []


def _synthesize(query: str, hits: list[dict], model: str | None = None) -> str | None:
    if not VLLM_ENDPOINT:
        return None
    import re

    import httpx

    snippets = [h for h in hits[:SYNTH_MAX_K] if h.get("content")]
    if not snippets:
        return None

    ctx_parts = []
    for s in snippets:
        genre = s.get("genre", s.get("kg_kind", ""))
        author = s.get("author") or ""
        title = s.get("title") or s.get("name") or ""
        header = " · ".join(x for x in [genre, author, title] if x)
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
                            "You are a knowledgeable literary guide to the Project Gutenberg "
                            "corpus — classical literature, philosophy, sacred texts, natural "
                            "history, science fiction, and diaries. Answer the question using "
                            "only the provided source passages. Be concise and specific. "
                            "Cite the author and work when relevant."
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
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handler(job: dict) -> dict:
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

    from kg_rag.primitives import KGKind

    kind_filter = None
    genre_filter: str | None = None

    if corpus == "gutenberg":
        kind_filter = [KGKind.GUTENBERG]
    elif corpus == "diary":
        kind_filter = [KGKind.DIARY]
    elif corpus in _ALL_GENRES:
        kind_filter = [KGKind.GUTENBERG]
        genre_filter = corpus
    elif corpus != "all":
        return {
            "error": (
                f"unknown corpus {corpus!r}; choose: all, gutenberg, diary, "
                f"or a genre name ({', '.join(sorted(_ALL_GENRES))})"
            )
        }

    # Over-request when genre-filtering so post-filter still has enough hits.
    query_k = k * 4 if genre_filter else k

    result = _kgrag.query(
        query,
        k=query_k,
        kinds=kind_filter,
        min_score=min_score,
        semantic_floor=semantic_floor,
    )

    hits = [_hit_to_dict(h) for h in result.hits]
    _attach_content(hits)
    _enrich_catalog(hits)

    if genre_filter:
        hits = [h for h in hits if h.get("genre") == genre_filter][:k]

    synthesis = _synthesize(query, hits, model) if synthesize else None

    return {
        "query": query,
        "corpus": corpus,
        "total_hits": len(hits),
        "kgs_queried": result.kgs_queried,
        "hits": hits,
        "synthesis": synthesis,
        "model": (model or VLLM_MODEL) if synthesize else None,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
