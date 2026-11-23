# Release Notes -- v1.41.0

> Released: 2026-11-22

### Changed

- **KG pins:** kg-rag floor 0.19.0 and kgmodule-utils floor 0.31.0
  (pyproject, Dockerfile `KG_RAG_VERSION` and `KGMODULE_UTILS_VERSION`).
- **The image servers are imagewright's.** `make image-server` and
  `make sdxl-server` install
  [imagewright](https://github.com/Flux-Frontiers/imagewright) into
  `.venv-image` and `.venv-sdxl` (from `docker/requirements-image.txt` and
  `requirements-sdxl.txt`) and run `imagewright serve --backend flux` or
  `--backend sdxl`. They answer the same routes with the same bodies on the
  same ports, and FLUX runs on one thread. `make image-agent-install` writes a
  LaunchAgent that runs `imagewright serve`, and `make sdxl-fetch` downloads
  the weights through imagewright. To move a machine, run `make image-server`
  and restart the server; run `make image-agent-install` to rewrite its
  LaunchAgent. Images requested with `response_format=filepath` go to
  imagewright's temporary folder unless `IMAGE_OUTPUT_DIR` is set.
- **`gutenkg-image-server` and `gutenkg-sdxl-server` are aliases of
  `imagewright serve`** for this release, so a LaunchAgent written by an
  earlier release keeps starting a server. They keep the `0.0.0.0` bind
  default and the `MFLUX_SERVER_*` and `SDXL_SERVER_*` variables. In an
  environment without imagewright they exit and name the `make` target that
  rebuilds it. They are removed in the next release. `make kill`, `make down`
  and `make image-agent-install` stop both the aliases and `imagewright serve`.
- **The image client is imagewright.** `gutenkg imagine` and the
  `generate_image` and `corpus_imagine` MCP tools now find an image server
  and send it the request through imagewright, the fleet's image package,
  which is a new core dependency (click, httpx and pillow; no model stack).
  The request body, the `GUTENKG_IMAGE_STEPS` and `GUTENKG_IMAGE_SIZE`
  defaults, and the two ports probed are unchanged, and
  `image_gen.generate_via_server` and `discover_image_endpoint` keep their
  names and signatures. The MCP tools return the image bytes in memory
  instead of leaving a temporary file, and keep shrinking an oversized image
  until it fits the client's limit.
- **Importing an alias needs nothing outside the standard library.** A test
  blocks kgmodule-utils and imagewright and imports both aliases, so a
  `.venv-image` that lacks them still starts far enough to say what to run.

### Removed

- **The built-in FLUX and SDXL servers.** `serve/image_server.py` and
  `serve/sdxl_server.py` hold only the aliases. Their FastAPI apps, request
  models and model loading are gone, with their tests; imagewright's own
  tests cover the same behavior.
- **In-process generation in `image_gen`:** `generate`, `generate_auto`,
  `model_loaded`, `unload_model` and `_load_model`. Generate through an image
  server with `generate_via_server`, or with imagewright's `mflux-local`
  backend.
- **The `image` extra.** Nothing in the package needs FastAPI except the
  worker, whose container installs it; the tests get FastAPI from the `dev`
  group. Drop `--extras image` from install commands.

### Fixed

- **The `mkdocs-build` pre-commit hook passes with mkdocs-material 9.8.**
  Its "MkDocs 2" notice names `NO_MKDOCS_2_WARNING`, which the hook read as
  an unaccepted warning. `scripts/check_docs_build.py` now sets that
  variable for the build.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
