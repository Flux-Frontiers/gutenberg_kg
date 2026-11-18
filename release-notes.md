# Release Notes -- v1.38.0

> Released: 2026-11-17

### Added

- **`make bootstrap` can set up the LLM provider.** A new last step sets up
  the provider named with `PROVIDER=omlx|openai|anthropic|none`, or asked for
  on a terminal. For oMLX it checks that oMLX is installed and running, that
  its port matches `VLLM_ENDPOINT_URL` and that `VLLM_API_KEY` is its key, then
  runs `scripts/setup_models.py`. For OpenAI and Anthropic it asks for the key,
  checks it against the provider's model list and writes it to `docker/.env`.
  `docker/.env` is backed up first and keys are never printed. Without a
  provider, as before, the backends are only reported.
- **`make models` sets up the LLM that fits this Mac.** `scripts/setup_models.py`
  picks a tier from the Mac's memory (or `TIER=`, or `MODEL=` for any MLX
  repo) and downloads that tier's model into `~/.omlx/models`. It has oMLX
  rescan (a model oMLX already serves is not downloaded again), then tests
  the model with one short request. Only if that passes
  does it write `VLLM_MODEL`, `MOOT_MODEL` and `IMAGE_IDLE_UNLOAD_S` to
  `docker/.env`, after a backup. A model oMLX refuses fails with oMLX's own
  message and the next tier down. Then it pulls the worker image. Docker's
  memory and oMLX's memory guard are reported, not changed. The tiers live in
  `scripts/model_tiers.json`: the 4B MLX build for 16 GB, `Qwen3-8B-MLX-4bit`
  for 18-24 GB, the 27B for 32-36 GB and A3B for 48 GB or more.
- **The FLUX image server can unload when idle.** `IMAGE_IDLE_UNLOAD_S`
  frees FLUX's 12-15 GB after that many idle seconds; the next render loads it
  again. It is off by default; `make models` sets 300 on Macs of 24 GB or less,
  and `make image-server` and `make image-agent-install` read it from
  `docker/.env`. `/health` now reports `loaded` and `idle_unload_s`.
- **`MOOT_MODEL` picks the moot model on oMLX.** Moots used Qwen3.8-27B-4bit
  unconditionally, which a 24 GB Mac cannot load beside FLUX. Empty keeps the
  27B.
- **The install guide has a "Small Macs (16-24 GB)" section.** It gives
  measurements from a 24 GB Mac: the 8B answers in 2-6 s and stays near 3 s
  with FLUX loaded, while renders slow under swapping. The 27B was refused
  and A3B cannot fit. It also says what to free first.

### Fixed

- **`docker/.env` and its backups are owner-only.** `make bootstrap`,
  `make models` and `scripts/rotate_omlx_key.py` write API keys into
  `docker/.env`, which Docker Compose needs in plain text, and the files were
  readable by every account on the machine (mode 644). They now write it, and
  every backup they make, with mode 600. To fix an existing file:
  `chmod 600 docker/.env docker/.env.bak-*`.
- **kgmodule-utils 0.30.2, and a lock that installs one cuBLAS.** The floor
  rises to 0.30.2 in `pyproject.toml`, `runpod/requirements.txt` and the
  Dockerfile. That release sends each synthesis key only to its own backend.
  The lock is regenerated with Poetry 2.4.3: the previous one, written by
  Poetry 2.5.1, marked the second `nvidia-cublas` and `nvidia-cuda-nvrtc`
  entries for all of Linux, so a Linux x86_64 install from the lock got both
  versions. The worker image was not affected, since it installs CPU torch
  with pip. `tests/test_lock_markers.py` now fails when the lock would
  install two versions of a package on Linux x86_64, macOS arm64 or Windows.
- **A diary-routing test no longer writes to `~/.kgrag`.**
  `test_run_ingest_routes_diaries_to_diary_pipeline` now passes a temporary
  registry path to `run_ingest`, so it no longer creates the real KGRAG
  registry folder, and it passes with no home folder.
- **An LLM that returns nothing is now an error.** When oMLX refused to load
  a model, the worker answered with an empty `synthesis` and no
  `synthesis_error`, because kg_utils turns every backend failure into
  `None`. The worker now reports that the model returned no answer and may
  not fit in memory.
- **`check_pins.py` checks the default model.** The compose file, the
  Makefile, `.env.example` and `image_gen._DEFAULT_VLM_MODEL` must name
  `model_tiers.json`'s default, and the install guide must name every tier's
  model.
- **`make image-agent-install` no longer fails with "Bootstrap failed: 5".**
  It now waits for the old agent to unload before loading the new one.
- **The FLUX image server starts again.** 1.37.0's `image_gen.py` imported
  the shared rewrite prompt at module level, which pulls in kgmodule-utils.
  The image server's `.venv-image` does not install it, so
  `gutenkg-image-server` exited on import and the LaunchAgent restarted it in
  a loop; the apps reported "Network is unreachable" on Render. The import
  now sits inside `vlm_rewrite()`, the only caller, and a test imports
  `image_gen` with kg_utils blocked.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
