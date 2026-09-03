
# corpus-gutenberg — build and run targets
#
# Typical workflow:
#   make init           — fetch local ML models (spaCy, embedder); run once after clone
#   make chunk-diaries  — rebuild .diary/ chunks from committed .md (clean-clone step)
#   make build-diaries  — build .diarykg/ indices (prerequisite for build-corpus)
#   make build-corpus   — rebuild the DocKG + diary bundle (takes ~24 min)
#   make build          — build the container image (bakes bundle into image)
#   make build-all      — build for every runtime installed on this machine
#   make rebuild        — force a fresh build (--no-cache) for the selected runtime
#   make rebuild-all    — force a fresh build (--no-cache) for every runtime installed
#   make prune          — remove dangling images / stopped containers / build cache
#   make kill           — force-kill worker/chat containers under every runtime installed
#   make run            — start the worker on http://localhost:8000
#   make image-server   — start the local FLUX image server on :8090 (needs mflux:
#                         Apple Silicon, or Linux + CUDA 13)
#   make sdxl-server    — start the local SDXL-Lightning image server on :8091
#                         (diffusers; cuda -> mps -> cpu, so it runs anywhere)
#   make sdxl-fetch     — pre-download the SDXL weights (~7 GB) before first use
#   make chat           — start worker + Streamlit chat UI on http://localhost:8501
#   make up             — start everything: worker + chat UI + an image server.
#                         Picks FLUX.2 (:8090) where mflux can run, SDXL (:8091)
#                         otherwise. The image server is optional — if it fails,
#                         worker and chat stay up.
#   make up IMAGE_BACKEND=sdxl|flux  — force one backend
#   make down           - stop everything: worker + image servers + chat UI
#   make docs           — build the mkdocs site into ./site
#   make docs-serve      — serve the mkdocs site locally with live reload
#   make query Q="..."  — fire a one-shot query against the running worker
#
# The Knowledge Press, iPhone app (app/ios) -- see app/RUNBOOK.md section 6:
#   make ios-devices        -- list connected iPhones and their identifiers
#   make ios-generate       -- regenerate KnowledgePress.xcodeproj from project.yml
#   make ios-check          -- compile for arm64 device, unsigned; no phone needed
#   make ios-install-corpus -- push the corpus packs into the app's container
#   make ios-verify-corpus  -- list what is actually in that container
#   make ios-launch         -- relaunch the app so it re-reads the corpus
#   make ios-deploy         -- install-corpus + verify + launch, in order
#
# All the ios-* targets auto-detect the connected phone. With more than one
# attached, name it: make ios-deploy IOS_DEVICE=<udid|name>
#
# The Knowledge Press, Mac app (app/macos) -- see app/RUNBOOK.md section 7:
#   make mac-generate  -- regenerate KnowledgePress.xcodeproj from project.yml
#   make mac-build     -- Release .app, Developer ID signed, hardened runtime
#   make mac-verify    -- prove the signature is distributable before shipping
#   make mac-notarize  -- submit to Apple, wait, staple the ticket
#   make mac-dmg       -- package the stapled .app as a .dmg
#   make mac-release   -- build + verify + notarize + dmg, in order
#
# Container runtime — RUNTIME=docker (default) or RUNTIME=apple.
# RUNTIME=apple drives Apple's native `container` CLI instead of Docker
# (Apple Silicon + macOS 26; no Docker Desktop). First-time / per-boot setup
# is automatic — build/run/chat depend on `setup`, which installs the CLI if
# missing (Homebrew cask) and runs `container system start`.
# Same targets, one extra variable:
#   make setup RUNTIME=apple    — install `container` CLI + start its services
#   make build RUNTIME=apple    — build the image with `container build`
#   make run   RUNTIME=apple    — worker on localhost:8000 (idempotent; leaves a warm worker alone)
#   make chat  RUNTIME=apple    — worker + chat UI on localhost:8501
#   make up    RUNTIME=apple    — everything: worker + chat UI + image server
#   make down  RUNTIME=apple    — stop and delete both containers + image servers
#   make logs  RUNTIME=apple    — follow worker logs (`container logs -f`)
#   make clean RUNTIME=apple    — remove the image (`container image rm`)
# Per-container VM sizing (overridable): WORKER_MEM=8g WORKER_CPUS=6 CHAT_MEM=4g
#   make run RUNTIME=apple WORKER_MEM=12g
# See docs/APPLE_CONTAINERS.md for setup and caveats.
RUNTIME ?= docker

# NOTE: docker/Dockerfile is self-contained (python:3.12-slim + PyPI pins) and
# is now the only image definition here — the old sqlite-vec variant
# (docker/Dockerfile.sqlite, FROM egsuchanek/kgrag-worker:latest) was deleted
# once this one went sqlite-vec by default. The KG package pins live in that
# file's ARG defaults and nowhere else; keep them >= the pyproject.toml floors
# or `pip install .` silently upgrades past them.

