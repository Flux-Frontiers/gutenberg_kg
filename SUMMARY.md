# Work Summary — Apple `container` Runtime Support

_Branch: `claude/gutenberg-apple-containers-w43ed9`. Date: 2026-07-22._

This documents the assessment and implementation of running the GutenbergKG
local stack (worker + chat UI) on **Apple's native `container` CLI** instead
of Docker Desktop, shipped as an opt-in runtime behind a single Makefile
variable. The full assessment with sources lives in
[`docs/APPLE_CONTAINERS.md`](docs/APPLE_CONTAINERS.md).

---

## TL;DR

1. **It works, and Gutenberg is an unusually good fit.** The base image
   (`egsuchanek/kgrag-worker:latest`) is already linux/arm64 — native in
   Apple's per-container VMs, no emulation. Both Dockerfiles are plain
   BuildKit-compatible and build unchanged. Crucially, Apple's runtime
   resolves **`host.docker.internal` natively** (since `container` 0.9.0,
   Feb 2026), so every host-service default — oMLX :8080, Ollama :11434,
   FLUX/SDXL :8090/:8091 — works verbatim.
2. **Shipped as `RUNTIME=apple`**, not a replacement:
   `make build|run|chat|up|down|logs|clean RUNTIME=apple`. Docker/compose
   remains the default path and is untouched.
3. **One real bug found and fixed**: the chat UI detected "inside a
   container" via `/.dockerenv`, which only Docker creates — under Apple's
   runtime it would have silently picked `localhost` instead of
   `host.docker.internal`. Both images now bake `GUTENKG_IN_CONTAINER=1`
   and the UI checks it.
4. **RunPod stays on Docker** — it targets x86_64 cloud; cross-building the
   torch stack under emulation buys nothing.
5. **Hard floor: macOS 26** for the chat profile (container↔container
   networking). On macOS 15 only the worker-alone path works.

---

## Why this is viable now (assessment findings)

Recorded so we don't re-litigate:

- **Arch**: verified via the Docker Hub registry manifest that the base
  image is published **arm64-only** — Apple Silicon native, no Rosetta.
- **Host access**: `container` 0.9.0 added `host.docker.internal`
  resolution; this removed what looked like the biggest migration cost
  (every endpoint default in `docker-compose.yml` and `docker/.env.example`
  leans on that hostname).
- **No compose exists** (Apple ships none as of v1.1.x). Not a blocker
  here because the Makefile is already the only entry point — compose was
  an implementation detail behind `make`, so the swap is invisible to the
  workflow.
- **Per-container VMs change the memory model**: Docker Desktop shared one
  big VM; Apple gives each container its own, with small defaults that
  would OOM the worker (torch + bge-small + 696K-node graph + LanceDB).
  Memory must be explicit — but it's a lazy upper bound, not a
  reservation, so `--memory 8g` doesn't pin 8 GB.
- **No restart policies** — compose's `restart: unless-stopped` has no
  equivalent; after a reboot the worker stays down until `make run`.
- **CI never touches Docker** — GitHub Actions needed no changes.

## What shipped (by file)

| File | Change |
|---|---|
| `Makefile` | `RUNTIME ?= docker` switch. Apple branch replaces compose with explicit `container run`: worker `--memory 8g --cpus 6`, chat `--memory 4g` (all overridable: `WORKER_MEM`, `WORKER_CPUS`, `CHAT_MEM`); sources `docker/.env` before launch to mirror compose's auto-loading; `make run` is idempotent (a warm worker with its loaded index is left alone); chat reaches the worker via the worker VM's IP pulled from `container inspect`. |
| `serve/Chat.py`, `serve/pages/1_Browse.py` | Container detection: `/.dockerenv` **or** `GUTENKG_IN_CONTAINER` env var. |
| `docker/Dockerfile`, `docker/Dockerfile.sqlite` | `ENV GUTENKG_IN_CONTAINER=1` (harmless under Docker). |
| `README.md` | Runtime-choice section under "Build and run"; requirements table row updated. |
| `docs/APPLE_CONTAINERS.md` | New: "Using it" runbook + the full original assessment. |
| `CHANGELOG.md` | Unreleased entries (Added/Changed). |

## Using it

On the Mac (macOS 26, `brew install --cask container`):

```bash
container system start        # once per boot
make build RUNTIME=apple      # container build -f docker/Dockerfile
make up    RUNTIME=apple      # worker :8000 + chat :8501 + FLUX :8090
make query Q="What is justice according to Plato?"
make down  RUNTIME=apple
```

Everything else — `docker/.env`, oMLX/Ollama/OpenAI synthesis, image
backends (`IMAGE_BACKEND=sdxl`), the chat UI — behaves identically to the
Docker path.

## Verification status & first-run watch items

Developed on a Linux box, so the Apple runtime itself could not be
executed. Verified here: all seven targets dry-run cleanly under **both**
runtimes (`make -n`), the generated shell is correct, edited Python
byte-compiles, and the Docker path's dry-run output is unchanged.

The real smoke test is on the Mac. Two most-likely first-contact issues:

1. **Builder VM headroom** — the multi-GB bundle `COPY` may need
   `container builder start --cpus 4 --memory 8g` before `make build`.
2. **Worker-IP parsing** — the `chat` target regex-parses the `address`
   field out of `container inspect` JSON. If chat can't reach the worker,
   that line in the Makefile is the first place to look (fallback: set
   `KGRAG_ENDPOINT` by hand).

## Deliberately out of scope

- `runpod/` build pipeline (x86_64 — stays Docker).
- Publishing `egsuchanek/kgrag-worker` itself (upstream of this repo;
  `container build` + `container registry push` could take it over later).
- DNS-based container naming (`container system dns create`) — IP
  injection was chosen instead to avoid a sudo setup step.
- Auto-restart on boot — if wanted later, a launchd agent running
  `container start gutenberg-worker` is the idiomatic Mac answer.

---

_Previous summary (retrieval quality / corpus hygiene / build performance,
branch `fix/build-corpus-memory`, 2026-06-17) is preserved in git history._
