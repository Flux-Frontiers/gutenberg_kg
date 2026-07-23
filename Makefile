
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
#   make run   RUNTIME=apple    — worker on :8000 (idempotent; leaves a warm worker alone)
#   make chat  RUNTIME=apple    — worker + chat UI on :8501 (needs macOS 26 vmnet)
#   make up    RUNTIME=apple    — everything: worker + chat UI + image server
#   make down  RUNTIME=apple    — stop and delete both containers + image servers
#   make logs  RUNTIME=apple    — follow worker logs (`container logs -f`)
#   make clean RUNTIME=apple    — remove the image (`container image rm`)
# Per-container VM sizing (overridable): WORKER_MEM=8g WORKER_CPUS=6 CHAT_MEM=4g
#   make run RUNTIME=apple WORKER_MEM=12g
# See docs/APPLE_CONTAINERS.md for setup and caveats.
RUNTIME ?= docker

# NOTE: docker/Dockerfile is self-contained (python:3.12-slim + PyPI pins).
# Only the sqlite-vec variant (docker/Dockerfile.sqlite) still builds FROM
# egsuchanek/kgrag-worker:latest — that base is built and pushed from the
# KGRAG repo (~/repos/KGRAG/runpod/build_image.sh, Docker required); keep it
# current on the Hub before building the sqlite variant.

IMAGE        = corpus-gutenberg
COMPOSE      = docker compose -f docker/docker-compose.yml
WORKER       = http://localhost:8000
IMAGE_SERVER = http://localhost:8090
SDXL_SERVER  = http://localhost:8091

# Apple `container` runtime settings (RUNTIME=apple only). Each container is
# its own VM — memory is an explicit upper bound, not shared with the host
# like Docker Desktop's single big VM, and the defaults are far too small for
# the worker (torch + embedder + 696K-node graph). Lazily allocated, so 8g
# does not pin 8 GB of RAM.
WORKER_NAME  = gutenberg-worker
CHAT_NAME    = gutenberg-chat
WORKER_MEM  ?= 8g
WORKER_CPUS ?= 6
CHAT_MEM    ?= 4g

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

.PHONY: init chunk-diaries build-diaries build-corpus setup build run image-server sdxl-server chat up stop down query logs clean docs

init:
	$(GUTENKG) init

chunk-diaries:
	$(GUTENKG) chunk-diaries

build-diaries: chunk-diaries
	$(GUTENKG) build-diaries --force

build-corpus: build-diaries
	$(GUTENKG) build-corpus

ifeq ($(RUNTIME),apple)

# ---------------------------------------------------------------------------
# Apple `container` runtime (macOS 26, Apple Silicon).
# `setup` installs the CLI if needed and starts its services (the once-per-
# boot step); build/run depend on it, so a clean clone works out of the box.
# host.docker.internal resolves to the host natively (container >= 0.9), so
# the same endpoint defaults as docker-compose.yml apply. docker/.env is
# sourced explicitly below to mirror compose's automatic .env loading.
# ---------------------------------------------------------------------------

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

build: setup
	container build -f docker/Dockerfile -t $(IMAGE):latest .

# Idempotent like `compose up`: a running worker is left alone (it takes a
# while to load the index), a stopped or stale one is replaced.
run: setup
	@if container list --quiet 2>/dev/null | grep -qx "$(WORKER_NAME)"; then \
		echo "Worker already running at $(WORKER)"; exit 0; \
	fi; \
	container delete -f $(WORKER_NAME) >/dev/null 2>&1 || true; \
	set -a; [ -f docker/.env ] && . docker/.env; set +a; \
	container run --detach --name $(WORKER_NAME) \
	  --memory $(WORKER_MEM) --cpus $(WORKER_CPUS) \
	  --publish 8000:8000 \
	  -e GUTENBERG_ROOT=/workspace/gutenberg \
	  -e EMBED_MODEL=BAAI/bge-small-en-v1.5 \
	  -e HANDLER_SECRET="$${HANDLER_SECRET:-}" \
	  -e VLLM_ENDPOINT_URL="$${VLLM_ENDPOINT_URL:-http://host.docker.internal:8080/v1}" \
	  -e VLLM_MODEL="$${VLLM_MODEL:-Qwen3-4B-Instruct-2507-MLX-8bit}" \
	  -e VLLM_API_KEY="$${VLLM_API_KEY:-}" \
	  -e OLLAMA_ENDPOINT="$${OLLAMA_ENDPOINT:-http://host.docker.internal:11434/v1}" \
	  -e OPENAI_API_KEY="$${OPENAI_API_KEY:-}" \
	  -e GUTENKG_IMAGE_ENDPOINT="$${GUTENKG_IMAGE_ENDPOINT:-$(IMG_ENDPOINT)}" \
	  -e IMAGE_ENDPOINT="$${GUTENKG_IMAGE_ENDPOINT:-$(IMG_ENDPOINT)}" \
	  -e IMAGE_STEPS="$${IMAGE_STEPS:-4}" \
	  $(IMAGE):latest \
	  python -u -m gutenberg_kg.serve.handler --rp_serve_api --rp_api_host 0.0.0.0
	@echo "Worker running at $(WORKER)"

# Chat reaches the worker container-to-container over the vmnet network
# (macOS 26 only — macOS 15 isolates containers from each other), addressed
# by the worker VM's IP pulled from `container inspect`.
chat: run
	@container delete -f $(CHAT_NAME) >/dev/null 2>&1 || true
	@WORKER_IP=$$(container inspect $(WORKER_NAME) | python3 -c 'import re,sys; print(re.search(r"\"address\"\s*:\s*\"(\d+\.\d+\.\d+\.\d+)", sys.stdin.read()).group(1))'); \
	set -a; [ -f docker/.env ] && . docker/.env; set +a; \
	container run --detach --name $(CHAT_NAME) \
	  --memory $(CHAT_MEM) \
	  --publish 8501:8501 \
	  -e KGRAG_ENDPOINT="http://$$WORKER_IP:8000" \
	  -e GUTENKG_IMAGE_ENDPOINT="$${GUTENKG_IMAGE_ENDPOINT:-$(IMG_ENDPOINT)}" \
	  -e IMAGE_ENDPOINT="$${GUTENKG_IMAGE_ENDPOINT:-$(IMG_ENDPOINT)}" \
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

build:
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
