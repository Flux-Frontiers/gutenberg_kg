
# corpus-gutenberg — build and run targets
#
# Typical workflow:
#   make build-diaries  — build .diarykg/ indices (prerequisite for build-corpus)
#   make build-corpus   — rebuild the DocKG + diary bundle (takes ~24 min)
#   make build          — build the Docker image (bakes bundle into image)
#   make run            — start the worker on http://localhost:8000
#   make image-server   — start the local FLUX image generation server on :8090
#   make chat           — start worker + Streamlit chat UI on http://localhost:8501
#   make up             — start everything: worker + image server + chat UI
#   make docs           — generate project docs into ./docs
#   make query Q="..."  — fire a one-shot query against the running worker

IMAGE        = corpus-gutenberg
COMPOSE      = docker compose -f docker/docker-compose.yml
WORKER       = http://localhost:8000
IMAGE_SERVER = http://localhost:8090

.PHONY: build-diaries build-corpus build run image-server chat up stop down query logs clean docs

build-diaries:
	gutenkg build-diaries --force

build-corpus: build-diaries
	gutenkg build-corpus

build:
	docker build -f docker/Dockerfile -t $(IMAGE):latest .

run:
	$(COMPOSE) up -d gutenberg-worker
	@echo "Worker running at $(WORKER)"

image-server:
	@if [ ! -x .venv-image/bin/python ]; then \
		echo "Creating .venv-image for isolated image dependencies ..."; \
		python3 -m venv .venv-image; \
	fi
	@.venv-image/bin/python -m pip install --quiet --upgrade pip
	@.venv-image/bin/python -m pip install --quiet -r docker/requirements-image.txt
	@echo "Starting FLUX image server on $(IMAGE_SERVER) (background, .venv-image) ..."
	MFLUX_SERVER_HOST=0.0.0.0 .venv-image/bin/python docker/image_server.py &

chat:
	$(COMPOSE) --profile chat up -d
	@echo "Worker:  $(WORKER)"
	@echo "Chat UI: http://localhost:8501"

start up:
	@echo "Starting worker + chat (Docker) ..."
	$(COMPOSE) --profile chat up -d
	@echo "Starting FLUX image server in isolated .venv-image ..."
	$(MAKE) image-server
	@echo ""
	@echo "Worker:       $(WORKER)"
	@echo "Image server: $(IMAGE_SERVER)"
	@echo "Chat UI:      http://localhost:8501"
	@echo ""
	@echo "Run 'make stop' to shut down Docker services."
	@echo "Kill the image server with: pkill -f image_server.py"

stop down:
	$(COMPOSE) --profile chat down
	-pkill -f image_server.py 2>/dev/null || true

query:
	@curl -s -X POST $(WORKER)/runsync \
	  -H "Content-Type: application/json" \
	  -d '{"input":{"query":"$(Q)","corpus":"all","k":5,"synthesize":false}}' | python3 -m json.tool

logs:
	$(COMPOSE) logs -f gutenberg-worker

clean:
	docker rmi $(IMAGE):latest 2>/dev/null || true

docs:
	cd src && pdoc --o ../docs --logo ./logo.png gutenberg_kg
