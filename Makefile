
# corpus-gutenberg — build and run targets
#
# Typical workflow:
#   make init           — fetch local ML models (spaCy, embedder); run once after clone
#   make chunk-diaries  — rebuild .diary/ chunks from committed .md (clean-clone step)
#   make build-diaries  — build .diarykg/ indices (prerequisite for build-corpus)
#   make build-corpus   — rebuild the DocKG + diary bundle (takes ~24 min)
#   make build          — build the container image (bakes bundle into image)
#   make run            — start the worker on http://localhost:8000
#   make image-server   — start the local FLUX image generation server on :8090
#   make sdxl-server    — start the local SDXL-Lightning image server on :8091
#   make chat           — start worker + Streamlit chat UI on http://localhost:8501
#   make up             — start everything: worker + chat UI + FLUX.2 image server (:8090)
#   make up IMAGE_BACKEND=sdxl  — start everything with the SDXL-Lightning server (:8091)
#   make down           - stop everything: worker + image servers + chat UI
#   make docs           — generate project docs into ./docs
#   make query Q="..."  — fire a one-shot query against the running worker
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

# Image backend for `make up`: flux (FLUX.2 / mflux, default) or sdxl (SDXL-Lightning).
#   make up                    → FLUX.2 on :8090
#   make up IMAGE_BACKEND=sdxl → SDXL-Lightning on :8091 (worker repointed automatically)
IMAGE_BACKEND ?= flux
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

.PHONY: init chunk-diaries build-diaries build-corpus check-pins setup build run image-server sdxl-server chat up stop down query logs clean docs

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
	container build -f docker/Dockerfile -t $(IMAGE):latest .

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
	$(MAKE) $(IMAGE_TARGET)
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
	docker build -f docker/Dockerfile -t $(IMAGE):latest .

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
	$(MAKE) $(IMAGE_TARGET)
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

query:
	@curl -s -X POST $(WORKER)/runsync \
	  -H "Content-Type: application/json" \
	  -d '{"input":{"query":"$(Q)","corpus":"all","k":5,"synthesize":false}}' | python3 -m json.tool

docs:
	cd src && pdoc --o ../site --logo "https://flux-frontiers.github.io/gutenberg_kg/logo.png" gutenberg_kg '!gutenberg_kg.serve.sdxl_server'
	cp assets/logos/logo_256.png site/logo.png
