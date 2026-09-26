# Release Notes -- v1.23.0

> Released: 2026-09-25

### Added

- **Knowledge Press Forest (web), three rounds before it moved to
  [knowledge_press](https://github.com/Flux-Frontiers/knowledge_press)** (#162,
  #163, #165; see Removed). Tree growth mirrors the Python viz3d
  (`kg_utils.viz3d.organic.colonize`, `grow_tree_geometry`): every chunk is a
  crown point, and at the Ultra leaf level each of the corpus's ~398k chunks is a
  leaf. Genres grow as five species with CC0 bark on swept meshes, in groves
  packed around the hub. Trees are placed by their wood, not a flat grid: each
  branch keeps 0.6 m of air from every other tree. At the hub stands a corpus
  redwood, 3.4 m of height per doubling of the corpus's chunks (63 m), with one
  limb per book reaching toward that book's tree; a book list (B) jumps to any
  tree. Kepler's *Mysterium Cosmographicum* stands as an exhibit in a roadside
  glade. The ring road is one loop that never crosses itself, with five spokes,
  and the guided tour follows it by pure pursuit. Also: a Web Worker for growth,
  per-grove render chunks, touch layouts, silent mode, a lantern trail that
  clears on arrival, and steering that no longer flips in reverse.

- **`make publish-worker-image` and `make pull-worker-image`: one multi-arch image for
  everyone.** `publish-worker-image` builds `linux/amd64` and `linux/arm64` into one image
  index and pushes it to `REGISTRY_IMAGE` (default
  `docker.io/egsuchanek/corpus-gutenberg`); under `RUNTIME=apple`,
  `container build` runs the amd64 half under Rosetta, and under Docker a
  `docker-container` buildx builder does it. `pull-worker-image` fetches the published
  image and tags it as the local one, so a new machine can skip `build-corpus`
  and `build`. The image holds no runtime-specific settings and no keys, so the
  same image runs under Docker or Apple `container`, on Apple Silicon or x86.
- **Image backend picker in the chat UI and the apps.** A new worker op,
  `image_backends`, reports which image backends the worker can use now: Local
  when its image server answers, OpenAI when it holds a key (the key is never
  returned). The Streamlit sidebar and the app's Settings > Illustrations list
  Auto plus only those. Auto follows the synthesis provider: OpenAI images
  for OpenAI, the local image server for oMLX or Ollama, and the worker's
  default when there is no local server or no provider. A choice the worker
  stops offering falls back to Auto.
- **Worker field in the Streamlit sidebar**, seeded from `KGRAG_ENDPOINT`, to
  match the app's Settings > Worker.
- **Setup docs for keys and LAN serving.** `docs/INSTALLATION.md` now covers
  where keys live and why a built image holds none, recreating the worker
  after a `docker/.env` change, and a checklist for serving the iOS and macOS
  apps from a Mac on the LAN, plus matching troubleshooting rows.
- **`make down-all`, and a guard against running two container runtimes.**
  With Docker Desktop and Apple's container services both running, other
  machines could ping the Mac but every inbound TCP connection hung, so the
  iPhone app could not reach the worker or image server. `make run`, `chat`
  and `up` now refuse to start while the other runtime is up
  (`ALLOW_BOTH_RUNTIMES=1` overrides). `make down-all` runs `make kill`, then
  stops Apple's container services and quits Docker Desktop.
- **`make ios-push-all`: app and corpus to every device in one step** (moved to
  knowledge_press with the apps). It builds
  once, then on each reachable device installs the app, copies the corpus and
  relaunches. `ios-deploy-all` still installs only the app. If a device drops
  off mid-copy, the target records it, moves on to the next device, and exits
  non-zero at the end with the list of devices to retry.

### Changed

- **Fleet dependency floors raised and relocked** (`kgrag_priv` sweep item 46):
  `kgmodule-utils` to `>=0.24.0` and `kg-rag` to `>=0.17.0`, in
  `pyproject.toml`, the Dockerfile ARGs and `runpod/requirements.txt`. The
  lock also moves `quiltwright` to 0.15.1.
- **Floors raised to the latest releases and relocked:** `quiltwright>=0.15.1`,
  `markdown>=3.11`, `plotly>=7.1.0`, `pyvistaqt>=0.13.1`, `streamlit>=1.64`,
  `uvicorn>=0.54.0`. `fastmcp` 4 and `rich` 15 stay behind their major-version
  caps.

### Fixed

- **Houdini's *Miracle Mongers and Their Methods* is now the Project Gutenberg
  edition.** The Internet Archive copy in `curiosities` was raw OCR of a library
  scan: page headers indexed as section headings, words split across line breaks,
  garbled text, a library date-due slip, and no author. It is replaced by
  Gutenberg #435 in `biography`. The IA catalog entry is commented out, so
  `curiosities` is now empty.
- **The worker's default image backend can be set again.** The docs said
  `IMAGE_BACKEND=openai` in `docker/.env` routes images to `gpt-image-1`, but
  neither compose nor `RUNTIME=apple` passed it into the worker, so it always
  used the local server. Both now pass `WORKER_IMAGE_BACKEND` from
  `docker/.env` in as the worker's `IMAGE_BACKEND`, plus `IMAGE_MODEL` and
  `IMAGE_API_KEY`. The new name keeps it apart from the Makefile's flux/sdxl
  `IMAGE_BACKEND`, which `make up IMAGE_BACKEND=sdxl` exports. A request's
  `image_backend` still overrides the default.
- **The MCP image tools called a model this package does not install.**
  `generate_image` and `corpus_imagine` both ran `image_gen.generate()`,
  which loads FLUX.2-Klein through mflux in-process, and mflux is
  deliberately not a dependency (its `transformers` pin conflicts with
  `pycode-kg`). Every call failed with `ModuleNotFoundError`. Both now call
  the running image server over HTTP, resolved as `gutenkg imagine` resolves
  it: `GUTENKG_IMAGE_ENDPOINT`, else the first of ports 8090 and 8091 that
  answers. With neither, the tool fails with "No image server found" and
  names `make up`.
- **`gutenkg imagine --query` no longer leaks a graph connection per diary.**
  The corpus lookup opened a `DocKG` for each diary searched and never closed
  it; it now opens each in a `with` block. In the long-running MCP server
  this was one leaked SQLite connection per diary per call.
- **Image docs match the CLI and the tools again.** `-r` is `--size
  WIDTHxHEIGHT`; the `--ratio 3:2` form the README and cheatsheet showed no
  longer exists and fails. The cheatsheet's MCP tool signatures take `size`,
  not `aspect_ratio`, its MCP config no longer sets model variables that only
  mattered for in-process generation, and `--endpoint` and
  `GUTENKG_IMAGE_ENDPOINT` are documented. `INSTALLATION.md` no longer says an
  empty endpoint means in-process generation.

### Removed

- **The apps moved to their own repo,
  [knowledge_press](https://github.com/Flux-Frontiers/knowledge_press).** The
  iOS/macOS app (`app/`) and Knowledge Press Forest (`web/knowledge-press-forest/`,
  now `web/` there) left with their history, along with the `ios-*` / `mac-*`
  Makefile targets, `.github/workflows/app.yml`, `docs/APP_INTERNALS.md` and
  `tests/test_app_version.py`, which kept the apps on the package's version
  (added this cycle in #161); they now version on their own.
  gutenberg_kg stays the producer: `gutenkg export-swift` and
  `docs/ON_DEVICE.md` (the pack format) remain here. `scripts/export_web_catalog.py`
  (`make export-web-catalog`) and `scripts/make_tokenizer_fixture.py` now write
  into a sibling knowledge_press checkout, or `KNOWLEDGE_PRESS_DIR`.
  `tests/test_synthesis_parity.py` reads the Swift prompts from there too, and
  CI checks knowledge_press out so it keeps running. `LICENSE` now covers the
  whole repository.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
