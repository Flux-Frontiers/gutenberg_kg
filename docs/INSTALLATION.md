# Installation

This guide covers everything needed to install, build, and run GutenbergKG — both the **CLI workflow** (build and query the corpus directly) and the **Docker workflow** (run the corpus behind a query worker and chat UI).

> **TL;DR** — For the CLI: install Poetry, `poetry install --extras full`, `gutenkg ingest --force-build`. For Docker: `make build-corpus && make build && make run`. Querying needs no LLM; synthesis and image generation need a local LLM (oMLX or Ollama).

---

## Requirements

| | Required for | Version | Notes |
|---|---|---|---|
| **Python** | everything | 3.12 or 3.13 (`>=3.12,<3.14`) | 3.14 not yet supported |
| **[Poetry](https://python-poetry.org/)** | CLI workflow | 2.x | dependency management + virtual env |
| **[GNU Make](https://www.gnu.org/software/make/)** | build/run targets | any | drives `build-corpus`, `build`, `run`, `chat`, `up` |
| **[Docker](https://docs.docker.com/get-docker/)** | container workflow | Engine 24+, Compose v2 | `docker compose` (v2 syntax, not `docker-compose`) |
| **Local LLM** | synthesis + image generation *(optional)* | — | [oMLX](https://omlx.ai) on Apple Silicon, or [Ollama](https://ollama.com) cross-platform |

### Do I need an LLM?

**No — not to query the corpus.** The knowledge graph and vector index answer semantic queries deterministically on their own. A local LLM is only required for the two optional layers:

- **Synthesis** — summarizing and comparing retrieved passages (`kgrag synthesize`, chat UI).
- **Image generation** — the VLM rewrite stage of `gutenkg imagine`.

On Apple Silicon, **oMLX** is recommended (fast, multi-model, OpenAI-compatible). **Ollama** works on macOS, Linux, and Windows.

### Platform notes

- **Apple Silicon (M-series)** is the primary target. The full corpus rebuilds in ~30 min on an M5 Max, ~45 min on a Mac mini M4. Image generation (FLUX.2-Klein) and oMLX are Apple-Silicon-only.
- **Linux / Windows** — the CLI and Docker query/synthesis workflows run anywhere Python 3.12+ and Docker run; use Ollama for synthesis. The MLX-based image generation path is not available off Apple Silicon.

---

## CLI workflow

### 1. Clone and install

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
cd gutenberg_kg
poetry install --extras full
gutenkg --help
```

`--extras full` is the **recommended default** — it installs everything except dev tooling (KG integrations, visualisation, and the MCP server). A bare `poetry install` gives you the core runtime only; layer in individual extras if you want a leaner install:

| Extra | Installs | Install with |
|---|---|---|
| `full` | **everything but dev** (kgdeps + viz + viz3d + mcp) — **recommended** | `poetry install --extras full` |
| `kgdeps` | doc-kg, diary-kg, kg-rag | `poetry install --extras kgdeps` |
| `viz` | plotly (2-D growth timeline) | `poetry install --extras viz` |
| `viz3d` | pyvista, PyQt5, pycode-kg (3-D visualiser) | `poetry install --extras viz3d` |
| `mcp` | fastmcp, structlog (MCP server) | `poetry install --extras mcp` |
| `dev` | pytest, ruff, ty, pdoc, pre-commit | `poetry install --extras dev` |
| `all` | `full` + dev (literally everything) | `poetry install --all-extras` |
| *(none)* | core runtime only | `poetry install` |

Contributors who need the test/lint toolchain should use `--all-extras` (adds `dev` on top of `full`).

Prefer a plain venv + pip? The same extras work with pip:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[full]"           # or ".[all]" to include dev tools
```

### 2. Build the knowledge graph

The graph indices are **not committed to git** — they're local build artifacts. Rebuild them from the source Markdown:

```bash
gutenkg ingest --force-build
```

> **Expect 30–45 minutes** for a full rebuild on Apple Silicon (M5 Max ~30 min, Mac mini M4 ~45 min). Individual genres take 30 seconds to 5 minutes.

### 3. Query

```bash
# Semantic search within a genre
dockg query "characters who seek revenge" --corpus gutenberg-russian-literature

# Cross-work thematic analysis
kgrag corpus query gutenberg-philosophy "free will and moral responsibility"
```

The full command reference is in [`CHEATSHEET.md`](CHEATSHEET.md); pipeline internals are in [`DOWNLOAD_PIPELINE.md`](DOWNLOAD_PIPELINE.md).

---

## Docker workflow

The Docker image extends a KGRAG worker base image with a pre-built corpus bundle (DocKG + DiaryKG indices) baked in. Because the bundle is generated locally, you need the CLI installed first.

### 1. Install the CLI and build the bundle

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
cd gutenberg_kg
poetry install --extras full

make build-corpus      # builds DiaryKG indices, then bundles DocKG + diaries (~24 min)
```

`make build-corpus` runs `make build-diaries` first (a prerequisite), then `gutenkg build-corpus`, producing `bundles/gutenberg-all/` (gitignored). `make build-diaries` in turn depends on `make chunk-diaries`, which reconstructs each diary's git-ignored `.diary/` chunk corpus from the committed `<book>.md` — so a fresh clone needs no extra steps. (The chunker uses spaCy; if prompted, run `python -m spacy download en_core_web_sm` once.)

### 2. Build the image and bring up the stack

```bash
make build             # docker build -f docker/Dockerfile -t corpus-gutenberg:latest .
make up                # worker (:8000) + chat UI (:8501) + FLUX image server (:8090)
```

`make build` then `make up` is the recommended happy path — it bakes the bundle into the image and brings up the full stack in one command. Fire a one-shot query against the running worker:

```bash
make query Q="What is justice according to Plato?"
```

### 3. Lighter setups and lifecycle

```bash
make run         # worker only, on http://localhost:8000
make chat        # worker + Streamlit chat UI on http://localhost:8501 (no image server)
make stop        # shut everything down
make logs        # follow worker logs
```

### Make targets reference

| Target | Does |
|---|---|
| `make chunk-diaries` | rebuild `.diary/` chunks from committed `<book>.md` (clean-clone step) |
| `make build-diaries` | rebuild `.diarykg/` indices (depends on `chunk-diaries`; prerequisite for `build-corpus`) |
| `make build-corpus` | rebuild the DocKG + diary bundle (~24 min) |
| `make build` | build the Docker image (bakes the bundle in) |
| `make run` | start the worker on `:8000` |
| `make chat` | start worker + chat UI on `:8501` |
| `make image-server` | start the local FLUX image server on `:8090` (isolated `.venv-image`) |
| `make up` | start everything (worker + chat + image server) |
| `make query Q="…"` | fire a one-shot query against the running worker |
| `make logs` | follow worker logs |
| `make stop` | shut everything down |
| `make clean` | remove the Docker image |

---

## Connecting a local LLM (optional)

Synthesis and image generation reach a host LLM. From inside Docker, the host is `host.docker.internal`.

### oMLX (Apple Silicon, recommended)

Start oMLX on **port 8080** (8000 is taken by the worker):

```bash
omlx serve mlx-community/Qwen3-30B-A3B-Instruct-2507-MLX-4bit --port 8080
```

Then copy and edit the environment file:

```bash
cp docker/.env.example docker/.env
```

Set in `docker/.env`:

```bash
VLLM_ENDPOINT_URL=http://host.docker.internal:8080/v1
VLLM_MODEL=Qwen3-4B-Instruct-2507-MLX-8bit
VLLM_API_KEY=sk-your-omlx-api-key     # from ~/.omlx/settings.json → auth.api_key
```

### Ollama (cross-platform)

```bash
ollama serve
ollama pull qwen3:4b
```

Set in `docker/.env`:

```bash
OLLAMA_ENDPOINT=http://host.docker.internal:11434/v1
```

### OpenAI (cloud — fully supported)

The OpenAI provider path works end to end — both **synthesis** and **image generation** — with no local model server at all. The endpoints and model IDs have sensible defaults (`https://api.openai.com/v1`, `gpt-4o-mini` for text, `gpt-image-1` for images), so the **only required variable is your API key**:

```bash
# docker/.env  — minimal OpenAI setup
OPENAI_API_KEY=sk-...
```

With just `OPENAI_API_KEY` set:

- **Synthesis** — select **OpenAI** in the chat UI's Provider dropdown (or send `"backend": "openai"` to the worker). Uses `gpt-4o-mini` unless you pick another model.
- **Image generation** — set `IMAGE_BACKEND=openai` to route image requests to `gpt-image-1` instead of the local FLUX server. No `make image-server` needed.

```bash
# docker/.env  — OpenAI for both text synthesis and image generation
OPENAI_API_KEY=sk-...
IMAGE_BACKEND=openai          # route images to gpt-image-1 (default is local mflux-serve)
# Optional overrides:
SYNTH_MODEL=gpt-4o            # text model (default gpt-4o-mini)
IMAGE_MODEL=gpt-image-1       # image model (default gpt-image-1)
```

Because OpenAI is a cloud API, this is the **one provider path that works identically on Linux and Windows** — no Apple Silicon, oMLX, or local FLUX server required.

### Image generation (local)

`gutenkg imagine` and the chat UI's image feature can instead use a local FLUX image server (`make image-server`, port 8090, Apple Silicon only). Set `GUTENKG_IMAGE_ENDPOINT=http://host.docker.internal:8090` in `docker/.env`, or leave it blank to disable image rendering. See [`CHEATSHEET.md § Corpus-Grounded Image Generation`](CHEATSHEET.md).

---

## Environment variables — full reference

All variables are **optional** unless noted; defaults target a pure-local Apple Silicon setup. In Docker, set them in `docker/.env` (copied from `docker/.env.example`). The worker reaches host services via `host.docker.internal`.

### Worker / core

| Variable | Default | Purpose |
|---|---|---|
| `GUTENBERG_ROOT` | `/workspace/gutenberg` | Path to the corpus bundle inside the container. |
| `EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | Sentence-transformer model for query embedding. |
| `HANDLER_SECRET` | *(empty)* | If set, every request must include `{"secret": "<value>"}`. |
| `SYNTH_MAX_K` | `12` | Max passages fed to the synthesizer per request. |
| `KGRAG_ENDPOINT` | `http://localhost:8000` | Chat UI → worker URL (set to `http://gutenberg-worker:8000` in compose). |
| `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` | `1` (set in Dockerfile) | Force offline mode — no HuggingFace calls at runtime. |

### Text synthesis

Provider is chosen per-request (chat UI Provider dropdown / `"backend"` field). The default backend when none is specified is read from `SYNTH_BACKEND`. The generic `SYNTH_*` variables override the provider-specific ones.

| Variable | Default | Applies to | Purpose |
|---|---|---|---|
| `SYNTH_BACKEND` | `omlx` | all | Default backend: `omlx`, `ollama`, or `openai`. |
| `SYNTH_ENDPOINT` | — | omlx | Endpoint override (falls back to `VLLM_ENDPOINT_URL`). |
| `SYNTH_API_KEY` | — | omlx, openai | Key override (falls back to `VLLM_API_KEY` / `OPENAI_API_KEY`). |
| `SYNTH_MODEL` | — | omlx | Model override (falls back to `VLLM_MODEL`). |
| `VLLM_ENDPOINT_URL` | `http://localhost:8080/v1` | omlx | oMLX / vLLM OpenAI-compatible endpoint. |
| `VLLM_API_KEY` | — | omlx | Bearer token for oMLX (omit for Ollama). |
| `VLLM_MODEL` | `Qwen3-4B-Instruct-2507-MLX-8bit` | omlx | oMLX model ID. |
| `OLLAMA_ENDPOINT` | `http://localhost:11434/v1` | ollama | Ollama OpenAI-compatible endpoint (no key needed). |
| `OPENAI_API_KEY` | — | openai | **Required for the OpenAI path.** Endpoint defaults to `https://api.openai.com/v1`, model to `gpt-4o-mini`. |

### Image generation

Backend is chosen by `IMAGE_BACKEND`. `mflux-serve` (default) and `mflux-local` are Apple-Silicon-only; `openai` works anywhere.

| Variable | Default | Applies to | Purpose |
|---|---|---|---|
| `IMAGE_BACKEND` | `mflux-serve` | all | `mflux-serve` (HTTP), `mflux-local` (in-process MLX), or `openai`. |
| `IMAGE_ENDPOINT` | `http://localhost:8090` | mflux-serve | mflux-serve base URL (compose maps `GUTENKG_IMAGE_ENDPOINT` → this). |
| `GUTENKG_IMAGE_ENDPOINT` | `http://localhost:8090` | mflux-serve | Canonical endpoint var used by `gutenkg imagine` and compose. |
| `IMAGE_MODEL` / `GUTENKG_IMAGE_MODEL` | `flux2-klein-4b` (serve) · `mlx-community/flux2-klein-4b-4bit` (local) | mflux | Image model override. |
| `IMAGE_STEPS` / `GUTENKG_IMAGE_STEPS` | `4` | mflux | Inference steps (ignored for OpenAI). |
| `IMAGE_API_KEY` | — | openai | Key override (falls back to `OPENAI_API_KEY`). |
| `OPENAI_API_KEY` | — | openai | Key for `gpt-image-1` when `IMAGE_BACKEND=openai`. |

### `gutenkg imagine` CLI (local Apple Silicon path)

The local `gutenkg imagine` command (outside Docker) reads its own `GUTENKG_*` variables for the VLM rewrite + FLUX generation pipeline:

| Variable | Default | Purpose |
|---|---|---|
| `GUTENKG_VLM_ENDPOINT` | `http://localhost:8080/v1` | oMLX endpoint for the VLM prose→scene rewrite. |
| `GUTENKG_VLM_MODEL` | `Qwen3-4B-Instruct-2507-MLX-8bit` | VLM model ID. |
| `GUTENKG_IMAGE_ENDPOINT` | *(empty → in-process)* | If set, proxy generation to a running image server; else generate locally. |
| `GUTENKG_IMAGE_MODEL` | `mlx-community/flux2-klein-4b-4bit` | Local FLUX model. |
| `GUTENKG_IMAGE_STEPS` | `4` | Local FLUX inference steps. |

### Image server (`make image-server` / `docker/image_server.py`)

| Variable | Default | Purpose |
|---|---|---|
| `MFLUX_SERVER_HOST` | `0.0.0.0` | Bind host for the FLUX server. |
| `MFLUX_SERVER_PORT` | `8090` | Bind port. |
| `IMAGE_OUTPUT_DIR` | `/tmp/gutenberg_images` | Where rendered images are written. |
| `IMAGE_PRELOAD` | `0` | Set to `1` to load the FLUX model at startup instead of first request. |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker compose` not found | Install Docker Compose v2 (bundled with recent Docker Desktop / Engine). The legacy `docker-compose` v1 is not used. |
| `make build` fails on `COPY bundles/gutenberg-all/` | Run `make build-corpus` first — the bundle must exist before the image build. |
| Synthesis returns errors / empty | Confirm your LLM server is running and `VLLM_ENDPOINT_URL` / `OLLAMA_ENDPOINT` in `docker/.env` is reachable from the container. |
| Worker can't reach host LLM | Use `host.docker.internal`, not `localhost`, in the endpoint URLs. The compose file adds the required `extra_hosts` entry. |
| Slow first query in Docker | The embedding model is pre-downloaded at build time and runs offline (`HF_HUB_OFFLINE=1`); the first request still warms the model into memory. |
| Image generation unavailable on Linux/Windows | FLUX.2-Klein / MLX image generation is Apple-Silicon-only. Query and synthesis work everywhere. |

---

*Author: Eric G. Suchanek, PhD · Flux-Frontiers, Liberty TWP, OH*
