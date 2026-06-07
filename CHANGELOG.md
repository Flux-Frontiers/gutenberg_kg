# Changelog

All notable changes to GutenbergKG are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added

- **`docker/image_gen.py` — standalone image generation module in Docker** — new
  file copied directly into `/app/image_gen.py` inside the container (no
  `gutenberg_kg` package import required). Provides four entry points:
  - `generate()` — local Flux2Klein generation on Apple Silicon via mflux.
  - `generate_via_server()` — HTTP client for a running mflux-serve instance;
    requires only `httpx` + `pillow`, safe from Linux containers.
  - `generate_auto()` — resolves server URL from `IMAGE_ENDPOINT` env var,
    falls back to local generation.
  - `vlm_rewrite()` — rewrites historical corpus text into a visual image-generation
    prompt via an OpenAI-compatible VLM; strips `<think>` blocks before returning.

- **RunPod handler: `corpus` routing** — `handler()` now accepts a `corpus` field
  (`all`, `gutenberg`, or any registered genre slug). Genre queries apply 6× query
  expansion and post-filter by genre tag from the enriched catalog, matching the
  docker handler behavior.

- **RunPod handler: `op=models` operation** — pass `{"input": {"op": "models"}}`
  to list models available at the configured vLLM endpoint without running a query.

- **RunPod handler: `HANDLER_SECRET` authentication** — optional shared secret; when
  `HANDLER_SECRET` is set, all requests must include `{"secret": "<value>"}`.

- **RunPod handler: `_attach_content()` and `_enrich_catalog()`** — post-processing
  pipeline attaches full node text from SQLite (by `node_id`) and joins
  author/title/genre from `catalog.json` onto each hit before synthesis.

- **RunPod handler: `_load_catalog()`** — loads `catalog.json` sidecar at startup
  for O(1) metadata enrichment on every request.

- **RunPod handler: `SYNTH_MAX_K` env var** — caps passages fed to synthesis
  (default 12), preventing context-window overflows for large `k` queries.

- **RunPod handler: timing fields in response** — `search_ms` and `synthesis_ms`
  added to every response payload.

- **Chat UI: global resolution control** — sidebar "Image" section with a
  Preview / Standard / Full selector (replacing the per-result inline aspect-ratio
  selectbox). Each tier maps six aspect ratios to pixel dimensions
  (Preview ~768 px wide, Standard ~1152 px wide, Full ~1536 px wide).

- **Chat UI: timing display** — `search_ms`, `synthesis_ms`, VLM rewrite latency,
  and image generation latency are shown in captions so pipeline bottlenecks are
  immediately visible.

- **`.env.example`: oMLX and Ollama setup instructions** — rewritten with
  step-by-step sections for the two recommended local LLM backends (oMLX on Apple
  Silicon and Ollama cross-platform), including port notes and API-key guidance.

### Changed

- **`docker/Dockerfile`** — `COPY docker/image_gen.py /app/image_gen.py` added so
  the standalone module is available at `/app/image_gen.py` inside the container.
  `chat.py` and `image_server.py` both import it via a `sys.path` insert rather
  than the `gutenberg_kg` package.

- **`IMAGE_ENDPOINT` env var standardised** — renamed from `GUTENKG_IMAGE_ENDPOINT`
  across `docker/chat.py`, `docker/docker-compose.yml`, `docker/handler.py`, and
  the `.env.example`. `IMAGE_STEPS` (not `GUTENKG_IMAGE_STEPS`) is now the
  canonical name in `image_server.py` as well.

- **`docker-compose.yml`: `extra_hosts` added** — `host.docker.internal:host-gateway`
  added to both `gutenberg-worker` and `gutenberg-chat` services so host services
  (oMLX on :8080, mflux-serve on :8090) are reachable from inside the container on
  Linux Docker hosts.

- **Default synthesis model updated** — `Qwen3-8B-MLX-4bit` → `Qwen3-4B-Instruct-2507-MLX-8bit`
  in `docker/handler.py`, `docker/docker-compose.yml`, and `docker/.env.example`.

- **RunPod handler `_synthesize()` reworked** — uses full node content instead of
  summaries; builds richer context headers (genre | author | title); applies
  `SYNTH_MAX_K` cap; supports per-request `model` override; disables thinking mode
  (`think: false`, `enable_thinking: false`); strips `<think>` blocks from output;
  uses `VLLM_API_KEY` (falling back to `RUNPOD_API_KEY`); returns `None` on error
  instead of raising.

- **RunPod handler: `RUNPOD_API_KEY` → `VLLM_API_KEY`** — module-level constant
  renamed; legacy `RUNPOD_API_KEY` env var retained as fallback for backward compat.

- **`runpod/test_local.py`** — `_add_sibling_src_to_path()` helper auto-discovers
  sibling `kgrag/src` trees so the smoke test works outside Docker. Added
  `op=models` and invalid-corpus test cases. Import error surfaces a clear message
  with `pip install` hints.

### Fixed

- **Chat UI `_query_worker()` error parsing** — error responses from the worker may
  carry `{"error": "<json-string>"}` or `{"error": {...}}`. Parser now handles both
  forms (JSON-decode string first, then fall through to dict extraction), preventing
  an `AttributeError: 'str' object has no attribute 'get'` crash on worker errors.

### Added

- **`scripts/bench_synthesis.py` — synthesis latency benchmark** — standalone script
  that hits the RunPod handler's `/runsync` endpoint with `synthesize=true` and
  reports per-query `search_ms`, `synthesis_ms`, and wall-clock time with aggregate
  stats (avg/min/max) and answer length.

- **`IMAGE_STEPS` env var — configurable image inference steps** — replaces the
  hardcoded default of 4 steps in `docker/handler.py`, `docker/image_server.py`,
  and `docker/chat.py`. Propagated through `docker-compose.yml` (`IMAGE_STEPS: ${IMAGE_STEPS:-4}`)
  on both the worker and chat services. Documented in `.env.example` and `.env`.
  - `image_server.py`: `ImageGenRequest` gains `num_inference_steps` field; passed
    to `image_gen.generate()`, falling back to `GUTENKG_IMAGE_STEPS`.
  - `chat.py`: reads `IMAGE_STEPS` and forwards `num_inference_steps` in every
    `/v1/images/generations` POST to the image server.
  - `handler.py`: `IMAGE_STEPS` module-level constant used as default in `_imagine`.

### Added

- **`gutenkg imagine` — corpus-grounded image generation CLI** — new subcommand
  (`src/gutenberg_kg/cli/cmd_imagine.py`) that generates images from a text prompt
  or from corpus content retrieved via DocKG / DiaryKG.
  - `gutenkg imagine "prompt"` — direct text-to-image via local FLUX.2-Klein (MLX).
  - `gutenkg imagine --query "great fire" --book pepys` — retrieves relevant diary
    chunks, rewrites them into a visual scene description via a local VLM (OpenAI-
    compatible, default Qwen3), then generates the image.
  - `--ratio` (default `3:2`), `--seed`, `--steps` (default 4), `--output`, and
    `--open/--no-open` flags round out the options.
  - `--corpus-only` dumps retrieved corpus text without generating; `--no-vlm` skips
    the rewrite step (corpus text passed directly to FLUX).
  - Falls back to the prose `bundles/gutenberg-all/.dockg` bundle if no diary KG
    matches the query.

