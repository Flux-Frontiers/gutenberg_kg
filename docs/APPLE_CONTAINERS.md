# Apple `container` as a Docker alternative for GutenbergKG

*Status: implemented as an alternative runtime — `make <target> RUNTIME=apple` —
and verified working on Apple Silicon / macOS 26 (2026-07-22). Sections below
record the original assessment; the "Using it" section describes what shipped.*

## Using it

Requirements: Apple Silicon, macOS 26 (Tahoe), and Apple's
[`container`](https://github.com/apple/container) tool v1.0+
(`brew install container` or the pkg from GitHub releases).

```sh
make setup RUNTIME=apple         # clean machine: installs the CLI (Homebrew)
                                 # + `container system start`; build/run/chat
                                 # depend on it, so this is optional
make build RUNTIME=apple         # container build -f docker/Dockerfile
make run   RUNTIME=apple         # worker on http://localhost:8000
make chat  RUNTIME=apple         # worker + chat UI on http://localhost:8501
make up    RUNTIME=apple         # everything incl. FLUX image server
make logs  RUNTIME=apple
make down  RUNTIME=apple
```

Notes:

- **Memory/CPU are per-container VM flags**, defaulting to 2g/6 CPUs for the
  worker and 512m for chat. Override like `make run RUNTIME=apple WORKER_MEM=4g`
  if a larger corpus or heavier query load needs headroom. These follow the
  same shape observed in the sibling `corpus_pepys` repo (same Makefile
  pattern, same worker/chat container shape): worker needs ~2g, chat ~512m —
  both a fraction of the old 8g/4g guesses. Memory is a lazy upper bound, not
  a reservation, so this doesn't pin RAM, just caps it. If a larger corpus
  ever pushes the worker past this cap (OOM, or `container stats` showing it
  pinned at the ceiling under load), re-measure with:
  1. `make up RUNTIME=apple` (or `run` + `chat-container`) with the current
     defaults.
  2. In one shell, poll `container stats --no-stream <worker-name> <chat-name>`
     every ~1s through cold start (model/index load is usually the peak) and
     while idle, to get a baseline.
  3. In another shell, fire a burst of concurrent real queries at the worker
     (e.g. several parallel `curl -X POST http://localhost:8000/runsync ...`
     with a generous `k`) while still polling `container stats`, to find the
     load peak.
  4. Repeat step 3 with `chat` too if there's an easy way to drive it
     (Streamlit UI interactions, or whatever the chat container actually does
     under load).
  5. Set `WORKER_MEM`/`CHAT_MEM` in the `Makefile` to roughly 2x the observed
     peak (round up to a clean value), re-verify `make up RUNTIME=apple` still
     works end-to-end at the new caps, and update the rationale comment here
     and in the `Makefile` with the measured numbers.
- **`docker/.env` still works** — the Make targets source it before
  `container run`, mirroring compose's automatic loading.
- **Ports are published to the host (`localhost` works).** Apple's `container`
  gained Docker-style port publishing in CLI **v1.1.0**, so `make run/chat/up`
  forward `8000`/`8501` to the host and print `http://localhost:PORT` — same as
  the Docker path. (Older CLIs had no `--publish` and forced vmnet-IP addressing;
  if `container run --help` shows no `-p/--publish`, `make setup RUNTIME=apple`
  upgrades it.)
- **Host services are reached at the vmnet gateway, not `host.docker.internal`.**
  Contrary to the 0.9 "resolves natively" claim, that hostname does *not*
  resolve inside the containers on the runtime tested here (still true on
  v1.1.0), so the Apple targets point oMLX/Ollama/image-server endpoints at the
  gateway IP (`APPLE_HOST_GW`, default `192.168.64.1`). Override per-machine if
  your subnet differs (`container inspect gutenberg-worker` → `networks[].gateway`).
  **The host service must also bind `0.0.0.0`, not `127.0.0.1`** — a
  loopback-only listener refuses vmnet connections. Start oMLX with
  `--host 0.0.0.0` (likewise Ollama / the image server).
- **chat→worker traffic** goes through the vmnet gateway: the worker's `8000`
  is published to the host, and the chat container reaches it at
  `http://$(APPLE_HOST_GW):8000`. No container-to-container vmnet needed, so
  this no longer hard-requires macOS 26 for the chat↔worker hop.
- **No restart policy** — unlike compose's `restart: unless-stopped`, the
  worker stays down after a reboot until you `make run RUNTIME=apple` again.
- **`make run` is idempotent**: a running worker is left alone; a stopped or
  stale container is replaced.
- The RunPod pipeline (`runpod/`) is untouched and still requires Docker.

---

## Original assessment (2026-07-22)

Apple's [`container`](https://github.com/apple/container) tool (v1.1.x as of
July 2026) runs OCI Linux containers natively on Apple Silicon, one
lightweight VM per container, with no Docker Desktop. This document assesses
what it would take for GutenbergKG to use it instead of Docker for the local
worker + chat stack.