IMAGE        = corpus-gutenberg
COMPOSE      = docker compose -f docker/docker-compose.yml
WORKER       = http://localhost:8000
IMAGE_SERVER = http://localhost:8090
SDXL_SERVER  = http://localhost:8091

# Extra flags spliced into both build recipes below. Empty for a normal
# `make build` (layer cache used); `make rebuild`/`rebuild-all` set this to
# --no-cache so a stale cached layer can't hide a change.
BUILD_FLAGS ?=

# Which runtimes are actually present, for `make build-all`/`prune` and the
# help text. Both are cheap `command -v` probes, evaluated once. Mirrors
# corpus_pepys, which carries the same dual-runtime setup.
HAVE_DOCKER := $(shell command -v docker >/dev/null 2>&1 && echo 1)
HAVE_APPLE  := $(shell command -v container >/dev/null 2>&1 && echo 1)

# HuggingFace auth for the image build's embedder pre-download. Anonymous Hub
# requests are rate-limited and print "You are sending unauthenticated requests
# to the HF Hub"; passing a token silences it and raises the limits. Sent as a
# BuildKit secret (both `docker build` and `container build` take --secret), so
# it is never baked into the image or readable from its history — unlike
# --build-arg. Source order: $HF_TOKEN from the environment, else the token
# `hf auth login` cached in ~/.cache/huggingface/token. Neither present is
# fine — bge-small is public and downloads anonymously.
COMMA := ,
HF_TOKEN_FILE ?= $(HOME)/.cache/huggingface/token
ifneq ($(HF_TOKEN),)
HF_SECRET := --secret id=hf_token$(COMMA)env=HF_TOKEN
else ifneq ($(wildcard $(HF_TOKEN_FILE)),)
HF_SECRET := --secret id=hf_token$(COMMA)src=$(HF_TOKEN_FILE)
else
HF_SECRET :=
endif

# Apple `container` runtime settings (RUNTIME=apple only). Each container is
# its own VM — memory is an explicit upper bound, not shared with the host
# like Docker Desktop's single big VM. Right-sized per the corpus_pepys
# `container stats` recipe (same worker/chat shape): worker needs ~2g,
# chat ~512m. See docs/APPLE_CONTAINERS.md. Lazily allocated, so this
# doesn't pin the RAM, just caps it — override per-machine if needed.
WORKER_NAME  = gutenberg-worker
CHAT_NAME    = gutenberg-chat
WORKER_MEM  ?= 2g
WORKER_CPUS ?= 6
CHAT_MEM    ?= 512m

# Host reachability from containers. Apple's `container` DOES support
# Docker-style port publishing (`--publish`) as of CLI v1.1.0, so the worker
# and chat ports are forwarded to the host and reachable at localhost, just
# like the Docker path. Containers reach the host — and each other's published
# ports — at the vmnet gateway IP; host.docker.internal still does NOT resolve
# in-container on this runtime. Getting the gateway wrong fails silently: the
# worker simply cannot reach the LLM, so you get answers with no synthesis and
# no error. So auto-detect it from the live `default` network, and treat the
# constant purely as a cold-start fallback for when the runtime is not running
# yet; override explicitly with `make APPLE_HOST_GW=… …` if needed.
#
# The fallback is 192.168.64.1 because that is what the `container-network-vmnet`
# plugin actually allocates — macOS's vmnet framework defaults to
# 192.168.64.0/24. Verified on CLI 1.1.0 against a network created fresh by
# `container system start`, so this is the current CLI's allocation, not a
# leftover from an older one:
#
#   $ container network list
#   NETWORK  SUBNET
#   default  192.168.64.0/24
#
# This previously read 192.168.65.1, with a comment claiming 1.1.0 had moved to
# 192.168.65.0/24. That was wrong — 192.168.65.x is *Docker Desktop's* gateway
# subnet, the likely source of the number — and it contradicted this repo's own
# docs/APPLE_CONTAINERS.md, which documents 192.168.64.1 throughout.
#
# Host services (oMLX :8080, Ollama :11434, image server) must also bind
# 0.0.0.0, not 127.0.0.1, to be reachable over the vmnet.
ifeq ($(RUNTIME),apple)
APPLE_HOST_GW ?= $(or $(shell container network inspect default 2>/dev/null | sed -n 's/.*"ipv4Gateway" : "\([0-9.]*\)".*/\1/p' | head -1),192.168.64.1)
else
APPLE_HOST_GW ?= 192.168.64.1
endif