- **`src/gutenberg_kg/image_gen.py` — image generation library** — module wrapping
  FLUX.2-Klein (mflux / MLX) with three call paths:
  - `generate()` — local generation on Apple Silicon; caches the loaded model
    between calls.
  - `generate_via_server()` — HTTP client for a running `mflux-serve` instance;
    requires only `httpx` + `pillow`, safe from Linux containers.
  - `generate_auto()` — resolves server URL from `GUTENKG_IMAGE_ENDPOINT` env var
    and falls back to local generation.
  - `vlm_rewrite()` — rewrites historical corpus text into a visual image-generation
    prompt via an OpenAI-compatible local VLM; strips `<think>` blocks before
    returning the cleaned prompt.
  - Controlled via `GUTENKG_IMAGE_MODEL`, `GUTENKG_IMAGE_STEPS`, and
    `GUTENKG_IMAGE_ENDPOINT` environment variables.

- **`src/gutenberg_kg/mcp_server.py` — GutenbergKG MCP server** — FastMCP server
  (`gutenkg-mcp` entry point) exposing two tools for Claude Code / Cursor:
  - `generate_image(prompt, aspect_ratio, seed, steps)` — direct text-to-image.
  - `corpus_imagine(query, book, extra_prompt, aspect_ratio, seed, steps)` — corpus
    retrieval + VLM rewrite + image generation in one MCP call.
  Auto-compresses output to JPEG if the PNG exceeds the 5 MB MCP transport limit.

- **`docker/image_server.py` — in-process FLUX image generation server** — thin
  FastAPI wrapper around `image_gen.generate()` that pre-loads the Flux2Klein model
  at startup and keeps it resident between requests. Exposes
  `GET /v1/models` and `POST /v1/images/generations` (OpenAI Images API shape).
  Runs on `:8090` by default; configured via `GUTENKG_IMAGE_MODEL`,
  `GUTENKG_IMAGE_STEPS`, `MFLUX_SERVER_HOST`, and `MFLUX_SERVER_PORT`.

- **`.mcp.json` — project MCP configuration** — declares the `gutenkg` and
  `paperbanana` MCP servers for Claude Code / Cursor; wires `GUTENKG_IMAGE_MODEL`,
  `GUTENKG_IMAGE_STEPS`, VLM provider, and image provider environment variables so
  both servers pick up the correct local endpoints without further user config.

- **`imagine` optional-dependency group** — `mflux>=0.9.0`, `fastmcp>=2.0`, and
  `structlog>=24.0` grouped under `[project.optional-dependencies] imagine`; install
  with `pip install -e ".[imagine]"` or `poetry install --extras "imagine"`. Added
  to `all`.

### Changed

- **`diary-kg` promoted to a core dependency** — `diary-kg>=0.92.6` added to
  `[project.dependencies]`; was previously only in the `kgdeps` extra. Also added
  to `kgdeps` and `all` extras for completeness.

- **`gutenkg-mcp` entry point added** — `pyproject.toml` now registers
  `gutenkg-mcp = "gutenberg_kg.mcp_server:main"` alongside `gutenkg`.

- **`tool.pycodekg.include` extended** — `docker` directory added to the PyCodeKG
  source-scan list so `image_server.py` and other Docker utilities are indexed in
  the code KG.

- **Makefile — image server and `up` targets** — added `IMAGE_SERVER = http://localhost:8090`
  variable, `image-server` target (starts `docker/image_server.py` on `:8090`), and
  `up` target (starts worker + image server + chat UI together). Workflow comment
  block updated to list all entry points.

- **Docker stack updated for image generation** — `docker/Dockerfile`,
  `docker/handler.py`, `docker/chat.py`, and `docker/docker-compose.yml` updated to
  wire the image server into the standalone deployment stack and route image
  generation requests through the handler.

- **Documentation refreshed** — `docs/CHEATSHEET.md`, `docs/DIARY_INGEST_HANDOFF.md`,
  `docs/ingestion-pipeline.md`, and `README.md` updated to document the `imagine`
  command, MCP server setup, and image server workflow.

### Added

- **`gutenkg build-corpus` — consolidated single-index builder** — new subcommand
  that walks the entire `corpus/` tree once and writes a *single* DocKG
  (`graph.sqlite` + `lancedb` + `catalog.json`) to the gitignored
  `bundles/<name>/.dockg/`, rather than the per-book federated indices that
  `ingest` builds. This is the artifact intended for a standalone "pull-and-run"
  Docker image.
  - `--genre` (repeatable) builds a subset (`gutenberg-<genre>`); default is all
    18 genres (`gutenberg-all`). `--output` overrides the bundle name.
  - The walk stays rooted at `corpus/` (subset selection is done via directory
    exclude), so every node's `file_path` stays genre-prefixed — **genre is
    recoverable at query time with no schema change**. `authors/`, `diaries/`,
    and DocKG `SKIP_DIRS` are pruned.
  - A `catalog.json` sidecar maps `<genre>/<book>` → author, title, Gutenberg ID,
    and author dates (parsed from each book's `reference.md` via
    `authors.parse_reference`), letting a handler join author/title onto a hit by
    its `file_path` prefix. Front-matter is already tagged `content_type='reference'`
    for query-time filtering.
  - `--similar-k` (default 8) caps SIMILAR_TO out-edges per chunk; `--no-similar`
    disables discovery — preventing the unbounded edge blow-up of an unconfigured
    corpus-wide build. `--workers`, `--dry-run`, and `--quiet` round out the flags.

- **42 corpus texts across 5 new genres** — biography, drama, letters,
  natural-history, and travel. Each title is stored as a Markdown-converted
  `.md` file plus a `reference.md` metadata stub.

  | Genre | Count | Notable titles |
  |---|---|---|
  | `biography` | 11 | Franklin, Douglass, Rousseau, Augustine, Grant Vol. 1, Henry Adams, Boswell's Johnson |
  | `drama` | 11 | Ibsen (3), Marlowe (2), Shaw (2), Chekhov (2), Wilde, Webster |
  | `letters` | 7 | Byron, Keats, Pliny, Chesterfield, Voltaire, Montagu |
  | `natural-history` | 7 | Darwin × 3 (Origin, Descent, Beagle), Huxley, Faraday, Wallace |
  | `travel` | 6 | Twain, Marco Polo, Isabella Bird, Mungo Park, Dana, Melville |

