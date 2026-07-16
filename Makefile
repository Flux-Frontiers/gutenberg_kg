
# corpus-gutenberg — build and run targets
#
# Typical workflow:
#   make init           — fetch local ML models (spaCy, embedder); run once after clone
#   make chunk-diaries  — rebuild .diary/ chunks from committed .md (clean-clone step)
#   make build-diaries  — build .diarykg/ indices (prerequisite for build-corpus)
#   make build-corpus   — rebuild the DocKG + diary bundle (takes ~24 min)
#   make build          — build the Docker image (bakes bundle into image)
#   make run            — start the worker on http://localhost:8000
#   make image-server   — start the local FLUX image generation server on :8090
#   make sdxl-server    — start the local SDXL-Lightning image server on :8091
#   make chat           — start worker + Streamlit chat UI on http://localhost:8501
#   make up             — start everything: worker + chat UI + FLUX.2 image server (:8090)
#   make up IMAGE_BACKEND=sdxl  — start everything with the SDXL-Lightning server (:8091)
#   make down           - stop everything: worker + image servers + chat UI
#   make docs           — generate project docs into ./docs
#   make query Q="..."  — fire a one-shot query against the running worker

IMAGE        = corpus-gutenberg
COMPOSE      = docker compose -f docker/docker-compose.yml
WORKER       = http://localhost:8000
IMAGE_SERVER = http://localhost:8090
SDXL_SERVER  = http://localhost:8091

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

.PHONY: init chunk-diaries build-diaries build-corpus build run image-server sdxl-server chat up stop down query logs clean docs

init:
	$(GUTENKG) init

chunk-diaries:
	$(GUTENKG) chunk-diaries

build-diaries: chunk-diaries
	$(GUTENKG) build-diaries --force

build-corpus: build-diaries
	$(GUTENKG) build-corpus

build:
	docker build -f docker/Dockerfile -t $(IMAGE):latest .

run:
	$(COMPOSE) up -d worker
	@echo "Worker running at $(WORKER)"

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

query:
	@curl -s -X POST $(WORKER)/runsync \
	  -H "Content-Type: application/json" \
	  -d '{"input":{"query":"$(Q)","corpus":"all","k":5,"synthesize":false}}' | python3 -m json.tool

logs:
	$(COMPOSE) logs -f worker

clean:
	docker rmi $(IMAGE):latest 2>/dev/null || true

docs:
	cd src && pdoc --o ../site --logo "https://flux-frontiers.github.io/gutenberg_kg/logo.png" gutenberg_kg '!gutenberg_kg.serve.sdxl_server'
	cp assets/logos/logo_256.png site/logo.png
