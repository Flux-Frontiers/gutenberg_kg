# corpus-gutenberg — build and run targets
#
# Typical workflow:
#   make build-corpus   — rebuild the DocKG + diary bundle (takes ~24 min)
#   make build          — build the Docker image (bakes bundle into image)
#   make run            — start the worker on http://localhost:8000
#   make chat           — start worker + Streamlit chat UI on http://localhost:8501
#   make query Q="..."  — fire a one-shot query against the running worker

IMAGE    = corpus-gutenberg
COMPOSE  = docker compose -f docker/docker-compose.yml
WORKER   = http://localhost:8000

.PHONY: build-corpus build run chat stop query clean

build-corpus:
	gutenkg build-corpus

build:
	docker build -f docker/Dockerfile -t $(IMAGE):latest .

run:
	$(COMPOSE) up -d gutenberg-worker
	@echo "Worker running at $(WORKER)"

chat:
	$(COMPOSE) --profile chat up -d
	@echo "Worker:  $(WORKER)"
	@echo "Chat UI: http://localhost:8501"

stop:
	$(COMPOSE) --profile chat down

query:
	@curl -s -X POST $(WORKER)/runsync \
	  -H "Content-Type: application/json" \
	  -d '{"input":{"query":"$(Q)","corpus":"all","k":5,"synthesize":false}}' | python3 -m json.tool

logs:
	$(COMPOSE) logs -f gutenberg-worker

clean:
	docker rmi $(IMAGE):latest 2>/dev/null || true