**Verdict: feasible with roughly half a day of work.** The images build and
run unchanged; the work is replacing `docker compose` conveniences (the
orchestration in the Makefile) and two small code/config fixes. The RunPod
deployment pipeline should stay on Docker.

---

## Current Docker surface

| Piece | What it does | Apple `container` fit |
|---|---|---|
| `docker/Dockerfile` | corpus image from `python:3.12-slim` (self-contained, sqlite-vec), bakes bundle | ✅ builds as-is |
| `docker/docker-compose.yml` | worker + chat services, profiles, ports, env, restart | ⚠️ no compose — replace with `container run` targets |
| `Makefile` (`run`/`chat`/`up`/`down`/`logs`/`clean`) | drives compose | ⚠️ rewrite ~6 targets |
| `host.docker.internal` (compose env, `docker/.env.example`) | reach oMLX :8080, Ollama :11434, mflux :8090/:8091 on the host | ⚠️ hostname does NOT resolve in-container on the tested runtime — Apple targets use the vmnet gateway IP (`APPLE_HOST_GW`, default 192.168.64.1); host services must bind 0.0.0.0 |
| `/.dockerenv` check in `serve/Chat.py` + `serve/pages/1_Browse.py` | detect "inside container" to pick `host.docker.internal` vs `localhost` | ❌ Apple VMs don't create `/.dockerenv` — needs a one-line fix |
| `runpod/` (Dockerfile, build_image.sh) | x86 serverless image for RunPod cloud | 🚫 keep on Docker (amd64 target) |
| GitHub Actions CI | — | ✅ no Docker usage at all |

## What works out of the box

**The base image is already linux/arm64.** `python:3.12-slim` is a multi-arch
official image, so the arm64 variant is selected automatically and runs
natively in Apple's VMs — no Rosetta, no emulation penalty on the
torch/embedding stack. Registry pull/push (`container registry login`) speaks
standard OCI, so Docker Hub keeps working.

**The Dockerfile is a plain BuildKit-compatible Dockerfile.**
`container build` runs a BuildKit-based builder in its own VM and handles
everything the file uses: `FROM`, `ARG`/`--build-arg`, `RUN` heredocs
(`python - <<'EOF'`), multi-file `COPY`, `ENV`, `CMD`. Expected commands:

```sh
container system start                       # once per boot
container build -f docker/Dockerfile -t corpus-gutenberg:latest .
```

The multi-GB bundle `COPY` works; give the builder VM headroom first
(`container builder start --cpus 4 --memory 8g`) or the default builder may
struggle with the layer.

