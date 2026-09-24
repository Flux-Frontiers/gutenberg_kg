# Installation

This guide covers everything needed to install, build, and run GutenbergKG — both the **CLI workflow** (build and query the corpus directly) and the **Docker workflow** (run the corpus behind a query worker and chat UI).

> **TL;DR** — For the CLI: install Poetry, `poetry install --extras "kgdeps viz viz3d mcp"`, `gutenkg ingest --force-build`. For Docker: `make build-corpus && make build && make run`. Querying needs no LLM; synthesis and image generation need a local LLM (oMLX or Ollama).

---

## Requirements

| | Required for | Version | Notes |
|---|---|---|---|
| **Python** | everything | 3.12 or 3.13 (`>=3.12,<3.14`) | 3.14 not yet supported |
| **[Poetry](https://python-poetry.org/)** | CLI workflow | 2.x | dependency management + virtual env |
| **[GNU Make](https://www.gnu.org/software/make/)** | build/run targets | any | drives `build-corpus`, `build`, `run`, `chat`, `up` |
| **[Docker](https://docs.docker.com/get-docker/)** | container workflow | Engine 24+, Compose v2 | `docker compose` (v2 syntax, not `docker-compose`) — or Apple's [`container`](https://github.com/apple/container) CLI on macOS 26 via `make … RUNTIME=apple` (see [APPLE_CONTAINERS.md](APPLE_CONTAINERS.md)) |
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
poetry install --extras "kgdeps viz viz3d mcp"
gutenkg --help
```

That set is the **recommended default** — everything except dev tooling (KG integrations, visualisation, and the MCP server). A bare `poetry install` gives you the core runtime only; layer in individual extras if you want a leaner install:

| Extra | Installs | Install with |
|---|---|---|
| `kgdeps` | kg-rag (doc-kg and diary-kg are core dependencies, always installed) | `poetry install --extras kgdeps` |
| `viz` | plotly (2-D growth timeline) | `poetry install --extras viz` |
| `viz3d` | pyvista, PyQt5, kgmodule-utils, quiltwright (3-D visualiser + light-field quilts) | `poetry install --extras viz3d` |
| `mcp` | fastmcp, structlog (MCP server) | `poetry install --extras mcp` |
| `chat` | streamlit, httpx, watchdog (reading-room UI) | `poetry install --extras chat` |
| `image` | fastapi, uvicorn, pydantic (image service) | `poetry install --extras image` |
| `pov` | quiltwright povgen, kgmodule-utils NumPy-only geometry (analytic POV-Ray output, `gutenkg pov`) — deliberately no PyVista/Qt/GL, so a headless box can install it alone | `poetry install --extras pov` |
| *(none)* | core runtime only | `poetry install` |
| *(everything)* | every extra above | `poetry install --all-extras` |

Dev tooling (pytest, ruff, ty, pre-commit) is **not an extra** — it lives in the *optional* Poetry `dev` group, so it stays out of the published wheel metadata and a bare `poetry install` stays core-runtime-only. The same is true of `pycode-kg`, in the optional `kg` group: this repo *runs* the `pycodekg` CLI and its MCP server but imports neither, so it is maintainer tooling rather than a feature of the package. There is no `.[dev]` to pip-install; development needs Poetry. Contributors who want the test/lint toolchain, matching every extra CI's own jobs install:

```bash
poetry install --with dev,kg --extras "kgdeps viz viz3d mcp image pov"   # or --with dev,kg --all-extras
pre-commit install
```

`--with dev` alone covers `ruff` and `ty`, but two extras are load-bearing for what the local `ty`/`pytest` pre-commit hooks actually check, and dropping either silently narrows what runs locally versus what CI runs on the same command:

- **`image`** — `tests/test_sdxl_server.py` imports fastapi/pydantic at module level, so without it `pytest` aborts during *collection* rather than skipping. CI's test job runs `poetry install --with dev --extras image --extras pov` for exactly this.
- **`pov`** — `tests/test_povscene.py` imports `gutenberg_kg.povscene`, which imports `quiltwright.povgen` at module scope; same collection-failure shape as `image` if it is missing. It matters for `ty` too, not just `pytest`: CI's type-check job installs `--extras pov` specifically because an unresolved import is not a type error, so `ty` reported "All checks passed" on `swept_scene(instance_index=<ndarray>)` sitting against a `Sequence[int]` parameter until the extra made the signature visible. Installing `viz3d` already pulls `quiltwright` transitively and happens to satisfy this too — but `pov` is what CI actually names, and a leaner setup that skips `viz3d` (a real path: `pov` explicitly needs no PyVista/Qt/GL) needs it named explicitly.

The other extras only turn optional-feature tests from skipped into run.

> **Watch for a stale venv.** Because the `dev` group is *optional*, a plain `poetry install` in an existing checkout leaves `.venv` without pytest/ruff/ty — and `poetry run pytest` then silently falls through to whatever `pytest` is on your `PATH`, which fails with confusing `ModuleNotFoundError`s. `ls .venv/bin/pytest` to check; re-run the command above to fix.

> **Note** — there are no `full` / `all` aggregate extras. They existed until they were found to be the reason `poetry lock` took over eight minutes: re-listing a package inside an aggregate makes it a second declaration under different markers, and poetry resolves that by throwing away the whole resolution and restarting. Dropping them took a lock from 503s to 11s. Name the extras you want, or use `--all-extras`.

Prefer a plain venv + pip? The same extras work with pip:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[kgdeps,viz,viz3d,mcp]"      # dev and kg tooling are poetry-only: poetry install --with dev,kg
```

### 2. Build the knowledge graph

The graph indices are **not committed to git** — they're local build artifacts. Rebuild them from the source Markdown:

```bash
gutenkg ingest --force-build
```

> **Expect 30–45 minutes** for a full rebuild on Apple Silicon (M5 Max ~30 min, Mac mini M4 ~45 min). Individual genres take 30 seconds to 5 minutes.

### 3. Query

```bash
# Semantic search across the locally ingested corpus
gutenkg query "the nature of justice"

# Semantic search within a local genre corpus
gutenkg query "characters who seek revenge" --corpus gutenberg-russian-literature
```

The full command reference is in [`CHEATSHEET.md`](CHEATSHEET.md); pipeline internals are in [`DOWNLOAD_PIPELINE.md`](DOWNLOAD_PIPELINE.md).

---

## Docker workflow

The Docker image extends a KGRAG worker base image with a pre-built corpus bundle (DocKG + DiaryKG indices) baked in. Because the bundle is generated locally, you need the CLI installed first.

### 1. Install the CLI and build the bundle

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
cd gutenberg_kg
poetry install --extras "kgdeps viz viz3d mcp"

make build-corpus      # builds DiaryKG indices, then bundles DocKG + diaries (~24 min)
```

`make build-corpus` runs `make build-diaries` first (a prerequisite), then `gutenkg build-corpus`, producing `bundles/gutenberg-all/` (gitignored). `make build-diaries` in turn depends on `make chunk-diaries`, which reconstructs each diary's git-ignored `.diary/` chunk corpus from the committed `<book>.md` — so a fresh clone needs no extra steps. (The chunker uses spaCy; if prompted, run `python -m spacy download en_core_web_sm` once.)

### 2. Build the image and bring up the stack

```bash
make build             # docker build -f docker/Dockerfile -t corpus-gutenberg:latest .
make up                # worker (:8000) + chat UI (:8501) + an image server
```

`make up` picks the image backend that this host can actually run: **FLUX** on
`:8090` where mflux is supported (Apple Silicon, or a CUDA 13 Linux box), and
**SDXL-Lightning** on `:8091` everywhere else. Override with
`make up IMAGE_BACKEND=flux|sdxl`. Image generation is optional either way — if
the server fails to start, the worker and chat UI stay up and only the chat UI's
*Render response* button is affected.

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
| `make chunk-diaries` | re-chunk `.diary/` from committed `<book>.md` (always `--force`, so a parser change propagates) |
| `make build-diaries` | rebuild `.diarykg/` indices (depends on `chunk-diaries`; prerequisite for `build-corpus`) |
| `make build-corpus` | rebuild the DocKG + diary bundle (~24 min) |
| `make build` | build the Docker image (bakes the bundle in) |
| `make run` | start the worker on `:8000` |
| `make chat` | start worker + chat UI on `:8501` |
| `make image-server` | start the local FLUX image server on `:8090` (isolated `.venv-image`; needs mflux — see below) |
| `make sdxl-server` | start the local SDXL-Lightning image server on `:8091` (isolated `.venv-sdxl`; runs anywhere) |
| `make sdxl-fetch` | pre-download the SDXL weights (~7 GB) without starting the server |
| `make up` | start everything (worker + chat + whichever image server this host supports) |
| `make query Q="…"` | fire a one-shot query against the running worker |
| `make logs` | follow worker logs |
| `make stop` | shut everything down |
| `make kill` | force-remove the worker and chat containers under both Docker and Apple `container`, plus the image servers |
| `make down-all` | `make kill`, then stop Apple's container services and quit Docker Desktop |
| `make clean` | remove the Docker image |

---

## Connecting a local LLM (optional)

Synthesis and image generation reach a host LLM. From inside Docker, the host is `host.docker.internal`.

### oMLX (Apple Silicon, recommended)

Start oMLX on **port 8080** (8000 is taken by the worker):

```bash
omlx serve --port 8080                  # serves the models in ~/.omlx/models
```

Or set the port in the oMLX app. Under `RUNTIME=apple` the containers reach
the host over vmnet, so oMLX must listen on `0.0.0.0` (`--host 0.0.0.0`), not
`127.0.0.1`.

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

If oMLX has API key verification on and this key is empty or wrong, oMLX
answers 401 and synthesis fails. Restart the worker (`make down && make up`)
after changing `docker/.env`.

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
- **Image generation** — pick **OpenAI** in the chat UI's or the app's **Image backend** picker, or leave it on **Auto**, which uses OpenAI images whenever the provider is OpenAI and the local image server for oMLX or Ollama. To make OpenAI the worker's default for every client, the iOS and macOS apps included, set `WORKER_IMAGE_BACKEND=openai` in `docker/.env` and restart the worker. No `make image-server` needed.

```bash
# docker/.env  — OpenAI for both text synthesis and image generation
OPENAI_API_KEY=sk-...
WORKER_IMAGE_BACKEND=openai   # route images to gpt-image-1 (default is local mflux-serve)
# Optional override:
IMAGE_MODEL=gpt-image-1       # image model (default gpt-image-1)
```

The text model is chosen per request: pick it in the chat UI's model list, or
send `"model"` to the worker.

With `WORKER_IMAGE_BACKEND=openai`, every client that does not name a backend
gets `gpt-image-1`, and OpenAI bills each image. A 1024x1024 image takes about
50 s. To go back to the local server, set `WORKER_IMAGE_BACKEND=mflux-serve` and
recreate the worker (see [API keys and `docker/.env`](#api-keys-and-dockerenv)).

Because OpenAI is a cloud API, it is the **one path that needs nothing installed locally at all** — no Apple Silicon, no oMLX, no local image server. It is not the only cross-platform option, though: Ollama covers text synthesis on Linux and Windows, and SDXL-Lightning covers images (below).

### Image generation (local)

Two local servers, both isolated in their own venv so their dependencies never touch the main Poetry environment:

| Server | Port | Start with | Runs on |
|---|---|---|---|
| FLUX.2 (mflux) | `8090` | `make image-server` | Apple Silicon, or Linux with CUDA 13 — mflux needs `mlx`, and there is no Windows wheel |
| SDXL-Lightning (diffusers) | `8091` | `make sdxl-server` | anywhere — `sdxl_server` resolves `cuda → mps → cpu`, so it works on CPU too, just slowly |

`make up` picks for you: FLUX where mflux is supported, SDXL everywhere else. Force one with `make up IMAGE_BACKEND=flux` or `IMAGE_BACKEND=sdxl`; asking for FLUX on a host that cannot run it now fails with a message naming the requirement instead of a pip resolution error.

**SDXL downloads weights on first run** — SDXL base, the fp16-fix VAE and the Lightning UNet come to roughly 7 GB, cached under `~/.cache/huggingface`. Run `make sdxl-fetch` to get that out of the way before starting the stack. Once cached, `SDXL_OFFLINE=1` makes the server refuse network access entirely.

Point the worker at whichever is running via `GUTENKG_IMAGE_ENDPOINT` in `docker/.env` (`http://host.docker.internal:8090` for FLUX, `:8091` for SDXL) — `make up` sets this automatically — or leave it blank to disable image rendering. See [`CHEATSHEET.md § Corpus-Grounded Image Generation`](CHEATSHEET.md).

> **Two different `IMAGE_BACKEND`s.** As a *Make* variable
> (`make up IMAGE_BACKEND=sdxl`) it selects which local image **server** to
> start — `flux` or `sdxl`. Inside the worker, `IMAGE_BACKEND` is the backend
> it generates through — `mflux-serve`, `mflux-local`, or `openai`. Because
> `make` exports a command-line variable, `docker/.env` sets the worker's value
> as `WORKER_IMAGE_BACKEND`, and compose and `RUNTIME=apple` pass it into the
> container as `IMAGE_BACKEND`.

---

## API keys and `docker/.env`

Keys (`OPENAI_API_KEY`, `VLLM_API_KEY`, `IMAGE_API_KEY`, `HANDLER_SECRET`) go
in `docker/.env`, which git ignores. `docker/.env.example` is the tracked
template and holds placeholders only.

**Keys are applied when the container starts, not when the image is built.**
Compose's `environment:` block and the `RUNTIME=apple` recipe's `-e` flags read
`docker/.env` at start. The image build copies only `pyproject.toml`,
`README.md`, `src/gutenberg_kg/` and the corpus bundle, and the Hugging Face
token reaches the build as a BuildKit secret, which is not written to any layer.
An image from `make build` holds no keys and is safe to push to a registry.

Two ways a key can still leak:

- `docker commit` of a running container makes an image that includes that
  container's environment. Push only images from `make build`.
- `docker inspect` / `container inspect` of a running container prints its
  environment, keys included.

**After editing `docker/.env`, recreate the worker.** No rebuild is needed:

```bash
docker compose -f docker/docker-compose.yml up -d worker            # Docker
container delete -f gutenberg-worker && make run RUNTIME=apple      # Apple
```

`make run RUNTIME=apple` leaves a running worker alone, so without the
`delete` it keeps the old environment. A rebuild (`make build`) is only needed
when the code or the corpus bundle changes.

---

## Serving phones and other devices on your LAN

The iOS and macOS apps talk only to the worker; the worker calls the LLM and
image servers on the Mac. Set the app's worker URL to
`http://<your-mac>.local:8000` or `http://<LAN-IP>:8000`. `localhost` on a
phone is the phone.

Checklist on the Mac that runs the worker:

1. **One container runtime.** With Docker Desktop and Apple's container
   services both running, other devices can ping the Mac but every TCP
   connection to it hangs. `make run`, `make chat` and `make up` refuse to
   start in that state; `make down-all` stops both runtimes.
2. **Host services listen on `0.0.0.0`.** Under `RUNTIME=apple` the containers
   reach oMLX (`:8080`), Ollama (`:11434`) and the image server (`:8090`) over
   vmnet, which a `127.0.0.1` listener does not accept.
3. **The oMLX key matches.** If oMLX verifies API keys, `VLLM_API_KEY` must be
   its key; otherwise synthesis fails with 401.
4. **No stale VPN DNS.** A VPN that was uninstalled or stopped (Tailscale, for
   one) can leave its DNS server set on the Wi-Fi service, which slows or
   breaks name lookups. Check with `networksetup -getdnsservers Wi-Fi`; clear
   with `sudo networksetup -setdnsservers Wi-Fi Empty`.

From the phone, open `http://<LAN-IP>:8000/health` in Safari. A
`{"detail":"Not Found"}` page means the network path works and the problem is
in the app; turn on the app's Local Network access in iOS Settings. A page that
never loads means the network path is broken; work through the checklist.

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

Backend is chosen by `IMAGE_BACKEND` inside the worker, set from `WORKER_IMAGE_BACKEND` in `docker/.env`. A request's `image_backend` (the chat UI's OpenAI provider sends `openai`) overrides it. `mflux-serve` (default) and `mflux-local` are Apple-Silicon-only; `openai` works anywhere.

| Variable | Default | Applies to | Purpose |
|---|---|---|---|
| `WORKER_IMAGE_BACKEND` → `IMAGE_BACKEND` | `mflux-serve` | all | `mflux-serve` (HTTP), `mflux-local` (in-process MLX), or `openai`. |
| `IMAGE_ENDPOINT` | `http://localhost:8090` | mflux-serve | mflux-serve base URL (compose maps `GUTENKG_IMAGE_ENDPOINT` → this). |
| `GUTENKG_IMAGE_ENDPOINT` | `http://localhost:8090` | mflux-serve | Canonical endpoint var used by `gutenkg imagine` and compose. |
| `IMAGE_MODEL` / `GUTENKG_IMAGE_MODEL` | `flux2-klein-4b` (serve) · `mlx-community/flux2-klein-4b-4bit` (local) | mflux | Image model override. |
| `IMAGE_STEPS` / `GUTENKG_IMAGE_STEPS` | `4` | mflux | Inference steps (ignored for OpenAI). |
| `IMAGE_API_KEY` | — | openai | Key override (falls back to `OPENAI_API_KEY`). |
| `OPENAI_API_KEY` | — | openai | Key for `gpt-image-1` when the backend is `openai`. |

### `gutenkg imagine` CLI (local Apple Silicon path)

The local `gutenkg imagine` command (outside Docker) reads its own `GUTENKG_*` variables for the VLM rewrite + FLUX generation pipeline:

| Variable | Default | Purpose |
|---|---|---|
| `GUTENKG_VLM_ENDPOINT` | `http://localhost:8080/v1` | oMLX endpoint for the VLM prose→scene rewrite. |
| `GUTENKG_VLM_MODEL` | `Qwen3-4B-Instruct-2507-MLX-8bit` | VLM model ID. |
| `GUTENKG_IMAGE_ENDPOINT` | *(empty: probe ports 8090, 8091)* | Image server to call. The CLI and the MCP tools never generate in-process; with no server answering they stop with "No image server found". |
| `GUTENKG_IMAGE_MODEL` | `mlx-community/flux2-klein-4b-4bit` | Local FLUX model. |
| `GUTENKG_IMAGE_STEPS` | `4` | Local FLUX inference steps. |

### Image server (`make image-server` / `gutenkg-image-server`)

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
| Image generation unavailable on Linux/Windows | FLUX.2-Klein / MLX image generation is Apple-Silicon-only. Use SDXL-Lightning (`make sdxl-server`) or OpenAI (`WORKER_IMAGE_BACKEND=openai`). |
| Changed `docker/.env`, nothing changed | Recreate the worker; see [API keys and `docker/.env`](#api-keys-and-dockerenv). |
| Synthesis fails with 401 from oMLX | `VLLM_API_KEY` is empty or wrong while oMLX verifies keys. |
| Phone or another Mac cannot reach the worker | See [Serving phones and other devices on your LAN](#serving-phones-and-other-devices-on-your-lan). |
| `make up` stops with "is running. With both container runtimes up" | The other runtime is running. `make down-all`, then `make up`. |
| Every `docker` command fails with HTTP 500 | Docker Desktop's backend outlived its engine. Quit Docker Desktop, `pkill -x com.docker.backend`, reopen it. |

---

*Author: Eric G. Suchanek, PhD · Flux-Frontiers, Liberty TWP, OH*
