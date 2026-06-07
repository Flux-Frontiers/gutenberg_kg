# GutenbergKG RunPod Serverless Worker

Serves semantic search over the **Project Gutenberg literary corpus** as a
cost-efficient RunPod serverless endpoint that scales to zero.

---

## Architecture

```
Client
  │ POST /v2/<endpoint-id>/runsync
  ▼
RunPod Serverless — GutenbergKG Query Worker
  • handler.py bootstraps the DocKG registry from the Network Volume on startup
  • BAAI/bge-small-en-v1.5 baked into the image (no cold-start download)
  • LanceDB + SQLite indices served from Network Volume (~200 MB)
  │ (optional, synthesize=true)
  ▼
RunPod vLLM Endpoint — Qwen3-8B-Instruct

RunPod Network Volume (~10 GB reserved)
  /workspace/
  └── gutenberg_kg/.dockg/       (DocKG index — SQLite + LanceDB)
```

---

## Step 1 — Build and push the Docker image

```bash
chmod +x build_image.sh
./build_image.sh gutenkg-worker:latest

docker tag gutenkg-worker:latest <your-registry>/gutenkg-worker:latest
docker push <your-registry>/gutenkg-worker:latest
```

`build_image.sh` builds local Python wheels for `gutenberg-kg` and `kg-rag`
(not yet on PyPI), then runs `docker build`.

Assumed repo layout (siblings):
```
repos/
├── gutenberg_kg/    ← this repo
└── kgrag/
```

---

## Step 2 — Create a Network Volume

1. RunPod dashboard → **Storage** → **+ Network Volume**
2. Size: **10 GB** (current indices are ~200 MB; 10 GB gives plenty of headroom)
3. Region: same datacenter as the worker

---

## Step 3 — Populate the volume

Spin up a temporary RunPod dev pod with the volume attached at `/workspace`
(any cheap CPU pod — no GPU needed for index building).

**Option A — push pre-built local indices** (~130 MB, minutes):

```bash
./push_indices.sh
```

**Option B — build from scratch inside the pod** (full Gutenberg catalog):

```bash
# Upload the builder to the pod
scp -P <PORT> runpod/build_kg.py root@ssh.runpod.io:/tmp/

# SSH in and run
ssh -p <PORT> root@ssh.runpod.io
python3 /tmp/build_kg.py

# Rebuild indices only (repos + venv already present):
python3 /tmp/build_kg.py --rebuild-only

# Skip corpus download, ingest from existing files:
python3 /tmp/build_kg.py --skip-download

# Custom genres:
python3 /tmp/build_kg.py --genres philosophy science english-literature

# Full help:
python3 /tmp/build_kg.py --help
```

---

## Step 4 — Deploy the serverless endpoint

RunPod dashboard → **Serverless** → **+ New Endpoint**

| Setting | Value |
|---|---|
| Container image | `<your-registry>/gutenkg-worker:latest` |
| GPU | RTX 3080 (or CPU-only — embedding runs on CPU) |
| Min workers | 0 |
| Max workers | 3 |
| FlashBoot | Enabled |
| Network Volume | Attach at `/workspace` |

**Environment variables:**

| Variable | Value |
|---|---|
| `KG_VOLUME` | `/workspace` |
| `HANDLER_SECRET` | shared secret for requests (optional) |
| `VLLM_ENDPOINT_URL` | `https://api.runpod.ai/v2/<vllm-endpoint-id>` (optional) |
| `VLLM_API_KEY` | bearer token for synthesis endpoint (optional) |
| `RUNPOD_API_KEY` | fallback token if `VLLM_API_KEY` is unset |
| `VLLM_MODEL` | `Qwen/Qwen3-8B-Instruct` (optional) |
| `SYNTH_MAX_K` | max passages fed to synthesis (default `12`) |

---

## Calling the endpoint

```bash
curl -s -X POST \
  "https://api.runpod.ai/v2/<ENDPOINT_ID>/runsync" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "query": "Marcus Aurelius on suffering and stoic virtue",
      "corpus": "philosophy",
      "k": 8,
      "synthesize": true
    }
  }' | jq .
```

**Request fields:**

| Field | Type | Default | Description |
|---|---|---|---|
| `op` | str | — | Optional operation: `models` returns available synthesis models |
| `query` | str | — | Natural-language query (required) |
| `secret` | str | — | Required if `HANDLER_SECRET` is set |
| `corpus` | str | `all` | `all`, `gutenberg`, or a genre like `philosophy` |
| `k` | int | `8` | Top-k hits |
| `min_score` | float | `0.0` | Drop hits below this score |
| `semantic_floor` | float | `0.0` | Discard the KG if its best hit is below this |
| `synthesize` | bool | `false` | Generate an answer via the vLLM endpoint |
| `model` | str | `VLLM_MODEL` | Override synthesis model for this request |

**No image generation in this worker:**

This RunPod worker intentionally supports retrieval and text synthesis only. It does not
expose image-generation operations.

**Model discovery request:**

```bash
curl -s -X POST \
  "https://api.runpod.ai/v2/<ENDPOINT_ID>/runsync" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"op":"models"}}' | jq .
```

**Example response:**

```json
{
  "output": {
    "query": "Marcus Aurelius on suffering and stoic virtue",
    "corpus": "philosophy",
    "total_hits": 8,
    "kgs_queried": 1,
    "search_ms": 142,
    "hits": [
      {
        "kg_name": "gutenberg",
        "kg_kind": "gutenberg",
        "node_id": "...",
        "name": "...",
        "kind": "chunk",
        "score": 0.8912,
        "summary": "The impediment to action advances action. What stands in the way becomes the way.",
        "source_path": "philosophy/meditations.md",
        "content": "...full node text...",
        "genre": "philosophy",
        "title": "Meditations",
        "author": "Marcus Aurelius"
      }
    ],
    "synthesis": "...grounded answer...",
    "synthesis_ms": 1310,
    "model": "Qwen/Qwen3-8B-Instruct"
  }
}
```

---

## Optional: vLLM generation endpoint

Deploy via RunPod Hub → **vLLM**:
- Model: `Qwen/Qwen3-8B-Instruct`
- GPU: RTX 4090
- `MAX_MODEL_LEN=8192`

Then set `VLLM_ENDPOINT_URL` in the query worker's environment and pass
`"synthesize": true` in requests to get a generated answer grounded in the
Gutenberg corpus.

---

## Local smoke test

```bash
cd runpod/
python test_local.py
```

The test script creates a symlink under a temp directory pointing at your local
`.dockg/` indices so you can validate the handler without Docker or a RunPod
account.

---

## Expanding the corpus

1. Download and ingest additional genres locally:
   ```bash
   gutenkg download fetch-genre science --max-results 200 --yes
   gutenkg ingest --genre science --force-build
   ```
2. Push the updated `.dockg/` to the Network Volume:
   ```bash
   ./push_indices.sh
   ```
3. No image rebuild needed — the handler reads indices from the volume at startup.