**Host services are reached at the vmnet gateway.** The 0.9.0 release notes
claim containers resolve `host.docker.internal` to the host, but on the
runtime tested here that name does *not* resolve in-container (DNS returns
`Name or service not known`; the containers' only nameserver is the gateway,
which doesn't answer it). Containers *do* always reach the host at the vmnet
gateway (192.168.64.1 on the default subnet), so the Apple Make targets point
oMLX :8080, Ollama :11434, and the FLUX/SDXL image servers :8090/:8091 at that
IP (`APPLE_HOST_GW`) rather than the docker hostname. Two caveats: the host
service must bind `0.0.0.0` (a `127.0.0.1`-only listener refuses vmnet
connections — verify from the host with `curl http://192.168.64.1:8080/v1/models`
before blaming the container), and the gateway IP can differ per machine
(override `APPLE_HOST_GW`).

**Ports and volumes.** Apple's `container` has **no** Docker-style port
publishing — there is no `--publish`/`-p` (passing it errors with
`Unknown option '--publish'`). Instead each container gets its own routable
vmnet IP (`container inspect`) that the host hits directly, so the Makefile
addresses the worker and chat UI by IP (each target prints the URL). Bind
mounts (`--volume`) exist,
which opens a nice option Docker made painful: mount the bundle instead of
baking 3–4 GB into the image (`--volume $(PWD)/bundles/gutenberg-all:/workspace/gutenberg`),
cutting rebuild time for index-only changes to zero.

## The gaps, and what each costs

**1. No compose (the main work item).** Apple ships no `docker compose`
equivalent, so `worker` + `chat` + the `--profile chat` distinction become
explicit `container run` invocations. Since the Makefile is already the
only entry point, this is a Makefile rewrite, not a workflow change:

```make
run-native:
	container run -d --name gutenberg-worker \
	  --memory 8g --cpus 6 \
	  --env-file docker/.env \
	  -e GUTENBERG_ROOT=/workspace/gutenberg \
	  corpus-gutenberg:latest \
	  python -u -m gutenberg_kg.serve.handler --rp_serve_api --rp_api_host 0.0.0.0
	# reach the worker from the host at its container IP: container inspect gutenberg-worker

chat-native: run-native
	container run -d --name gutenberg-chat \
	  --memory 4g \
	  -e KGRAG_ENDPOINT=http://gutenberg-worker.gutenberg:8000 \
	  corpus-gutenberg:latest \
	  gutenkg chat --port 8501 --address 0.0.0.0

down-native:
	-container rm -f gutenberg-chat gutenberg-worker
```

`depends_on` becomes Make prerequisite ordering; profiles become separate
targets. (Community shims like
[Container-Compose](https://github.com/Mcrich23/Container-Compose) can read
a compose file directly, but for two services the Makefile is simpler and
has no extra dependency.)

**2. chat → worker networking requires macOS 26.** In compose, chat reaches
the worker as `http://worker:8000` on the compose network. With Apple
`container`, container-to-container traffic works on macOS 26 (Tahoe) — on
macOS 15 the vmnet network isolates containers from each other, which would
be a hard blocker for the chat profile. Name resolution comes from a local
DNS domain set up once:

```sh
sudo container system dns create gutenberg
container system property set dns.domain gutenberg
```

after which `gutenberg-worker.gutenberg` resolves from the chat container.
Alternative: skip DNS and inject the worker's IP
(`container inspect gutenberg-worker`) into `KGRAG_ENDPOINT`.

**3. Per-container memory must be set explicitly.** Docker Desktop gave all
containers one big shared VM; Apple gives each container its own VM with a
small default allocation. The worker (torch + bge-small + 696K-node
graph.sqlite + LanceDB) will OOM at defaults — `--memory 8g` (worker) /
`--memory 4g` (chat) are the starting points. Memory is a lazy upper bound,
not a reservation, so this doesn't pin 12 GB of RAM; but note that pages
freed inside the guest aren't fully returned to the host, so a long-running
worker may want an occasional restart.

**4. No `restart: unless-stopped`.** Apple `container` has no restart
policies and no daemon supervising containers across reboots. For a dev
worker this mostly doesn't matter (`make run` after boot); if auto-start is
wanted, a small launchd agent running `container start gutenberg-worker` is
the idiomatic Mac answer.

**5. `/.dockerenv` detection breaks.** `serve/Chat.py:29` and
`serve/pages/1_Browse.py:25` decide between `host.docker.internal` and
`localhost` by testing for `/.dockerenv`, which only Docker creates. Inside
an Apple container the code would wrongly pick `localhost`. Fix: add
`ENV GUTENKG_IN_CONTAINER=1` to both Dockerfiles and change the check to

```python
_IN_CONTAINER = os.path.exists("/.dockerenv") or bool(os.environ.get("GUTENKG_IN_CONTAINER"))
```

which stays correct under both runtimes.

**6. `.env` handling.** Compose auto-loads `docker/.env`; `container run`
needs an explicit `--env-file docker/.env` (supported) in the Make targets.

## What should NOT move

- **`runpod/`** — RunPod serverless is x86_64 cloud infrastructure. The
  image must stay linux/amd64 and the build stays on Docker/buildx.
  (`container build --arch amd64` exists but cross-builds the whole
  pip/torch install under emulation — slow for no benefit.)
- **Publishing `egsuchanek/kgrag-worker`** — can move later
  (`container build` + `container registry push` handle it), but it's
  upstream of this repo and orthogonal to this assessment.

## Migration plan (estimated ~half a day)

1. **Prereqs** — macOS 26, `brew install --cask container` (or the pkg from
   GitHub releases), `container system start`. Hard requirement: macOS 26
   for the chat↔worker networking; macOS 15 supports only the worker-alone
   path.
2. **Smoke test, zero code changes** (~30 min): `container build` the main
   image, `container run` the worker with `--memory 8g -p 8000:8000`, hit
   `make query`. This validates 90% of the risk surface immediately.
3. **Code fix** (~15 min): the `/.dockerenv` → env-var change in `Chat.py`,
   `1_Browse.py`, plus `ENV GUTENKG_IN_CONTAINER=1` in both Dockerfiles
   (harmless under Docker).
4. **Makefile** (~1–2 h): add `run`/`chat`/`up`/`down`/`logs`/`clean`
   equivalents driven by a `RUNTIME ?= docker` variable so both runtimes
   coexist (`make up RUNTIME=apple`), rather than deleting the compose path
   on day one.
5. **DNS setup** (~10 min, once per machine): `container system dns create`
   for the chat→worker hostname, documented in INSTALLATION.md.
6. **Docs** (~30 min): README/CHEATSHEET notes; keep compose documented as
   the cross-platform path (collaborators on Linux/older macOS still need
   it).

## Recommendation

Worth doing, as an *addition* rather than a replacement. GutenbergKG is an
unusually good candidate: the base image is already arm64, the host-service
pattern (oMLX/mflux/Ollama on the Mac, worker in the container) is exactly
what `container` 0.9+ supports natively, and orchestration already lives in
the Makefile rather than in compose-specific tooling. The payoffs are no
Docker Desktop dependency (licensing + the perpetual-update treadmill),
faster cold starts, and per-container VM isolation. The costs are the
Makefile rewrite, explicit memory flags, no restart policy, and a hard
macOS 26 floor — which is why keeping the compose path alive alongside a
`RUNTIME=apple` switch is the sensible end state, with Docker remaining
mandatory for RunPod builds regardless.
