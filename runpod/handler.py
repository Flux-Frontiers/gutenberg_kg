"""
RunPod serverless handler — GutenbergKG query service.

Serves semantic search over the Project Gutenberg literary corpus
mounted from a RunPod Network Volume.

Environment variables
---------------------
KG_VOLUME        Path where the network volume is mounted. Default: /workspace
EMBED_MODEL      Sentence-transformer model ID. Default: BAAI/bge-small-en-v1.5
VLLM_ENDPOINT_URL   Optional: RunPod vLLM endpoint base URL for synthesis.
RUNPOD_API_KEY   RunPod API key (used for vLLM auth when synthesize=true).
VLLM_MODEL       Model ID served by the vLLM endpoint. Default: Qwen/Qwen3-8B-Instruct

Request schema
--------------
{
  "query":          str   — natural-language query (required)
  "k":              int   — top-k hits to return (default: 8)
  "min_score":      float — drop hits below this score (default: 0.0)
  "semantic_floor": float — discard the KG entirely if its best hit is below
                           this value (default: 0.0)
  "synthesize":     bool  — call vLLM endpoint for a generated answer
                           (default: false)
}
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import runpod

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VOLUME = Path(os.environ.get("KG_VOLUME", "/workspace"))
REGISTRY_PATH = Path("/tmp/gutenkg_worker/registry.sqlite")
VLLM_ENDPOINT = os.environ.get("VLLM_ENDPOINT_URL", "")
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-8B-Instruct")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

_CORPUS_MAP = {
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


print("[startup] bootstrapping registry …")
_registry = _bootstrap_registry()

print("[startup] loading embedder …")
_embedder = _make_embedder()

print("[startup] initialising KGRAG orchestrator …")
from kg_rag.orchestrator import KGRAG  # noqa: E402

_kgrag = KGRAG(registry_path=REGISTRY_PATH, embedder=_embedder)
print("[startup] ready ✓")


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


def _synthesize(query: str, hits: list[dict]) -> str | None:
    if not VLLM_ENDPOINT:
        return None
    import httpx

    ctx = "\n\n".join(f"[{h['source_path']}]\n{h['summary']}" for h in hits if h.get("summary"))
    resp = httpx.post(
        f"{VLLM_ENDPOINT}/v1/chat/completions",
        headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
        json={
            "model": VLLM_MODEL,
            "messages": [
                {"role": "system", "content": "Answer using only the provided context."},
                {"role": "user", "content": f"Context:\n{ctx}\n\nQuestion: {query}"},
            ],
            "max_tokens": 512,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handler(job: dict) -> dict:
    inp = job.get("input", {})
    query = inp.get("query", "").strip()
    k = max(1, int(inp.get("k", 8)))
    min_score = float(inp.get("min_score", 0.0))
    semantic_floor = float(inp.get("semantic_floor", 0.0))
    synthesize = bool(inp.get("synthesize", False))

    if not query:
        return {"error": "query is required"}

    from kg_rag.primitives import KGKind

    result = _kgrag.query(
        query,
        k=k,
        kinds=[KGKind.GUTENBERG],
        min_score=min_score,
        semantic_floor=semantic_floor,
    )

    hits = [_hit_to_dict(h) for h in result.hits]
    synthesis = _synthesize(query, hits) if synthesize else None

    return {
        "query": query,
        "total_hits": result.total_hits,
        "kgs_queried": result.kgs_queried,
        "hits": hits,
        "synthesis": synthesis,
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