- **Two-pane Rich display for `gutenkg ingest`** — progress bar (top) and live
  scrolling build log (bottom) replace flat terminal output during corpus builds.
  Uses OS-level `os.dup2` stdout redirect so all output — including Rich `Console()`
  instances inside doc_kg — is captured into the log panel. The progress bar uses a
  yellow colour scheme for accessibility. Refreshes at 4 Hz.

- **`--quiet` flag for `gutenkg ingest`** — suppresses per-book DocKG build output
  (parsing, embedding, and indexing progress bars) while keeping the two-pane overall
  display. Wired through `IngestOptions`, `build_dockg()`, and all three `DocKG` build
  phases (`build_graph`, `build_embeddings`, `build_index_from_cache`).

### Changed

- **`gutenkg ingest` status icons** — replaced double-width Unicode emoji (`✅`, `⚪`,
  `⚠️`) in the job summary box with ASCII tokens (`[ok]`, `[~]`, `[!]`) to prevent
  column misalignment in fixed-width terminal output.

- **`rich` promoted to a core dependency** — `rich>=13.0.0` added to
  `[project.dependencies]`. It was already imported by `gutenkg ingest`'s two-pane
  display but only present transitively.

- **`doc-kg` minimum version raised to 0.15.5** — 0.15.5 is the first release
  that exposes `similar_max_degree` through `DocKG.build_index_from_cache` and
  `DocKG.build_index`; earlier versions silently drop the cap.

- **`docker/handler.py` diary filter** — `corpus=diary` routing added.
  Queries with `corpus=diary` filter results to diary KGs (excluding the main
  `gutenberg` DocKG), with 6× query expansion matching the existing
  `genre_filter` behaviour. Diary result cards now include the diary slug from
  a `_DIARY_META` lookup so the client can display the source diary title.

- **`GENRE_STRATEGY` cleared for sacred-texts** — removed `{"sacred-texts":
  "verse"}` from `build_corpus.py`. Only the KJV Bible (ID 10) uses `N:M`
  chapter:verse format; `VerseChunker` auto-detects it via the >10%-line heuristic.
  All other sacred texts (Quran, Dhammapada, Bhagavad Gita, Tao Te Ching,
  Upanishads, Analects) are prose translations with no verse markers and should use
  semantic chunking. Forcing verse strategy on them produced malformed chunks.

- **README refreshed to v1.4.0** — version badge, corpus totals (245 books /
  18 genres / 1.24M nodes / 5.32M edges), the per-genre table, and the citation
  metadata updated to reflect the expanded corpus.

### Added

- **Standalone Docker image** (`docker/`) — self-contained RunPod/Docker worker
  that bakes the pre-built `bundles/gutenberg-all/` corpus into the image so it
  starts without any network access or corpus build step at runtime.
  - `docker/Dockerfile` — extends `egsuchanek/kgrag-worker` with `doc-kg`,
    `diary-kg`, pre-downloaded `BAAI/bge-small-en-v1.5`, and `HF_HUB_OFFLINE=1`
    so HuggingFace is never reached at inference time.
  - `docker/handler.py` — RunPod/FastAPI handler that registers the consolidated
    DocKG (245 books) and 4 DiaryKG indices on startup; routes `/runsync` and
    `/runsync/query` with optional synthesis via an OpenAI-compatible endpoint.
  - `docker/chat.py` — Streamlit chat UI (The Knowledge Press) wired to the
    worker; genre-filter sidebar, suggested queries, result cards with relevance
    scores, and optional LLM synthesis.
  - `docker/docker-compose.yml` — `gutenberg-worker` service plus optional
    `--profile chat` for the Streamlit UI.
  - `docker/.env.example` — template for `HANDLER_SECRET`, `VLLM_ENDPOINT_URL`,
    `VLLM_MODEL`, and `VLLM_API_KEY`.
  - `Makefile` — `build-corpus / build / run / chat / stop / query / logs`
    targets for the full build-then-run workflow.

- **`gutenkg build-diaries` — diary DocKG index builder** — new subcommand
  (`src/gutenberg_kg/build_diaries.py` + `cli/cmd_build_diaries.py`) that
  builds `.diarykg/` DocKG indices for diary corpora under `corpus/diaries/`.
  Prerequisites the `gutenkg build-corpus` bundle stage, which copies these
  indices verbatim.
  - `--diary NAME` (repeatable) builds a subset; default is all discovered
    diary directories. Must match an exact subdirectory name under
    `corpus/diaries/`.
  - Build flags fixed to match the Docker image: `sentence_group` chunking,
    `--no-similar` (chronologically dense entries produce SIMILAR_TO noise),
    `BAAI/bge-small-en-v1.5` embedding model.
  - Skips diaries with an existing `.diarykg/graph.sqlite`; use `--force` to
    rebuild. `--workers`, `--dry-run`, and `--quiet` match the `ingest` flags.

- **`docs/DIARY_INGEST_HANDOFF.md`** — comprehensive diary ingestion reference
  documenting the `.diary/` chunk format (YAML frontmatter with `timestamp`,
  `category`, `topics`), concrete `dockg build` commands for all four diaries
  (Pepys, Evelyn Vol 1 & 2, Boswell Hebrides), expected node/edge counts, how
  `bundle_diaries()` picks up indices, handler slug derivation, and a
  troubleshooting table. Serves as the handoff document for Docker build agents
  that need to pre-build diary indices from scratch.

- **`gutenberg-diaries` in `GENRE_LABELS`** — diaries are registered as a KG
  corpus but are not in `genres.json` / `ALL_GENRES` (they are built by
  DiaryKG, not the standard Gutenberg pipeline).  Adding the label explicitly
  means `gutenkg status` and snapshot commands show the diary corpus correctly.

### Removed

- **`handoff.md`** — removed stale top-level handoff notes.

### Fixed

- **SIMILAR_TO edge hub-chunk explosion** — `similar_max_degree` was silently
  dropped before reaching the BLAS matmul in `_discover_similar_edges` because
  neither `DocKG.build_index_from_cache` nor `DocKG.build_index` accepted the
  parameter.  Result: uncapped edges produced hub chunks with degree 100+
  (max observed: 111 in Pride and Prejudice), inflating `_semantic_rank_boost`
  to 88× and drowning topical/entity signals.  Fix: wired `similar_max_degree`
  through the full `kg.py` API chain; `gutenkg ingest` now defaults to 8 (the
  evaluated cap); `build-corpus` inherits the same default via
  `BuildCorpusOptions.similar_max_degree`.  Re-evaluated on 12 books / 34
  labeled queries: nDCG +10.3%, MRR +3.4%, Recall +17.7% vs no-SIMILAR baseline
  (previous memory entry of +5.6% was measured against the uncapped bug).
  Requires `doc-kg>=0.15.5`.