# ------------------------------------------------------------------
# Can this host run the FLUX image server?
#
# `make image-server` builds .venv-image from docker/requirements-image.txt,
# which installs mflux. mflux is not portable — its own metadata says:
#
#     mlx<0.32.0,>=0.27.0          ; sys_platform == "darwin"
#     mlx[cuda13]<0.32.0,>=0.30.3  ; sys_platform == "linux"
#
# so it needs Apple MLX on macOS arm64, or CUDA 13 and an NVIDIA GPU on Linux,
# and there is no Windows entry at all. On any other host the pip install fails.
#
# The SDXL backend has no such constraint: gutenberg_kg.serve.sdxl_server
# resolves cuda -> mps -> cpu, so its diffusers/torch stack runs anywhere (on
# CPU it is slow, but it works). That is why the default below falls back to it
# rather than simply skipping image generation.
#
# FORCE_IMAGE_SERVER=1 asserts flux support — the escape hatch for a CUDA 13
# Linux box, which mflux does support but this probe cannot detect.
# ------------------------------------------------------------------
MFLUX_OK := $(shell \
  if [ "$(FORCE_IMAGE_SERVER)" = "1" ]; then echo 1; \
  elif [ "$$(uname -s 2>/dev/null)" = "Darwin" ] && [ "$$(uname -m 2>/dev/null)" = "arm64" ]; then echo 1; \
  fi)

# Image backend for `make up`: flux (FLUX.2 / mflux) or sdxl (SDXL-Lightning).
#   make up                    → FLUX.2 on :8090   (where mflux can run)
#                                SDXL-Lightning on :8091 (everywhere else)
#   make up IMAGE_BACKEND=sdxl → SDXL-Lightning on :8091 (worker repointed automatically)
#   make up IMAGE_BACKEND=flux → force FLUX.2; errors out if mflux cannot run here
#
# The default is conditional so `make up` works on a host without Apple Silicon.
# It used to be a flat `flux`, which meant `up` ran `make image-server`
# unconditionally and died on the mflux install — after the worker and chat had
# already started, so the whole stack looked broken when only the image backend
# was unavailable. On Apple Silicon nothing changes.
IMAGE_BACKEND ?= $(if $(MFLUX_OK),flux,sdxl)
ifeq ($(IMAGE_BACKEND),sdxl)
IMAGE_TARGET  = sdxl-server
IMAGE_URL     = $(SDXL_SERVER)
IMG_ENDPOINT  = http://host.docker.internal:8091
else
IMAGE_TARGET  = image-server
IMAGE_URL     = $(IMAGE_SERVER)
IMG_ENDPOINT  = http://host.docker.internal:8090
endif

# Use the project's own CLI from the repo venv, not a (possibly stale) global
# `gutenkg` on PATH. Override with e.g. `make GUTENKG=gutenkg build-corpus`.
GUTENKG     ?= poetry run gutenkg

.PHONY: init chunk-diaries build-diaries build-corpus check-pins setup build build-all rebuild rebuild-all prune kill run image-server sdxl-server sdxl-fetch chat up stop down query logs clean docs ios-devices ios-generate ios-check ios-install-corpus ios-verify-corpus ios-launch ios-deploy mac-generate mac-build mac-verify mac-notarize mac-dmg mac-release

init:
	$(GUTENKG) init

chunk-diaries:
	$(GUTENKG) chunk-diaries

build-diaries: chunk-diaries
	$(GUTENKG) build-diaries --force

build-corpus: build-diaries
	$(GUTENKG) build-corpus

# The four KG packages are named in four files that drift independently:
# pyproject floors, poetry.lock, docker/Dockerfile ARGs, runpod/requirements.txt.
# A Dockerfile ARG below its pyproject floor is not a build failure — the
# `pip install .` step just re-resolves past it — so the pin silently stops
# describing the image. A prerequisite of `build` in both runtime branches so a
# drifted image cannot be produced in the first place.
check-pins:
	@python3 scripts/check_pins.py

# Build the image under EVERY runtime installed on this machine, rather than
# only the one RUNTIME selects. Docker and Apple's `container` CLI keep
# separate image stores, so an image built by one is invisible to the other.
# Skips a runtime that is not installed rather than failing — mirrors
# corpus_pepys, which carries the same dual-runtime setup.
build-all:
	@if [ -z "$(HAVE_DOCKER)$(HAVE_APPLE)" ]; then \
		echo "ERROR: neither Docker nor Apple's 'container' CLI is installed."; \
		exit 1; \
	fi
	@if [ "$(HAVE_DOCKER)" = "1" ]; then \
		echo "==> Building with Docker ..."; \
		$(MAKE) --no-print-directory build RUNTIME=docker; \
	else \
		echo "==> Skipping Docker — not installed."; \
	fi
	@if [ "$(HAVE_APPLE)" = "1" ]; then \
		echo "==> Building with Apple container ..."; \
		$(MAKE) --no-print-directory build RUNTIME=apple; \
	else \
		echo "==> Skipping Apple container — not installed."; \
	fi

# Force a fresh image under the selected runtime, ignoring the layer cache —
# for when a cached layer is masking a change (e.g. a KG pin bump that
# `check-pins` confirms but the cached pip-install layer never re-ran).
# `build-all`'s BUILD_FLAGS override propagates through automatically: GNU
# Make re-exports a command-line-set variable to every nested $(MAKE).
rebuild:
	@$(MAKE) --no-print-directory build BUILD_FLAGS=--no-cache

