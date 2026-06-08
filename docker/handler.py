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
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from kg_utils.retrieval import attach_content_by_sqlite, hit_to_dict
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
            n_diaries += 1
            print(f"[bootstrap] registered diary: {slug}")
    else:
        print("[bootstrap] no diaries/ directory found")
    print(f"[bootstrap] diaries corpus: {n_diaries} KG(s)")

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


def _hit_to_dict(hit) -> dict:
    return hit_to_dict(hit, include_diary_timestamp=True)


def _attach_content(hits: list[dict]) -> None:
    """Fetch full node text from the appropriate SQLite for each hit."""
    attach_content_by_sqlite(hits, _KG_SQLITE)


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

    from kg_rag.primitives import KGKind

    kind_filter = None
    genre_filter: str | None = None

    if corpus == "gutenberg":
        kind_filter = [KGKind.GUTENBERG]
    elif corpus in _ALL_GENRES:
        kind_filter = [KGKind.GUTENBERG]
        genre_filter = corpus
    elif corpus not in ("all", "diary"):
        return {
            "error": (
                f"unknown corpus {corpus!r}; choose: all, gutenberg, diary, "
                f"or a genre name ({', '.join(sorted(_ALL_GENRES))})"
            )
        }

    t0_search = time.perf_counter()

    if corpus == "diary":
        # Query only the diary KGs via the "diaries" corpus — avoids dilution
        # from the 696K-node main dockg when searching for diary-specific content.
        result = _kgrag.query_corpus(
            "diaries",
            query,
            k=k,
            min_score=min_score,
            semantic_floor=semantic_floor,
        )
    else:
        # Over-request for genre post-filtering; exact k otherwise.
        query_k = k * 6 if genre_filter else k
        result = _kgrag.query(
            query,
            k=query_k,
            kinds=kind_filter,
            min_score=min_score,
            semantic_floor=semantic_floor,
        )

    hits = [_hit_to_dict(h) for h in result.hits]
    # Drop structural graph nodes — entities, keywords, topics, and bare document
    # nodes carry no passage text and outscore content chunks on name-match queries.
    hits = [h for h in hits if h.get("kind") in ("chunk", "section")]
    _attach_content(hits)
    _enrich_catalog(hits)

    if genre_filter:
        hits = [h for h in hits if h.get("genre") == genre_filter][:k]
    elif corpus == "diary":
        hits = hits[:k]

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
        "kgs_queried": result.kgs_queried,
        "hits": hits,
        "search_ms": round(search_ms),
        "synthesis": synthesis,
        "synthesis_ms": round(synthesis_ms) if synthesis_ms is not None else None,
        "model": (model or active_synth._cfg.resolved_model()) if synthesize else None,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
