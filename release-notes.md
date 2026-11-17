# Release Notes -- v1.37.0

> Released: 2026-11-17

### Added

- **The FLUX image server can run as a LaunchAgent.** `make image-agent-install`
  installs `local.gutenkg-image`, which starts `gutenkg-image-server` at login
  and restarts it if it exits; `make image-agent-uninstall` removes it. While it
  is installed, `make image-server` (and so `make up`) does not start a second
  copy.

### Changed

- **kgmodule-utils 0.30.1, and a refreshed lock.** The floor rises to
  0.30.1 for its accurate-scene image rewrite prompt, in pyproject, the
  Dockerfile ARG and `runpod/requirements.txt`. `poetry update` moved 113
  locked packages to current releases (among them huggingface-hub 2.4,
  openai 3.52, torch 2.15 and transformers 5.23); kg-rag, doc-kg and
  diary-kg were already current.
- **The install guide has a model-sizing table.** "Choosing a model" under
  Connecting a local LLM compares the 4B default with Qwen3.6-35B-A3B and
  two Qwen3.8-27B builds: weight size, answer and rewrite times, and which
  follow the image rewrite's accuracy rules. It also gives memory guidance
  for 16-24, 32 and 48 GB Macs. The default stays 4B.
- **`gutenkg imagine` and the MCP image tool use the shared rewrite prompt.**
  `image_gen.py` kept its own copy of the art-director prompt; it now imports
  `IMAGE_REWRITE_SYSTEM`, so the CLI, the MCP server and the worker rewrite
  with the same text. The prompt itself (accurate-scene rules) comes from
  kgmodule-utils.
- **The chat container restarts with Docker**, like the worker
  (`restart: unless-stopped`).

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