rebuild-all:
	@$(MAKE) --no-print-directory build-all BUILD_FLAGS=--no-cache

# Hygiene: dangling images, stopped containers, and (Docker only) build cache
# left behind by repeated build/rebuild runs. Runs under every runtime
# installed, not just $(RUNTIME) — mirrors build-all, since Docker's and
# Apple container's stores accumulate independently of each other. Only
# removes dangling/stopped resources, never the tagged $(IMAGE):latest itself
# — that's what `make clean` is for.
prune:
	@if [ "$(HAVE_DOCKER)" = "1" ]; then \
		echo "==> Pruning Docker: dangling images, stopped containers, build cache ..."; \
		docker image prune -f; \
		docker container prune -f; \
		docker builder prune -f; \
	else \
		echo "==> Skipping Docker — not installed."; \
	fi
	@if [ "$(HAVE_APPLE)" = "1" ]; then \
		echo "==> Pruning Apple container: dangling images, stopped containers ..."; \
		container image prune; \
		container prune; \
	else \
		echo "==> Skipping Apple container — not installed."; \
	fi
	@echo "Done. Pruned."

# Force-kill the worker + chat containers and the local image-server
# processes, under every runtime installed — not just $(RUNTIME). Unlike
# `stop`/`down` (gated to the selected runtime, graceful), this is the "get
# me back to zero" button: no grace period, no profile/service-name
# filtering, and it reaches whichever runtime actually has something running
# regardless of which one is currently selected.
kill:
	@if [ "$(HAVE_DOCKER)" = "1" ]; then \
		echo "==> Killing Docker containers ..."; \
		$(COMPOSE) --profile chat down --timeout 0 --remove-orphans 2>/dev/null || true; \
	else \
		echo "==> Skipping Docker — not installed."; \
	fi
	@if [ "$(HAVE_APPLE)" = "1" ]; then \
		echo "==> Killing Apple containers ..."; \
		container delete -f $(WORKER_NAME) $(CHAT_NAME) 2>/dev/null || true; \
	else \
		echo "==> Skipping Apple container — not installed."; \
	fi
	@echo "==> Killing local image-server processes ..."
	-pkill -f gutenkg-image-server 2>/dev/null || true
	-pkill -f gutenkg-sdxl-server 2>/dev/null || true
	@echo "Done. Killed."

ifeq ($(RUNTIME),apple)

# ---------------------------------------------------------------------------
# Apple `container` runtime (macOS 26, Apple Silicon).
# `setup` installs the CLI if needed and starts its services (the once-per-
# boot step); build/run depend on it, so a clean clone works out of the box.
# Ports are published to the host (`--publish`, container CLI >= 1.1.0), so the
# worker and chat UI are reachable at localhost, same as the Docker path.
# host.docker.internal does NOT resolve inside the containers on this runtime,
# so in-container endpoints (chat->worker, host services) use the vmnet gateway
# ($(APPLE_HOST_GW)). docker/.env is sourced explicitly below to mirror
# compose's automatic .env loading.
# ---------------------------------------------------------------------------

# Rewrite the shared image-server endpoint (defined with host.docker.internal
# for docker-compose) to the vmnet gateway, which is how the host is reachable.
IMG_ENDPOINT := $(subst host.docker.internal,$(APPLE_HOST_GW),$(IMG_ENDPOINT))

# docker/.env is written for Docker, where the host is host.docker.internal —
# a name that does NOT resolve inside an Apple container VM. After sourcing it,
# rewrite each endpoint var to the vmnet gateway ($(APPLE_HOST_GW)) so host
# services (oMLX :8080, Ollama :11434, image server) stay reachable, applying
# the gateway default when the var is unset. Used after `. docker/.env` in the
# run/chat recipes; without this, a .env pointing oMLX at host.docker.internal
# silently disables synthesis (the worker can't see the LLM).
APPLE_REWRITE_ENDPOINTS = \
  VLLM_ENDPOINT_URL=$$(printf '%s' "$${VLLM_ENDPOINT_URL:-http://$(APPLE_HOST_GW):8080/v1}" | sed 's/host\.docker\.internal/$(APPLE_HOST_GW)/g'); \
  OLLAMA_ENDPOINT=$$(printf '%s' "$${OLLAMA_ENDPOINT:-http://$(APPLE_HOST_GW):11434/v1}" | sed 's/host\.docker\.internal/$(APPLE_HOST_GW)/g'); \
  GUTENKG_IMAGE_ENDPOINT=$$(printf '%s' "$${GUTENKG_IMAGE_ENDPOINT:-$(IMG_ENDPOINT)}" | sed 's/host\.docker\.internal/$(APPLE_HOST_GW)/g')