- **`gutenkg status` / `snapshot save` under-reporting corpus** — `GENRE_LABELS`
  in `corpus.py` was a hardcoded dict missing all 5 new genres; both commands
  silently reported 203 books / 1,017,563 nodes / 4,427,515 edges instead of the
  correct 245 / 1,236,169 / 5,321,000. Fixed by making `GENRE_LABELS` dynamic:
  it is now built from `genres.ALL_GENRES` (sourced from `corpus/genres.json`),
  so new genres registered via `gutenkg genres add` are automatically visible
  to `status` and `snapshot` without any code change.

- **Three wrong Gutenberg IDs in `science-fiction` catalogs** — wrong texts were
  being downloaded and indexed:
  - *The Lost World*: `29808` → `139`
  - *The Gods of Mars*: `364` → `64`
  - *Pellucidar*: `4358` → `605`

- **RunPod build pod prefers curated catalog files** — `runpod/build_kg.py` now
  checks for `scripts/catalogs/<genre>.txt` before falling back to
  `fetch-genre --max-results 200`, so pod corpora match the local curated set.

- **Sacred-texts catalog corrections** — two corpus entries were wrong and one
  needed a translator label fix:
  - ID 1097 (labelled "Torah / Tanakh") actually downloaded *Mrs. Warren's
    Profession* by George Bernard Shaw — a catalog ID collision. Replaced with
    Dhammapada (ID 2017, F. Max Müller translation), the canonical Buddhist
    wisdom text.
  - ID 2800 (labelled "Quran — Yusuf Ali translation") is the Rodwell
    translation; label corrected to "The Quran (Rodwell translation)".
  - Both corpus folders deleted and re-downloaded with correct content and
    labels; `scripts/catalogs/sacred-texts.txt` updated accordingly.
  - `scripts/catalogs/ancient-classical.txt` comment clarified: Bible KJV (#10)
    lives in sacred-texts, not ancient-classical.

- **`docker/chat` profile missing Python dependencies** — `make chat` failed
  with `exec: "streamlit": executable file not found` because `streamlit` and
  `httpx` (imported by `chat.py`) were absent from the Dockerfile pip install
  line. Both added; image must be rebuilt with `make build`.

---

## [1.3.0] - 2026-05-16

### Added

- **`gutenkg snapshot prune`** — new subcommand that removes vestigial snapshots carrying
  no new metric information. Cleans three categories: metric-duplicates (interior snapshots
  with identical metrics), broken entries (manifest entries whose JSON file is missing), and
  orphaned files (JSON files on disk not referenced by the manifest). Oldest (baseline) and
  newest (latest) snapshots are always kept. `--dry-run` reports what would be removed
  without deleting anything.

- **`gutenkg re-register`** — new CLI command (`cmd_reregister.py` + `run_reregister()` in
  `ingest.py`) that re-registers all built books in the KGRAG registry with the correct
  `kind=gutenberg` without rebuilding DocKGs. Idempotent and safe to run on any machine,
  including fresh clones where the registry is empty. Accepts `--genre`, `--dry-run`, and
  `--registry` flags. Skips books that are already correctly tagged and books with no built
  `.dockg/graph.sqlite`.

### Changed

- **`gutenkg snapshot`** — rewritten to use `GutenbergSnapshotManager` (backed by
  `kg_utils.snapshots.SnapshotManager`). Snapshots are now keyed by git tree hash and
  stored alongside a `manifest.json` index with per-entry deltas vs. previous and baseline.
  Subcommands updated: `save` gains `--force` and `--json`; `list` gains `--branch`,
  `--limit`, and `--json`; `show` is key-addressable (defaults to latest); `diff` accepts
  explicit keys or auto-selects last two, with `--json` output.

- **`tests/test_cmd_snapshot.py`** — fully rewritten for the new `GutenbergSnapshotManager`
  API (37 tests). Covers help text, `list`/`show`/`diff`/`prune`/`save` CLI paths, error
  cases, JSON output, round-trip save→list and save→show flows. Uses a `fake_registry`
  fixture (in-memory SQLite) for `save` tests; all others use a manifest-writing helper so
  no live registry is required.

### Fixed

- **`gutenkg snapshot diff` delta display** — all metrics showed `(+0)` because `_line()`
  looked up the computed delta using `total_books`/`total_nodes` keys while
  `_compute_delta_from_metrics` stores them as `books`/`nodes`. Fixed by computing the
  delta directly as `mb − ma` from the already-fetched metric values, eliminating any
  dependency on delta dict key names.

- **`ingest.py` `register_book`** — changed `KGKind.from_str("doc")` to `KGKind.GUTENBERG`
  so all new ingest runs register books with the correct kind. Previously all 203 Gutenberg
  books were registered as `kind=doc` instead of `kind=gutenberg`.

---

## [1.2.2] - 2026-05-16

### Added

- **`runpod/`** — RunPod serverless deployment package for GutenbergKG semantic
  search. Includes `handler.py` (RunPod serverless handler with KGRAG
  orchestration), `Dockerfile` (bakes `BAAI/bge-small-en-v1.5` into the image
  for cold-start-free embedding), `build_image.sh` (builds local wheels +
  Docker image), `build_kg.py` (remote index builder for RunPod dev pods),
  `push_indices.sh` (rsyncs local indices to Network Volume), `test_local.py`
  (local smoke test without Docker), and `test_input.json` (RunPod local worker
  test payload).

- **`.runpod/hub.json`** — RunPod Hub endpoint metadata for the GutenbergKG
  semantic search worker (name, description, env var schema, resource config).

- **`.runpod/tests.json`** — RunPod Hub automated test cases (stoic virtue,
  redemption in literature, nature of justice).

- **`reports/ingest_2026-05-15_234014.md`** — full ingest report from the
  384-dim index rebuild across all 203 Gutenberg books.

### Changed

- **`ingest.py` — embedder surfaced in job summary** — both the terminal box
  and the saved Markdown report now include an `Embedder:` row showing the
  sentence-transformer model used (e.g. `BAAI/bge-small-en-v1.5`). Captured
  from the first genre's shared embedder; `print_summary` and `save_summary`
  accept a new optional `embed_model` parameter.

- **`pyproject.toml`** — pinned `transformers>=5.8.1` to resolve
  `huggingface-hub 1.x` compatibility; `transformers 5.8.0` incorrectly
  rejected `huggingface-hub>=1.0` at import time.

---

## [1.2.1] - 2026-05-13

### Changed

- **`gutenkg rebuild-indices`** — rewritten to delegate to `ingest.run_ingest()`
  instead of shelling out to `dockg build`. Now honours the same `IngestOptions`
  pipeline as `gutenkg ingest`, adds `--force-build` flag, and skips books whose
  `.dockg/` already exists unless `--force-build` is passed. Removes the old
  `subprocess` + manual loop implementation (~60 lines → ~10 lines).

- **`.claude/skills/gutenkg/`** — Claude Code skill updated to v1.2.1 coverage:
  adds `ia` command group (download/catalog/search/survey), `snapshot` subcommands,
  `status`, `viz3d`, `viz-timeline`, `list-genres`, and `rebuild-indices --force-build`
  to both SKILL.md and references/commands.md. Standard batch workflow now includes
  `snapshot save` step. IA catalog file format documented. Pitfalls section expanded.

---

## [1.2.0] - 2026-05-12

### Added

- **`src/gutenberg_kg/corpus.py`** — new library module that extracts all
  corpus data logic from the CLI layer into a path-parameterised public API.
  Provides `collect_genre_stats`, `corpus_status`, `snapshot_build`,
  `snapshot_save`, `snapshot_list`, `snapshot_show`, `snapshot_diff`, plus
  internal helpers `_sqlite_counts`, `_count_authors`, `_git_info`, and the
  canonical `GENRE_LABELS` mapping. All functions accept explicit path
  arguments so they can be called from CLI, tests, or adapter code without
  depending on package-level constants.

- **`gutenkg viz-timeline`** — interactive Plotly corpus growth chart built
  from saved snapshots. Two modes via `--type`:
  - `2d` (default): 2×2 subplot grid — Books / Authors / Nodes / Edges over
    time, with hover tooltips showing version and commit.
  - `3d`: normalized multi-metric scatter stacked by metric; all four series
    rendered in one scene for cross-metric trend comparison.
  Requires the new `viz` extra (`pip install gutenberg-kg[viz]`). Emits an
  ASCII growth summary table before showing the chart.

- **`viz` optional-dependency group** — `plotly>=5.0.0` for the `viz-timeline`
  command. Install with `pip install -e ".[viz]"` or
  `poetry install --extras "viz"`. Included in `all`.

### Changed

- **`cmd_status.py` refactored** — delegates all data collection to
  `corpus.corpus_status()`; module now contains only Click command wiring,
  Rich table rendering, and README badge patching. Thin wrapper aliases
  (`_collect_genre_stats`, `_count_book_dirs`, `_genre_corpus_name`,
  `_sqlite_counts`, `_GENRE_LABELS`) kept for test-import compatibility.

- **`cmd_snapshot.py` refactored** — delegates snapshot I/O to
  `corpus.snapshot_save/list/show/diff()`; `_SNAPSHOTS_DIR` renamed to
  `SNAPSHOTS_DIR` (public) so tests can monkeypatch it. Thin wrappers
  (`_snapshot_filename`, `_load_snapshot`, `_list_snapshots`) retained for
  test-import compatibility.

- **`pyproject.toml`** — `all` extra reorganized with `# dev / # kgdeps /
  # viz / # viz3d` section comments; `viz` and `viz3d` install lines added
  to the Quick Install header.

### Fixed

- **`tests/test_cmd_status.py` and `tests/test_cmd_snapshot.py` import
  errors** — after the corpus refactor the tests could not import private
  helpers (`_collect_genre_stats`, `_list_snapshots`, etc.) that had moved
  to `corpus.py`. Re-exposed as thin wrappers in the respective CLI modules;
  both test files now collect and pass cleanly (83 tests, 0 failures).

- **`gutenkg status`** — new CLI command that reads live corpus statistics
  directly from the KGRAG registry SQLite without requiring a rebuild.
  Displays a Rich table (with plain-text fallback) of per-genre book,
  node, and edge counts. Options: `--json` (machine-readable output),
  `--update-readme` (patches corpus/node/edge badge URLs in `README.md`
  automatically), `--registry` (override registry path).

- **`gutenkg snapshot` subcommand group** — point-in-time corpus metrics
  snapshots stored in `corpus/.snapshots/` (gitignored). Four subcommands:
  - `snapshot save` — capture current stats; writes timestamped JSON keyed
    by version, branch, and commit. `--output` overrides path; `--print`
    also emits JSON to stdout.
  - `snapshot list` — tabular listing of all saved snapshots.
  - `snapshot show [SNAPSHOT]` — print full JSON for a snapshot (defaults
    to the most recent); accepts a timestamp prefix for selection.
  - `snapshot diff [A] [B]` — compare two snapshots showing Δ books/nodes/
    edges at the total and per-genre level (defaults to last two).

- **`tests/test_cmd_status.py`** — 42 tests covering all pure helpers
  (`_genre_corpus_name`, `_count_book_dirs`, `_sqlite_counts`,
  `_fmt_badge_nodes`, `_update_readme_badges`, `_collect_genre_stats`) and
  CLI integration (help, missing registry, `--json` payload shape and
  totals, author count, `--update-readme` side effect).

- **`tests/test_cmd_snapshot.py`** — 41 tests covering all pure helpers
  (`_snapshot_filename`, `_load_snapshot`, `_list_snapshots`) and CLI
  integration (all four subcommands, error paths, round-trip save→list
  and save→diff flows). Uses `monkeypatch` to redirect `SNAPSHOTS_DIR`
  and `CORPUS_ROOT` to `tmp_path` for isolation.

- **`corpus/.snapshots/` gitignored** — snapshot files live alongside
  `.dockg/` directories but are excluded from version control.

### Changed

- **Corpus stats updated: 178 → 181 books** — README.md badges, prose
  counts, and `docs/CORPUS.md` header updated; per-genre node/edge counts
  refreshed (878,403 nodes, 17,564,366 edges after re-index).

### Fixed

- **Circular import in `cmd_snapshot.py`** — `_collect_genre_stats` was
  imported from `cmd_status` at module level; `main.py` imports both
  modules at startup, creating a load-order cycle. Fixed by lazily
  importing `_collect_genre_stats` inside `_build_snapshot()` and
  defining `_REGISTRY_DEFAULT` locally in `cmd_snapshot.py`.

- **Unused `rich.text.Text` import removed** from `cmd_status.py`
  `_print_rich_table()` (flagged by ruff F401).

- **Corpus expanded to 178 books** — five new Stoic texts added to
  `ancient-classical` and one new Nietzsche work to `philosophy`:
  - *Minor Dialogues, Together With the Dialogue on Clemency* — Seneca
    (Stewart trans.; includes *Of Providence*, *Of Constancy*, *Of Anger*,
    *Of Clemency*)
  - *The Golden Sayings of Epictetus, with the Hymn of Cleanthes* — Epictetus
  - *The Meditations of the Emperor Marcus Aurelius Antoninus* — Marcus Aurelius
    (Long trans.)
  - *The Teaching of Epictetus* — Epictetus
  - *Thoughts of Marcus Aurelius Antoninus* — Marcus Aurelius
  - *The Twilight of the Idols; or, How to Philosophize with the Hammer.
    The Antichrist* — Friedrich Nietzsche
  - Corpus now at 944,384 nodes and 18,443,197 edges

- **`docs/CORPUS.md`** — dedicated 249-line corpus listing (178 books × 13 genres)
  extracted from `README.md` so the master README stays lean; README now links
  to it.

- **`scripts/provenance_verifier.py`** — mechanized 8-word substring verifier
  for the frontier-model provenance experiment. Takes the first 8 words of each
  quoted passage, normalises case and punctuation, and checks against the
  committed corpus files; produces VERIFIED / HALLUCINATED / UNVERIFIABLE
  verdicts.

- **`HANDOFF.md`** — task handoff document describing the provenance verifier
  work item, input files, and expected output format.

- **`.claude/skills/gutenkg/`** — Claude Code skill definition for the gutenkg
  CLI (`SKILL.md` + `references/commands.md`), enabling AI-assisted corpus
  management and ingest workflows directly in the IDE.

- **New author profiles** — 40+ author metadata files added under
  `corpus/authors/` for newly ingested and back-filled authors (Seneca,
  Epictetus, Aeschylus, Aristophanes, Aristotle, Herodotus, Thucydides,
  Ovid, Plutarch, Boethius, Kant, Rousseau, Descartes, Mill, Emerson,
  Wollstonecraft, and more).

- **`viz3d.py` — `GENRE_PALETTE`** — 10-color dark-background-friendly,
  colour-blind-safe genre palette for tree trunk colouring.

- **`viz3d.py` — `_glyph_proto()`** — prototype mesh factory for
  `pv.PolyData.glyph()` batch rendering; replaces the per-node
  `_make_node_mesh()` loop in the main render path.

- **`viz3d.py` — `ForestLayout.branch_lines`** — list of `(axis_pt, tip_pt)`
  tuples populated during `compute()`; drawn as a single flat numpy polydata
  with zero per-line Python objects.

- **`viz3d.py` — `ForestLayout.trunk_genres` / `genre_color_map`** — per-trunk
  genre label and genre→hex-colour mapping for the merged-trunk draw call.

- **`viz3d.py` — `ForestLayout.max_trunk_height`** — cap (default 45 units) so
  no single large book dominates the grove silhouette.

- **Two new ingest reports** — `reports/ingest_2026-05-07_014830.md` and
  `reports/ingest_2026-05-07_020626.md` capturing the Stoic corpus expansion
  runs.

### Changed

- **`gutenkg rebuild-lancedb` → `gutenkg rebuild-indices`** — command and all
  associated help text renamed to a technology-neutral term; `cmd_rebuild.py`
  function renamed from `rebuild_lancedb` to `rebuild_indices`.  Docs and tests
  updated accordingly.

- **`viz3d.py` — ForestLayout grove radii doubled** — `grove_inner_radius`
  default 40 → 80, `grove_outer_radius` 120 → 240; `trunk_scale` 6 → 4.  Gives
  178-book groves room to breathe without overlap.

- **`viz3d.py` — section nodes spiral up trunk (golden-angle branching)**
  — replaces the Fibonacci upper-hemisphere approach: sections are placed along
  the trunk height at a golden-angle offset, producing a real tree branching
  pattern. Trunk-axis → section-tip lines are recorded as `branch_lines` and
  drawn as a single line mesh.

- **`viz3d.py` — glyph rendering replaces per-node mesh loop** — node
  rendering is now O(kinds) Python work rather than O(nodes): positions are
  bucketed per kind, then `pv.PolyData.glyph()` creates one merged mesh per
  kind in a single VTK draw call.  Eliminates the progress-bar loop and
  associated `QApplication.processEvents()` calls during mesh building.

- **`viz3d.py` — genre-colored trunks via merged mesh + `ListedColormap`**
  — all trunk cylinders are merged into a single `pv.PolyData` with a
  `genre_idx` cell scalar; a `ListedColormap` maps indices to genre colours.
  Result: one `add_mesh` call for all trunks regardless of genre count.

- **`viz3d.py` — chunk canopy uses upper-hemisphere cone** — orphan chunks and
  section-child chunks are now placed in the upper hemisphere above their parent
  Z level; reflected if insufficient upper-hemisphere points are available from
  the Fibonacci sample.

- **`viz3d.py` — CONTAINS edges hidden by default** — `show_contains` param
  default changed `True` → `False`; the control panel checkbox initialised
  accordingly. Reduces visual noise on first load.

- **`viz3d.py` — ground plane enlarged** — `i_size` / `j_size` 600 → 1000 to
  match the doubled grove radii.

- **`viz3d.py` — pick handler improved** — trunk clicks navigate to the nearest
  document node (showing book info); status bar messages added for every pick
  outcome; `picker.SetPickFromList(0)` set to enable actor-list picking.

- **`README.md`** — corpus stats updated (175 → 178 books, 850K → 944K nodes,
  16.9M → 18.4M edges); corpus book listing moved to `docs/CORPUS.md`; `kgrag
  synthesize` example added to the query section; "Audel Electric (IA)" genre
  renamed to "Technical Reference (IA)"; DOI badge switched to canonical
  `zenodo.org/badge/doi/` form.

- **`docs/CHEATSHEET.md`** — updated for `rebuild-indices` command; `.dockg/`
  layout comment clarified.

- **`docs/DOWNLOAD_PIPELINE.md`** — `.dockg/` layout comments clarified
  (graph.sqlite → "Graph database"; lancedb → "Vector index (gitignored)").

- **Multiple author profiles updated** — Darwin, Dickens, Dante Alighieri,
  Marcus Aurelius, Epictetus, Nietzsche, Dostoevsky, H.G. Wells, Thoreau,
  Jack London, Jules Verne, Tolstoy, Plato, Victor Hugo, Shakespeare author
  files updated to reflect new works or corrected metadata.

### Fixed

- **`tests/test_cli.py`** — `test_rebuild_lancedb_help` renamed to
  `test_rebuild_indices_help`; command string updated from `rebuild-lancedb`
  to `rebuild-indices` throughout.

---

## [1.1.0] - 2026-05-05

### Added

- **`src/gutenberg_kg/ingest.py` — `run_ingest()` orchestrator** — centralised
  genre-loop, corpus setup, registry management, and summary printing into a
  single public function. `cmd_ingest.py` now calls `ig.run_ingest()` in three
  lines instead of duplicating ~80 lines of logic.

- **`gutenkg download search` — `--subject` and `--language` options** — two
  arguments present in the old argparse layer were missing from the Click CLI.
  Added to `cmd_download.py` and wired through to `gutenberg.run_search()`.

- **Test suite** — four new test modules covering the full library API:
  - `tests/test_gutenberg.py` — 17 tests (metadata fetch, boilerplate strip,
    heading detection, `text_to_markdown`, slugify, idempotence, catalog parsing)
  - `tests/test_ia.py` — 19 tests (search, download, `_coerce_str`,
    `find_text_file`, `write_reference`, `fetch_url` retry)
  - `tests/test_ingest.py` — 9 tests (`run_ingest`, `IngestOptions`,
    `GenreSummary`, `ensure_corpus`, `is_sqlite_valid`)
  - `tests/test_genres.py` — 5 tests (registry load/save, `add_genre`,
    `seed_registry`, fallback defaults)

- **`analysis/gutenberg_kg_analysis_20260505.md`** — PyCodeKG structural
  analysis of the post-refactor codebase (1731 nodes, 1411 edges, 15 modules,
  A/100 quality grade, 93% docstring coverage).

### Changed

- **`src/gutenberg_kg/gutenberg.py`** — removed `import argparse`, five
  `cmd_*` adapter functions, `main()`, and the `if __name__` block (~200 lines).
  Module is now a pure download library; entry point is `gutenkg download`.

- **`src/gutenberg_kg/ia.py`** — same treatment as `gutenberg.py`: removed
  argparse layer, `build_parser()`, `main()`, and `if __name__` (~90 lines).
  Entry point is `gutenkg ia`.

- **`src/gutenberg_kg/cli/cmd_ingest.py`** — collapsed from ~140 lines to ~30.
  Removed duplicated genre loop, corpus setup, and summary printing; delegates
  entirely to `ig.run_ingest()`.

- **`src/gutenberg_kg/cli/cmd_ia.py`** — `ia download --genre` changed from
  `required=True` to `default=None` to match what `ia.download_book()` already
  accepted.

- **Docs updated** — `README.md`, `CHEATSHEET.md`, and `DOWNLOAD_PIPELINE.md`
  updated to remove all script-equivalent blocks and reflect the CLI-only
  interface.

### Removed

- **`scripts/download_gutenberg.py`** — thin wrapper around the old argparse
  `gutenberg.main()`; superseded by `gutenkg download`.
- **`scripts/download_ia.py`** — thin wrapper around `ia.main()`; superseded
  by `gutenkg ia`.
- **`scripts/ingest.py`** — was already broken (called `ingest.main()` which
  never existed); superseded by `gutenkg ingest`.
- **`scripts/rebuild_lancedb.sh`** — covered by `gutenkg rebuild-lancedb`.
- **`scripts/push.sh`** — covered by `gutenkg ingest --push`; contained a
  hardcoded genre list that would have drifted from `corpus/genres.json`.

### Added (corpus & genre registry)

- **Aristophanes** added to the `ancient-classical` genre — three new texts:
  - *The Frogs* (Gutenberg #7998, 77.8 KB standalone)
  - *The Eleven Comedies, Volume 1* (Gutenberg #8688, 499.6 KB — includes *The Wasps*, *The Acharnians*, *The Knights*, *The Clouds*, *Peace*, *The Birds*)
  - *The Eleven Comedies, Volume 2* (Gutenberg #8689, 585.6 KB — includes *Lysistrata*, *Thesmophoriazusae*, *The Frogs* alt. translation, *Ecclesiazusae*, *Plutus*)
  - Ingested as three DocKGs: 11,105 combined nodes, 151,966 combined edges
  - `ancient-classical` corpus now at 12 books, 63,000 nodes, 798,131 edges

- **`audel-electric` genre** — three Audel electric library volumes downloaded
  from Internet Archive and ingested as DocKGs:
  - *Audels Electric Library Vol 1* (IA: `audels-electric-library-vol-1`, 1929) — Fundamental Principles and Rules of Electricity, Magnetism, Armature Winding
  - *Audels Electric Library Vol 2* (IA: `audels-electric-library-vol-2`, 1929) — Dynamos, DC Motors, Construction, Installation, Maintenance
  - *Audels New Electric Library Vol VIII* (IA: `audelsnewelectri008004mbp`, 1962)
  - Ingested: 22,922 nodes, 168,745 edges across 3 books in 44.8s

- **`src/gutenberg_kg/genres.py`** — centralized genre registry backed by
  `corpus/genres.json`. Loads the JSON at import time with built-in defaults as
  fallback; exposes `GUTENBERG_GENRES`, `IA_GENRES`, and `ALL_GENRES`. Provides
  `seed_registry()` and `add_genre()` helpers consumed by the CLI.

- **`gutenkg genres` command group** (`src/gutenberg_kg/cli/cmd_genres.py`) —
  manage the genre registry without editing code:
  - `gutenkg genres init` — seed `corpus/genres.json` from built-in defaults
    (`--force` to overwrite)
  - `gutenkg genres list` — print all registered genres grouped by source
  - `gutenkg genres add <name> --source gutenberg|ia` — append a genre to the
    registry (auto-inits the file if absent)

- **`corpus/genres.json`** — committed registry file seeded with all current
  genres; now the single file to edit when adding a genre.

### Changed

- **Genre lists decoupled from module constants** — `gutenberg.py`, `ia.py`,
  `ingest.py`, and `cli/options.py` all previously contained their own hardcoded
  genre lists (diverging over time). Each now imports from `genres.py`.

- **Documentation updated** — `CHEATSHEET.md`, `README.md`, and
  `DOWNLOAD_PIPELINE.md` updated to document the `gutenkg genres` workflow,
  the `corpus/genres.json` registry, and the new file-layout entries.

### Fixed

- **Internet Archive search API** — `mediatype=texts` is no longer accepted as a
  standalone query parameter by the IA Solr API. Moved it into the Solr query
  string as `AND mediatype:texts`; searches now return results correctly.

---

## [1.0.1] - 2026-05-04

### Added

- **Epictetus** added to the `ancient-classical` genre — *A Selection from the
  Discourses of Epictetus with the Encheiridion* (Gutenberg #10661). Brings the
  Stoic shelf alongside Marcus Aurelius's *Meditations* to two works.

### Changed

- **Full corpus re-indexed** with the new BAAI/bge-small-en-v1.5 embedder.
  Updated corpus stats: **79 books, 448,139 nodes, 4,836,993 edges** (was
  78 books, 445,486 nodes, 4,525,716 edges).
- **Bumped DocKG dependency to 0.13.0** for the bounded SIMILAR_TO graph.
  See "Fixed" below.

### Fixed

- **SIMILAR_TO edge explosion** — under the new embedder, the previous
  threshold-only logic in DocKG produced ~12.4M edges (up from 4.5M) due to
  formulaic prose corpora (Burroughs, Lovecraft, long Russian novels) saturating
  the 0.85 cosine threshold. Patched DocKG to enforce a per-chunk top-k cap
  (default k=5) on SIMILAR_TO edges; corpus now sits at 4.84M edges with bounded
  out-degree, signal-rich similarity links, and ~14% faster ingest. The fix
  required:
  - Implementing the documented-but-dead `similar_k` parameter in
    `doc_kg/index.py:_discover_similar_edges` (was previously labelled
    "unused — kept for API compatibility")
  - Exposing `--similar-k` and `--similar-threshold` flags on `dockg build`
  - Canonicalizing edges to `(min(src,dst), max(src,dst))` so the SQLite
    `(src, rel, dst)` PRIMARY KEY dedupes cross-batch under per-row top-k

---

## [1.0.0] - 2026-05-04

### Added

- **Brand assets** — `assets/gutenberg_logo.png` (RGBA master with real transparency),
  `assets/gutenberg_logo.svg` (true vector via vtracer), and size variants:
  `assets/logos/logo_{32,64,128,256,512}.png` for embedding,
  `assets/badges/badge_{20,40,80,200}.png` for shields and inline badges.
- **`scripts/process_logo.py`** — automated logo pipeline. Removes baked-in
  checkerboard background, produces real RGBA alpha with edge-feathered anti-alias,
  generates all logo/badge size variants, and exports SVG via `vtracer`. CLI flags
  for tuning background threshold and feather radius.
- **Test suite** — `tests/test_authors.py`, `tests/test_cli.py`, `tests/test_options.py`,
  `tests/test_version.py` (65 tests, all passing).
- **CI workflow** — `.github/workflows/ci.yml` runs lint + tests on push/PR.
- **GitHub issue templates** — `.github/ISSUE_TEMPLATE/bug_report.md` and
  `feature_request.md`.
- **Pre-commit hooks** — `.pre-commit-config.yaml` + `.secrets.baseline` for
  ruff, mypy, and detect-secrets enforcement.
- **`.vscode/settings.json`** — pytest configured against the project venv interpreter.
- **README citation section** — BibTeX + APA blocks; centered logo header; refined
  badges (Python 3.12 | 3.13, Elastic-2.0 code, Public Domain texts, v1.0.0,
  corpus stats, DocKG, KGRAG).
- **Dev dependencies** — `pillow`, `scipy`, `vtracer` added for logo processing.
- **Internet Archive ingestion** — `gutenkg ia` CLI group with `search`, `download`,
  `catalog`, and `survey` subcommands. Fetches books from archive.org, converts OCR
  text to structured Markdown (same pipeline as Gutenberg), and deposits under `corpus/`.
- **`scripts/download_ia.py`** — promoted from `audel_kg/` sub-project into the main
  scripts directory as a first-class source alongside `download_gutenberg.py`.
- **`src/gutenberg_kg/cli/cmd_ia.py`** — Click command group for IA operations.
- **`ALL_IA_GENRES`** in `cli/options.py` — separate genre registry for IA-sourced corpora
  (`audel-electric` initial entry).
- **`HANDOFF_IA.md`** — architecture handoff document for the IA integration work.
- **`gutenkg` CLI** — full Click-based command-line interface (`src/gutenberg_kg/`),
  matching the code_kg/doc_kg package pattern. Entry point: `gutenkg`.
  - `gutenkg ingest` — build DocKG indices, register with KGRAG, push per-genre
  - `gutenkg download book/catalog/search/fetch-genre/survey` — all download operations
  - `gutenkg rebuild-lancedb` — rebuild LanceDB vector indices after clone
  - `gutenkg list-genres` — print all known genres
- **`pyproject.toml`** — Poetry package scaffold; `poetry install` installs `gutenkg`
- **`CHEATSHEET.md`** — full quick-reference for all CLI commands and workflows
- **`scripts/ingest.py`** — major upgrade:
  - Rich box-drawing job summary with per-genre breakdown, node/edge counts, timing
  - Auto-saved Markdown reports to `reports/ingest_YYYY-MM-DD_HHMMSS.md`
  - `--push` flag — `git add + commit + push` per genre after ingest
  - `--list-genres` flag
  - `BookResult` and `GenreSummary` dataclasses with timing and graph stats
  - Auto-wipe corrupt/empty `graph.sqlite` before rebuild
  - Wipe `.dockg` before `--force-build` to avoid stale state errors
- **`scripts/download_gutenberg.py`** — major upgrade:
  - `survey` subcommand — scan repo, show `md/ref/kg` status per book by genre
  - `fetch-genre` subcommand — search, confirm, download, report in one step
  - `--genre` flag on `download` and `catalog` — route books into genre subdirectories
  - `--force` flag — re-download even if already present
  - `--dry-run` flag on `download`, `catalog`, `fetch-genre`
  - Idempotent downloads — skip already-present books by default
  - `science-fiction` added to `ALL_GENRES`
- **`scripts/catalogs/science-fiction.txt`** — curated sci-fi catalog (Shelley,
  Wells, Lovecraft, Burroughs, Doyle, Abbott)
- **`scripts/rebuild_lancedb.sh`** — rebuild LanceDB indices after cloning
- **`scripts/push.sh`** — standalone per-genre git push helper (superseded by `--push`)
- **Science-fiction genre** — 14 books ingested (445K nodes, 4.5M edges total corpus)
- **`.gitignore`** — exclude `lancedb/` dirs, `__pycache__`, `.venv/`, build artifacts
- **`.gitattributes`** — LFS tracking scoped to `**/.dockg/graph.sqlite` only
  (removed `.lance`, `.txn`, `.manifest` from LFS — lancedb is now gitignored entirely)
- **`reports/`** — four auto-generated ingest run reports

### Changed

- **`CITATION.cff`** — bumped to version 1.0.0, dated 2026-05-04. Title updated to
  "GutenbergKG: The Knowledge Press"; abstract expanded to cover Internet Archive
  and corpus stats; added `references` block linking DocKG and KGRAG; corrected
  contact email; added explicit `license` field.
- **Re-framed as "The Knowledge Press"** — GutenbergKG is now positioned as a universal
  ingestion engine for digitized text corpora, not a Gutenberg-specific tool. Name is
  unchanged; the metaphor is now explicit: any public domain text source feeds the same
  pipeline.
- **`pyproject.toml`** description updated to "The Knowledge Press -- universal ingestion
  engine for digitized text corpora"; classifier promoted from Alpha to Production/Stable.
- **`gutenkg` CLI help text** updated to reflect the Knowledge Press framing.
- **README.md** — lead paragraph and overview updated for the broader scope; Project
  Gutenberg logo image removed (no affiliation); "Public Domain" badge link changed from
  gutenberg.org to the repo (no implied endorsement).
- **License section** now explicitly states GutenbergKG has no affiliation with or
  endorsement from Project Gutenberg or the Internet Archive.
- LanceDB vector indices are now **local-only** (gitignored). Only `graph.sqlite`
  is committed. Rebuild with `gutenkg rebuild-lancedb` after cloning.
- Git push strategy changed from single monolithic push to **per-genre batched commits**
  via `gutenkg ingest --push`.

### Removed

- **`MANIFESTO.md`** — content consolidated into `README.md` ("Knowledge Press"
  framing).

### Fixed

- `graph.sqlite` corruption crash — `ingest.py` now detects and auto-wipes corrupt
  or empty sqlite files before attempting a build, preventing `sqlite3.DatabaseError`
  on partial builds.
- `--force-build` now wipes `.dockg/` before rebuilding, preventing stale-state errors.
