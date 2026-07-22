# Assessment: Apple `container` as a Docker replacement for GutenbergKG

*Status: assessment only — no migration performed. 2026-07-22.*

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
| `docker/Dockerfile` | corpus image from `egsuchanek/kgrag-worker:latest`, bakes bundle | ✅ builds as-is |
| `docker/Dockerfile.sqlite` | sqlite-vec variant | ✅ builds as-is |
| `docker/docker-compose.yml` | worker + chat services, profiles, ports, env, restart | ⚠️ no compose — replace with `container run` targets |
| `Makefile` (`run`/`chat`/`up`/`down`/`logs`/`clean`) | drives compose | ⚠️ rewrite ~6 targets |
| `host.docker.internal` (compose env, `docker/.env.example`) | reach oMLX :8080, Ollama :11434, mflux :8090/:8091 on the host | ✅ supported natively since `container` 0.9.0 |
| `/.dockerenv` check in `serve/Chat.py` + `serve/pages/1_Browse.py` | detect "inside container" to pick `host.docker.internal` vs `localhost` | ❌ Apple VMs don't create `/.dockerenv` — needs a one-line fix |
| `runpod/` (Dockerfile, build_image.sh) | x86 serverless image for RunPod cloud | 🚫 keep on Docker (amd64 target) |
| GitHub Actions CI | — | ✅ no Docker usage at all |

## What works out of the box

**The base image is already linux/arm64.** `egsuchanek/kgrag-worker:latest`
on Docker Hub is published arm64-only, so it runs natively in Apple's VMs —
no Rosetta, no emulation penalty on the torch/embedding stack. Registry
pull/push (`container registry login`) speaks standard OCI, so Docker Hub
keeps working.

**Both Dockerfiles are plain BuildKit-compatible Dockerfiles.**
`container build` runs a BuildKit-based builder in its own VM and handles
everything these files use: `FROM`, `ARG`/`--build-arg`, `RUN` heredocs
(`python - <<'EOF'`), multi-file `COPY`, `ENV`, `CMD`. Expected commands:

```sh
container system start                       # once per boot
container build -f docker/Dockerfile -t corpus-gutenberg:latest .
container build -f docker/Dockerfile.sqlite -t corpus-gutenberg-sqlite:latest .
```

The multi-GB bundle `COPY` works; give the builder VM headroom first
(`container builder start --cpus 4 --memory 8g`) or the default builder may
struggle with the layer.

**Host services need no rework.** As of release 0.9.0 (Feb 2026), containers
resolve `host.docker.internal` to the host, so every default in
`docker-compose.yml` and `docker/.env.example` — oMLX on :8080, Ollama on
:11434, the FLUX/SDXL image servers on :8090/:8091 — keeps working verbatim.
(Containers also always reach the host at the vmnet gateway, 192.168.64.1 on
the default subnet.)

**Ports and volumes.** `container run --publish 8000:8000` forwards to
localhost like Docker; alternatively each container has its own routable IP
(`container inspect`) you can hit directly. Bind mounts (`--volume`) exist,
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
	  --publish 8000:8000 \
	  --env-file docker/.env \
	  -e GUTENBERG_ROOT=/workspace/gutenberg \
	  corpus-gutenberg:latest \
	  python -u -m gutenberg_kg.serve.handler --rp_serve_api --rp_api_host 0.0.0.0

chat-native: run-native
	container run -d --name gutenberg-chat \
	  --memory 4g \
	  --publish 8501:8501 \
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