# Idempotent host setup: install Apple's `container` CLI if missing (Homebrew
# formula, bottled — no sudo; otherwise point at the GitHub releases pkg) and
# start its services. `container system start` is a no-op when already
# running; --enable-kernel-install auto-answers the first-run prompt to
# download the default guest kernel (Kata) that every container VM boots.
setup:
	@if ! command -v container >/dev/null 2>&1; then \
		if command -v brew >/dev/null 2>&1; then \
			echo "Installing Apple container CLI (brew install container) ..."; \
			brew install container; \
		else \
			echo "Apple 'container' CLI not found and Homebrew is unavailable."; \
			echo "Install the pkg from https://github.com/apple/container/releases, then re-run."; \
			exit 1; \
		fi; \
	fi
	@container system start --enable-kernel-install
	@echo "Apple container runtime ready."

build: check-pins setup
	container build $(BUILD_FLAGS) $(HF_SECRET) -f docker/Dockerfile -t $(IMAGE):latest .

# Idempotent like `compose up`: a running worker is left alone (it takes a
# while to load the index), a stopped or stale one is replaced.
run: setup
	@if container list --quiet 2>/dev/null | grep -qx "$(WORKER_NAME)"; then \
		echo "Worker already running at $(WORKER)"; exit 0; \
	fi; \
	container delete -f $(WORKER_NAME) >/dev/null 2>&1 || true; \
	set -a; [ -f docker/.env ] && . docker/.env; set +a; \
	$(APPLE_REWRITE_ENDPOINTS); \
	container run --detach --name $(WORKER_NAME) \
	  --memory $(WORKER_MEM) --cpus $(WORKER_CPUS) \
	  --publish 8000:8000 \
	  -e GUTENBERG_ROOT=/workspace/gutenberg \
	  -e EMBED_MODEL=BAAI/bge-small-en-v1.5 \
	  -e HANDLER_SECRET="$${HANDLER_SECRET:-}" \
	  -e VLLM_ENDPOINT_URL="$$VLLM_ENDPOINT_URL" \
	  -e VLLM_MODEL="$${VLLM_MODEL:-Qwen3-4B-Instruct-2507-MLX-8bit}" \
	  -e VLLM_API_KEY="$${VLLM_API_KEY:-}" \
	  -e OLLAMA_ENDPOINT="$$OLLAMA_ENDPOINT" \
	  -e OPENAI_API_KEY="$${OPENAI_API_KEY:-}" \
	  -e GUTENKG_IMAGE_ENDPOINT="$$GUTENKG_IMAGE_ENDPOINT" \
	  -e IMAGE_ENDPOINT="$$GUTENKG_IMAGE_ENDPOINT" \
	  -e IMAGE_STEPS="$${IMAGE_STEPS:-4}" \
	  $(IMAGE):latest \
	  python -u -m gutenberg_kg.serve.handler --rp_serve_api --rp_api_host 0.0.0.0
	@echo "Worker running at $(WORKER)"

# Chat reaches the worker at the vmnet gateway, where the worker's published
# 8000 is forwarded to the host — no container-to-container vmnet needed.
chat: run
	@container delete -f $(CHAT_NAME) >/dev/null 2>&1 || true
	@set -a; [ -f docker/.env ] && . docker/.env; set +a; \
	$(APPLE_REWRITE_ENDPOINTS); \
	container run --detach --name $(CHAT_NAME) \
	  --memory $(CHAT_MEM) \
	  --publish 8501:8501 \
	  -e KGRAG_ENDPOINT="http://$(APPLE_HOST_GW):8000" \
	  -e HANDLER_SECRET="$${HANDLER_SECRET:-}" \
	  -e GUTENKG_IMAGE_ENDPOINT="$$GUTENKG_IMAGE_ENDPOINT" \
	  -e IMAGE_ENDPOINT="$$GUTENKG_IMAGE_ENDPOINT" \
	  -e IMAGE_STEPS="$${IMAGE_STEPS:-4}" \
	  $(IMAGE):latest \
	  gutenkg chat --port 8501 --address 0.0.0.0
	@echo "Worker:  $(WORKER)"
	@echo "Chat UI: http://localhost:8501"

start up:
	@echo "Starting worker + chat (Apple container), image backend: $(IMAGE_BACKEND) ($(IMG_ENDPOINT)) ..."
	GUTENKG_IMAGE_ENDPOINT=$(IMG_ENDPOINT) $(MAKE) chat RUNTIME=apple
	@echo "Starting $(IMAGE_BACKEND) image server ..."
	-@$(MAKE) --no-print-directory $(IMAGE_TARGET) || \
		echo "WARNING: the image server did not start. Worker and chat are up; only the chat UI's 'Render response' button is affected."

	@echo ""
	@echo "Worker:       $(WORKER)"
	@echo "Image server: $(IMAGE_URL)  ($(IMAGE_BACKEND))"
	@echo "Chat UI:      http://localhost:8501"
	@echo ""
	@echo "Run 'make stop RUNTIME=apple' to shut down containers + image servers."

