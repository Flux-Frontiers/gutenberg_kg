# RunPod Serverless Deployment

This document covers deploying GutenbergKG as a RunPod serverless endpoint. This is a distinct path from the local Docker app (`make up`) — two different images, two different purposes.

| | Local app (`docker/`) | RunPod worker (`runpod/`) |
|---|---|---|
| Image size | ~4–6 GB (corpus baked in) | ~1.5 GB (packages + model only) |
| Corpus location | Baked into image | RunPod Network Volume |
| Push to DockerHub? | No — local only | Yes — required |
| Image generation | Yes (FLUX.2-Klein) | No |
| Chat UI | Yes (Streamlit) | No — retrieval + synthesis API only |

---

## Architecture

```
Client
  │  POST /v2/<endpoint-id>/runsync
  ▼
RunPod Serverless — GutenbergKG Query Worker
  • BAAI/bge-small-en-v1.5 baked into the image (no cold-start download)
  • DocKG + DiaryKG indices served from the Network Volume
  │  (optional, synthesize=true)
  ▼
RunPod vLLM Endpoint — Qwen3-8B-Instruct

RunPod Network Volume (20 GB recommended)
  /workspace/
  └── gutenberg_kg/
      ├── .dockg/          (DocKG: graph.sqlite + vectors.sqlite)
      └── diaries/         (DiaryKG temporal indices)
```

---

## Prerequisites

- Local corpus built: `make build-corpus` has completed and `bundles/gutenberg-all/` exists.
- Docker installed and authenticated with DockerHub (or another registry).
- RunPod account with a Network Volume created (≥ 20 GB, same region as your planned worker).
- SSH key added to RunPod (Settings → SSH Public Keys).

Sibling repo layout assumed by `build_image.sh`:

```
repos/
├── gutenberg_kg/    ← this repo
└── kgrag/
```

---

## Step 1 — Build and push the worker image

```bash
cd runpod
./build_image.sh gutenkg-worker:latest

docker tag gutenkg-worker:latest <your-registry>/gutenkg-worker:latest
docker push <your-registry>/gutenkg-worker:latest
```

`build_image.sh` builds local Python wheels for `gutenberg-kg` and `kgrag` (not yet on PyPI), then runs `docker build`. The image is ~1.5 GB: Python packages + the embedding model baked in. The corpus is **not** in this image.

---

## Step 2 — Populate the Network Volume

Spin up a temporary RunPod dev pod (any cheap CPU pod — no GPU needed) with the Network Volume attached at `/workspace`. Get its SSH address from the RunPod dashboard: **Pods → \<pod\> → Connect → SSH over exposed TCP**.

```bash
# From your local machine (gutenberg_kg/runpod/):
./push_indices.sh
# Prompts for pod SSH host and port, or set POD_HOST / POD_PORT env vars.
```

This rsyncs `bundles/gutenberg-all/` → `/workspace/gutenberg_kg/` on the volume. The transfer is several GB (1.3M nodes, 5.2M edges, 384-dim vectors). Once done, detach or terminate the temporary pod — the volume persists.

---

## Step 3 — Deploy the serverless endpoint

RunPod dashboard → **Serverless → + New Endpoint**

| Setting | Value |
|---|---|
| Container image | `<your-registry>/gutenkg-worker:latest` |
| GPU | RTX 3080 (embedding runs on CPU — GPU optional) |
| Min workers | 0 |
| Max workers | 3 |
| FlashBoot | Enabled |
| Network Volume | Attach at `/workspace` |

**Environment variables:**

| Variable | Value |
|---|---|
| `KG_VOLUME` | `/workspace` |
| `HANDLER_SECRET` | Shared secret for requests (optional but recommended) |
| `VLLM_ENDPOINT_URL` | `https://api.runpod.ai/v2/<vllm-endpoint-id>` (optional) |
| `VLLM_API_KEY` | Bearer token for synthesis endpoint (optional) |
| `RUNPOD_API_KEY` | Fallback token if `VLLM_API_KEY` is unset |
| `VLLM_MODEL` | `Qwen/Qwen3-8B-Instruct` (optional) |
| `SYNTH_MAX_K` | Max passages fed to synthesis (default `12`) |

---

## Step 4 — Test the endpoint

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
      "synthesize": false
    }
  }' | jq .
```

---

## Request reference

| Field | Type | Default | Description |
|---|---|---|---|
| `op` | str | — | `models` returns available synthesis models |
| `query` | str | — | Natural-language query (required) |
| `secret` | str | — | Required if `HANDLER_SECRET` is set |
| `corpus` | str | `all` | `all`, `gutenberg`, `diary`, or a genre slug |
| `k` | int | `8` | Top-k hits to return |
| `min_score` | float | `0.0` | Drop hits below this score |
| `semantic_floor` | float | `0.0` | Discard the KG if its best hit is below this |
| `synthesize` | bool | `false` | Call the vLLM endpoint for a generated answer |
| `model` | str | `VLLM_MODEL` | Override synthesis model for this request |

Available genre slugs: `american-literature`, `ancient-classical`, `biography`, `drama`, `english-literature`, `french-literature`, `german-literature`, `letters`, `natural-history`, `philosophy`, `russian-literature`, `sacred-texts`, `science-fiction`, `shakespeare`, `spanish`, `travel`, `world-literature`.

**Note:** image generation is not available in the RunPod worker. Use `make up` locally for the full stack including FLUX.2-Klein.

---

## Local smoke test

Before pushing to RunPod, validate the handler against your local corpus bundle:

```bash
cd runpod
python test_local.py
```

This symlinks `bundles/gutenberg-all/` into a temp volume directory so the handler resolves the same paths it would on a RunPod Network Volume. Requires `make build-corpus` to have run first.

---

## Optional: vLLM synthesis endpoint

Deploy via RunPod Hub → **vLLM**:
- Model: `Qwen/Qwen3-8B-Instruct`
- GPU: RTX 4090
- `MAX_MODEL_LEN=8192`

Set `VLLM_ENDPOINT_URL` in the query worker's environment and pass `"synthesize": true` in requests to get a generated answer grounded in the corpus.

---

## Updating the corpus

After adding books locally (`gutenkg ingest`) and rebuilding the bundle (`make build-corpus`):

```bash
# Spin up the temporary pod again with the volume attached, then:
cd runpod
./push_indices.sh
```

No image rebuild is needed — the handler reads indices from the volume at startup.
