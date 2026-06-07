"""
RunPod serverless handler — GutenbergKG query service.

Serves semantic search over the Project Gutenberg literary corpus
mounted from a RunPod Network Volume.

Environment variables
---------------------
KG_VOLUME        Path where the network volume is mounted. Default: /workspace
EMBED_MODEL      Sentence-transformer model ID. Default: BAAI/bge-small-en-v1.5
HANDLER_SECRET   Optional shared secret for requests.
VLLM_ENDPOINT_URL Optional: OpenAI-compatible endpoint base URL for synthesis.
VLLM_API_KEY     Optional bearer token for synthesis endpoint.
RUNPOD_API_KEY   Optional fallback token for synthesis endpoint.
VLLM_MODEL       Default model ID used for synthesis.
SYNTH_MAX_K      Max passages sent to synthesis (default: 12).

Request schema
--------------
{
    "op":             str   — optional operation. "models" lists synthesis models.
  "query":          str   — natural-language query (required)
    "secret":         str   — required when HANDLER_SECRET is configured
    "corpus":         str   — "all" | "gutenberg" | <genre> (default: "all")
  "k":              int   — top-k hits to return (default: 8)
  "min_score":      float — drop hits below this score (default: 0.0)
  "semantic_floor": float — discard the KG entirely if its best hit is below
                           this value (default: 0.0)
  "synthesize":     bool  — call vLLM endpoint for a generated answer
                           (default: false)
    "model":          str   — optional synthesis model override
}

This worker intentionally excludes all image-generation operations.
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

import runpod

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VOLUME = Path(os.environ.get("KG_VOLUME", "/workspace"))
REGISTRY_PATH = Path("/tmp/gutenkg_worker/registry.sqlite")
VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT_URL", "")
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "") or os.environ.get("RUNPOD_API_KEY", "")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-8B-Instruct")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
SYNTH_MAX_K = int(os.environ.get("SYNTH_MAX_K", "12"))
HANDLER_SECRET = os.environ.get("HANDLER_SECRET", "")

_DOCKG_SQLITE = VOLUME / "gutenberg_kg" / ".dockg" / "graph.sqlite"
_CATALOG_PATH = VOLUME / "gutenberg_kg" / ".dockg" / "catalog.json"
_KG_SQLITE: dict[str, Path] = {}
_CATALOG: dict[str, dict] = {}

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

_CORPUS_MAP: dict[str, tuple[str, Path, Path, Path]] = {
    "gutenberg": (
        "gutenberg",
        VOLUME / "gutenberg_kg",
        VOLUME / "gutenberg_kg" / ".dockg" / "graph.sqlite",
        VOLUME / "gutenberg_kg" / ".dockg" / "lancedb",
    ),
}


# ---------------------------------------------------------------------------
# Startup: bootstrap registry, load embedder, initialise orchestrator
# ---------------------------------------------------------------------------


def _bootstrap_registry():
    from kg_rag.primitives import KGEntry, KGKind
    from kg_rag.registry import KGRegistry

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    reg = KGRegistry(db_path=REGISTRY_PATH)

    for name, (kind_str, repo_path, sqlite_path, lancedb_path) in _CORPUS_MAP.items():
        repo_path = Path(repo_path)
        sqlite_path = Path(sqlite_path)
        lancedb_path = Path(lancedb_path)
        if not sqlite_path.exists():
            print(f"[bootstrap] {name}: index not found at {sqlite_path}, skipping")
            continue
        entry = KGEntry(
            id=str(uuid.uuid4()),
            name=name,
            kind=KGKind.from_str(kind_str),
            repo_path=repo_path,
            venv_path=Path("/usr"),
            sqlite_path=sqlite_path,
            lancedb_path=lancedb_path,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        reg.register(entry)
        _KG_SQLITE[name] = sqlite_path
        print(f"[bootstrap] registered {name} ({kind_str}) from {sqlite_path}")

    registered = [e.name for e in reg.list()]
    print(f"[bootstrap] active corpora: {registered}")
    return reg


def _make_embedder():
    from kg_rag._embedders import SentenceTransformerEmbedder

    print(f"[startup] loading embedder: {EMBED_MODEL}")
    emb = SentenceTransformerEmbedder(EMBED_MODEL)
    emb.embed_texts(["warm up"])
    print("[startup] embedder ready")
    return emb


def _load_catalog() -> None:
    if not _CATALOG_PATH.exists():
        print(f"[startup] catalog not found at {_CATALOG_PATH}; metadata enrichment disabled")
        return
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        _CATALOG.update(data)
    print(f"[startup] loaded catalog: {len(_CATALOG)} entries")


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
# Helpers
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
        except sqlite3.Error:
            continue
        for h in kg_hits:
            h["content"] = text_by_id.get(h["node_id"], "")


def _enrich_catalog(hits: list[dict]) -> None:
    for h in hits:
        src = h.get("source_path", "")
        parts = src.split("/")
        if len(parts) >= 2:
            key = f"{parts[0]}/{parts[1]}"
            meta = _CATALOG.get(key, {})
            h["genre"] = meta.get("genre") or parts[0]
            h["title"] = meta.get("title") or parts[1]
            h["author"] = meta.get("author")


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
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return []


def _synthesize(query: str, hits: list[dict], model: str | None = None) -> str | None:
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
    elif corpus in _ALL_GENRES:
        kind_filter = [KGKind.GUTENBERG]
        genre_filter = corpus
    elif corpus != "all":
        return {
            "error": (
                f"unknown corpus {corpus!r}; choose: all, gutenberg, "
                f"or a genre name ({', '.join(sorted(_ALL_GENRES))})"
            )
        }

    t0_search = time.perf_counter()
    query_k = k * 6 if genre_filter else k
    result = _kgrag.query(
        query,
        k=query_k,
        kinds=kind_filter,
        min_score=min_score,
        semantic_floor=semantic_floor,
    )

    hits = [_hit_to_dict(h) for h in result.hits]
    hits = [h for h in hits if h.get("kind") in ("chunk", "section")]
    _attach_content(hits)
    _enrich_catalog(hits)

    if genre_filter:
        hits = [h for h in hits if h.get("genre") == genre_filter][:k]
    else:
        hits = hits[:k]

    search_ms = (time.perf_counter() - t0_search) * 1000.0

    synthesis = None
    synthesis_ms: float | None = None
    if synthesize:
        t0_synth = time.perf_counter()
        synthesis = _synthesize(query, hits, model)
        synthesis_ms = (time.perf_counter() - t0_synth) * 1000.0

    return {
        "query": query,
        "corpus": corpus,
        "total_hits": len(hits),
        "kgs_queried": result.kgs_queried,
        "hits": hits,
        "search_ms": round(search_ms),
        "synthesis": synthesis,
        "synthesis_ms": round(synthesis_ms) if synthesis_ms is not None else None,
        "model": (model or VLLM_MODEL) if synthesize else None,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})  # type: ignore[attr-defined]