stop down:
	-container delete -f $(CHAT_NAME) $(WORKER_NAME) 2>/dev/null || true
	-pkill -f gutenkg-image-server 2>/dev/null || true
	-pkill -f gutenkg-sdxl-server 2>/dev/null || true

logs:
	container logs -f $(WORKER_NAME)

clean:
	container image rm $(IMAGE):latest 2>/dev/null || true

else

# ---------------------------------------------------------------------------
# Docker runtime (default) — docker compose drives worker + chat.
# ---------------------------------------------------------------------------

# Nothing to install here — just verify the Docker daemon is reachable.
setup:
	@command -v docker >/dev/null 2>&1 || { echo "Docker not found — install Docker Desktop, or use RUNTIME=apple."; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker daemon not running — start Docker Desktop, or use RUNTIME=apple."; exit 1; }
	@echo "Docker runtime ready."

build: check-pins
	docker build $(BUILD_FLAGS) $(HF_SECRET) -f docker/Dockerfile -t $(IMAGE):latest .

run:
	$(COMPOSE) up -d worker
	@echo "Worker running at $(WORKER)"

chat:
	$(COMPOSE) --profile chat up -d
	@echo "Worker:  $(WORKER)"
	@echo "Chat UI: http://localhost:8501"

start up:
	@echo "Starting worker + chat (Docker), image backend: $(IMAGE_BACKEND) ($(IMG_ENDPOINT)) ..."
	GUTENKG_IMAGE_ENDPOINT=$(IMG_ENDPOINT) IMAGE_ENDPOINT=$(IMG_ENDPOINT) $(COMPOSE) --profile chat up -d
	@echo "Starting $(IMAGE_BACKEND) image server ..."
	-@$(MAKE) --no-print-directory $(IMAGE_TARGET) || \
		echo "WARNING: the image server did not start. Worker and chat are up; only the chat UI's 'Render response' button is affected."

	@echo ""
	@echo "Worker:       $(WORKER)"
	@echo "Image server: $(IMAGE_URL)  ($(IMAGE_BACKEND))"
	@echo "Chat UI:      http://localhost:8501"
	@echo ""
	@echo "Run 'make stop' to shut down Docker services + image servers."

stop down:
	$(COMPOSE) --profile chat down
	-pkill -f gutenkg-image-server 2>/dev/null || true
	-pkill -f gutenkg-sdxl-server 2>/dev/null || true

logs:
	$(COMPOSE) logs -f worker

clean:
	docker rmi $(IMAGE):latest 2>/dev/null || true

endif

image-server:
	@if [ "$(MFLUX_OK)" != "1" ]; then \
		echo "ERROR: the FLUX image server cannot run on this host."; \
		echo "  mflux needs Apple MLX (macOS arm64), or mlx[cuda13] on a Linux box"; \
		echo "  with an NVIDIA GPU. It publishes no Windows wheel."; \
		echo "  Use the portable backend instead:  make up IMAGE_BACKEND=sdxl"; \
		echo "  (SDXL-Lightning resolves cuda -> mps -> cpu, so it runs anywhere.)"; \
		echo "  Or re-run with FORCE_IMAGE_SERVER=1 on a CUDA 13 Linux host."; \
		exit 1; \
	fi
	@if [ ! -x .venv-image/bin/python ]; then \
		echo "Creating .venv-image for isolated image dependencies ..."; \
		python3 -m venv .venv-image; \
	fi
	@.venv-image/bin/python -m pip install --quiet --upgrade pip
	@.venv-image/bin/python -m pip install --quiet -r docker/requirements-image.txt
	@.venv-image/bin/python -m pip install --quiet --no-deps -e .
	@echo "Starting FLUX image server on $(IMAGE_SERVER) (background, .venv-image) ..."
	MFLUX_SERVER_HOST=0.0.0.0 .venv-image/bin/gutenkg-image-server &

sdxl-server:
	@if [ ! -x .venv-sdxl/bin/python ]; then \
		echo "Creating .venv-sdxl for isolated SDXL/diffusers dependencies ..."; \
		python3 -m venv .venv-sdxl; \
	fi
	@.venv-sdxl/bin/python -m pip install --quiet --upgrade pip
	@.venv-sdxl/bin/python -m pip install --quiet -r docker/requirements-sdxl.txt
	@.venv-sdxl/bin/python -m pip install --quiet --no-deps -e .
	@echo "Starting SDXL-Lightning image server on $(SDXL_SERVER) (background, .venv-sdxl) ..."
	SDXL_SERVER_HOST=0.0.0.0 .venv-sdxl/bin/gutenkg-sdxl-server &

# Pre-download the SDXL weights without starting the server, so the first
# `make up` on a fresh machine is not a silent multi-GB wait. Once cached,
# SDXL_OFFLINE=1 makes the server refuse network access entirely.
sdxl-fetch:
	@if [ ! -x .venv-sdxl/bin/python ]; then \
		echo "Creating .venv-sdxl for isolated SDXL/diffusers dependencies ..."; \
		python3 -m venv .venv-sdxl; \
	fi
	@.venv-sdxl/bin/python -m pip install --quiet --upgrade pip
	@.venv-sdxl/bin/python -m pip install --quiet -r docker/requirements-sdxl.txt
	@.venv-sdxl/bin/python -m pip install --quiet --no-deps -e .
	@echo "Fetching SDXL-Lightning weights (~7 GB, cached under ~/.cache/huggingface) ..."
	@.venv-sdxl/bin/python -c "from gutenberg_kg.serve.sdxl_server import _load_pipeline; _load_pipeline()"
	@echo "Done. Weights cached; SDXL_OFFLINE=1 will now work."

query:
	@curl -s -X POST $(WORKER)/runsync \
	  -H "Content-Type: application/json" \
	  -d '{"input":{"query":"$(Q)","corpus":"all","k":5,"synthesize":false}}' | python3 -m json.tool

docs:
	poetry run mkdocs build

docs-serve:
	poetry run mkdocs serve

# ---------------------------------------------------------------------------
# The Knowledge Press -- iPhone app (app/ios)
#
# Codifies app/RUNBOOK.md section 6. The generated .xcodeproj is gitignored;
# project.yml is the source of truth, so `ios-generate` is safe to re-run and
# anything hand-edited in Xcode's target editor is lost by design.
# ---------------------------------------------------------------------------

IOS_BUNDLE_ID ?= com.fluxfrontiers.knowledgepress
IOS_CORPUS_DIR ?= bundles/gutenberg-all/swift
IOS_CONTAINER_PATH = Library/Application Support/Corpus
IOS_DEVICE ?=

# Resolve the target device inside a recipe: honour IOS_DEVICE when set, else
# take the single connected phone, else say so and stop.
define ios_resolve_device
DEV="$(IOS_DEVICE)"; \
if [ -z "$$DEV" ]; then \
	DEV=$$(xcrun devicectl list devices --json-output /dev/stdout 2>/dev/null \
	  | python3 -c 'import json,sys; d=json.load(sys.stdin)["result"]["devices"]; print(d[0]["identifier"] if d else "")'); \
fi; \
if [ -z "$$DEV" ]; then \
	echo "No iPhone found. Connect one, enable Developer Mode, or pass IOS_DEVICE=<udid|name>."; \
	exit 1; \
fi
endef

ios-devices:
	@xcrun devicectl list devices

ios-generate:
	@command -v xcodegen >/dev/null 2>&1 \
	  || { echo "xcodegen not found -- brew install xcodegen"; exit 1; }
	cd app/ios && xcodegen generate

# Compiles for a real device without a phone, an Apple account, or a
# signature -- so a code failure is never confused with a signing one.
ios-check: ios-generate
	cd app/ios && xcodebuild -project KnowledgePress.xcodeproj -scheme KnowledgePress \
	  -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build

# Run the app on the device at least once first, so its container exists.
# Unchanged files are skipped, so re-running after a fresh export only moves
# what actually differs.
ios-install-corpus:
	@test -f "$(IOS_CORPUS_DIR)/manifest.json" \
	  || { echo "No corpus at $(IOS_CORPUS_DIR) -- run 'gutenkg export-swift --verify' first."; exit 1; }
	@$(ios_resolve_device); \
	cd "$(IOS_CORPUS_DIR)" && xcrun devicectl device copy to --device "$$DEV" \
	  --domain-type appDataContainer --domain-identifier $(IOS_BUNDLE_ID) \
	  --destination "$(IOS_CONTAINER_PATH)" \
	  $$(for f in *; do printf -- '--source %s ' "$$f"; done)

# Sixteen entries, because BGEEmbedder.mlpackage lists its insides. The one
# that matters is .../weights/weight.bin at ~63 MB: a flattened copy of that
# bundle is what leaves the app reporting a corpus it cannot open.
ios-verify-corpus:
	@$(ios_resolve_device); \
	xcrun devicectl device info files --device "$$DEV" \
	  --domain-type appDataContainer --domain-identifier $(IOS_BUNDLE_ID) \
	  --subdirectory "$(IOS_CONTAINER_PATH)"

ios-launch:
	@$(ios_resolve_device); \
	xcrun devicectl device process launch --device "$$DEV" \
	  --terminate-existing $(IOS_BUNDLE_ID)

ios-deploy: ios-install-corpus ios-verify-corpus ios-launch
	@echo "Corpus installed and app relaunched. Settings > Corpus should say 'on this device'."

# ---------------------------------------------------------------------------
# The Knowledge Press -- Mac app (app/macos)
#
# `swift run KnowledgePress` from app/GutenbergKGKit is still the fast loop.
# These targets produce the thing a SwiftPM executable cannot be: a signed,
# notarized bundle someone else can install.
#
# Deliberately unsandboxed, so the .app reads the same
# ~/Library/Application Support/Corpus that `swift run` does. Adding the
# sandbox later moves that into the app's container and costs one re-copy --
# no code change, since CorpusPacks.defaultDirectory() goes through
# FileManager.
# ---------------------------------------------------------------------------

MAC_BUILD_DIR ?= app/macos/build
MAC_APP = $(MAC_BUILD_DIR)/Build/Products/Release/KnowledgePress.app
MAC_DMG ?= $(MAC_BUILD_DIR)/KnowledgePress.dmg
# `notarytool store-credentials <name>` writes this; see RUNBOOK section 7.
MAC_NOTARY_PROFILE ?= knowledgepress-notary

# Resolve the Developer ID Application identity from the login keychain, so
# the signer's name is never hardcoded here.
define mac_resolve_identity
IDENTITY=$$(security find-identity -v -p codesigning \
	  | sed -n 's/.*"\(Developer ID Application: .*\)"/\1/p' | head -1); \
if [ -z "$$IDENTITY" ]; then \
	echo "No Developer ID Application certificate in the login keychain."; \
	echo "Xcode > Settings > Accounts > Manage Certificates > + Developer ID Application."; \
	exit 1; \
fi; \
TEAM=$$(printf '%s' "$$IDENTITY" | sed -n 's/.*(\([A-Z0-9]*\))$$/\1/p')
endef

mac-generate:
	@command -v xcodegen >/dev/null 2>&1 \
	  || { echo "xcodegen not found -- brew install xcodegen"; exit 1; }
	cd app/macos && xcodegen generate

mac-build: mac-generate
	@$(mac_resolve_identity); \
	echo "Signing as $$IDENTITY"; \
	cd app/macos && xcodebuild -project KnowledgePress.xcodeproj \
	  -scheme KnowledgePress -destination 'platform=macOS' \
	  -derivedDataPath build -configuration Release \
	  CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM="$$TEAM" \
	  CODE_SIGN_IDENTITY="$$IDENTITY" OTHER_CODE_SIGN_FLAGS="--timestamp" \
	  build | tail -3

# The checks worth making before spending a notarization round trip. The
# entitlements check is the one that matters: Xcode injects
# com.apple.security.get-task-allow unless CODE_SIGN_INJECT_BASE_ENTITLEMENTS
# is NO, the notary service rejects anything carrying it, and the app signs
# and passes spctl locally either way.
mac-verify:
	@test -d "$(MAC_APP)" || { echo "No app at $(MAC_APP) -- run 'make mac-build'."; exit 1; }
	@echo "== architectures =="
	@lipo -archs "$(MAC_APP)/Contents/MacOS/KnowledgePress"
	@echo "== signature =="
	@codesign -dvvv "$(MAC_APP)" 2>&1 | grep -E 'Authority|TeamIdentifier|flags|Timestamp'
	@echo "== hardened runtime =="
	@codesign -dvvv "$(MAC_APP)" 2>&1 | grep -q '0x10000(runtime)' \
	  && echo "enabled" \
	  || { echo "MISSING -- notarization will fail"; exit 1; }
	@echo "== debug entitlement =="
	@codesign -d --entitlements - "$(MAC_APP)" 2>&1 | grep -q 'get-task-allow' \
	  && { echo "PRESENT -- notarization will be rejected"; exit 1; } \
	  || echo "absent"
	@echo "== gatekeeper =="
	@spctl -a -vvv -t exec "$(MAC_APP)" 2>&1 | head -3

mac-notarize: mac-verify
	@xcrun notarytool history --keychain-profile "$(MAC_NOTARY_PROFILE)" >/dev/null 2>&1 \
	  || { echo "No notarytool profile '$(MAC_NOTARY_PROFILE)'. Create it once:"; \
	        echo "  xcrun notarytool store-credentials $(MAC_NOTARY_PROFILE) \\"; \
	        echo "    --apple-id <your-apple-id> --team-id <team> --password <app-specific-password>"; \
	        echo "App-specific passwords come from appleid.apple.com, not your Apple ID password."; \
	        exit 1; }
	ditto -c -k --keepParent "$(MAC_APP)" "$(MAC_BUILD_DIR)/KnowledgePress.zip"
	xcrun notarytool submit "$(MAC_BUILD_DIR)/KnowledgePress.zip" \
	  --keychain-profile "$(MAC_NOTARY_PROFILE)" --wait
	xcrun stapler staple "$(MAC_APP)"
	@echo "Stapled. The app now launches on a machine that has never seen it."

mac-dmg:
	@test -d "$(MAC_APP)" || { echo "No app at $(MAC_APP) -- run 'make mac-build'."; exit 1; }
	@rm -f "$(MAC_DMG)"
	hdiutil create -volname "Knowledge Press" -srcfolder "$(MAC_APP)" \
	  -ov -format UDZO "$(MAC_DMG)"
	@echo "Wrote $(MAC_DMG)"

mac-release: mac-build mac-verify mac-notarize mac-dmg
	@echo "Signed, notarized, stapled, packaged: $(MAC_DMG)"
