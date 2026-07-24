# Release Notes — v1.11.0

> Released: 2026-07-24

GutenbergKG 1.11.0 makes the local stack fully Apple-native. The worker and
chat services now run end-to-end on Apple's own `container` runtime on Apple
Silicon — no Docker Desktop, no cloud, and no external LLM. Paired with local
MLX or Ollama models on the host, you can stand up the entire retrieval-plus-
chat experience with a single `make up RUNTIME=apple` and keep every byte on
your machine.

## What changed

**A purely local, Apple-Silicon environment.** The `RUNTIME=apple` path graduates
from experimental to the recommended way to run GutenbergKG locally on macOS 26.
Each service runs in its own lightweight VM under Apple's `container` CLI, and
with container CLI 1.1.0 the worker (`:8000`) and chat UI (`:8501`) publish to
`localhost` exactly like the Docker path — so nothing about how you reach the
services changes when you drop Docker Desktop.

**Reliable host-to-container networking.** Apple's runtime does not resolve
`host.docker.internal` and does not keep a stable vmnet subnet across CLI
versions, which previously caused the worker to silently see no LLM after a CLI
upgrade. The Makefile now rewrites host endpoints (oMLX, Ollama, image server)
to the vmnet gateway and **auto-detects** that gateway from the live network
instead of hardcoding it, so a `container` upgrade no longer breaks model
access.

**A self-contained worker image.** The default `docker/Dockerfile` builds from
`python:3.12-slim` and pulls everything from PyPI pins plus this checkout,
rather than extending a separately-published base image — a cleaner, more
reproducible build for both the Docker and Apple paths.

## Upgrading

Nothing changes for existing Docker users — `make up` still defaults to Docker.
To run natively on Apple Silicon, install Apple's `container` CLI **1.1.0 or
newer** (older 0.x builds lack `--publish` and use a different vmnet subnet),
make sure your host LLM servers bind `0.0.0.0` (not `127.0.0.1`), and run
`make up RUNTIME=apple`. The host gateway is detected automatically; override it
with `make APPLE_HOST_GW=… RUNTIME=apple` only if you run a non-default subnet.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
