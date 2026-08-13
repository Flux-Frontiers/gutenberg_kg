# Changelog

All notable changes to GutenbergKG are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added

- **`gutenkg quilt --topics`** draws topic nodes as their own blue pollen
  cloud, and **`--leaf-size`** overrides the leaf radius before density
  scaling. The second exists because leaves shrink by the cube root of chunk
  count, so Pepys renders its 18,757 chunks at 0.32x and reads sparse even
  though every chunk has a leaf; `--leaf-size 0.9` thickens that canopy.

### Changed

- **3-D layout primitives now come from `kg_utils.viz3d`, not
  `pycode_kg.layout3d`.** `Layout3D`, `LayoutNode`, `LayoutEdge`,
  `fibonacci_sphere`, and `fibonacci_annulus` moved into kgmodule-utils 0.11.0,
  which ends an odd dependency: GutenbergKG's 3-D layer was pulling in the
  *code* KG package for what is pure geometry. `ForestLayout` still subclasses
  `Layout3D`, and `LayoutNode` carries an identical field set, so this is an
  import swap rather than a rewrite.

  `viz3d` now declares `kgmodule-utils[viz3d]>=0.11.0` in place of
  `pycode-kg`, and the core floor moves to `>=0.11.0`. `pycode-kg` stays in the
  `kgdeps` extra for its own CLI.

- **Entities and topics are now separate spore clouds.** `show_entities` drew
  `entity`, `topic`, and `keyword` as one gold halo, which conflated what a
  book *names* with what it is *about* and left the blue `KIND_COLOR["topic"]`
  unused since it was defined. They toggle independently; the viewer drives
  both from its single checkbox, so it behaves exactly as before.

- **Spore halos are capped at 200 glyphs.** One glyph per node cannot work at
  corpus scale — Pepys carries 7,065 entities and 7,287 topics against 18,757
  leaves, and the halo buried the tree it exists to annotate. Measured against
  a spore-free Hamlet render, an uncapped halo left 38% of the foliage legible,
  350 left 64%, and 200 leaves ~68%. A halo reads as a cloud rather than a
  count, so a deterministic sample carries the same meaning at a fraction of
  the ink. Spores are also sized against the leaves rather than their own
  count, so the halo always reads finer than the foliage.

  Opacity is not a free dial: below about 0.2 the spores stop being visible
  while still veiling the crown, which is strictly worse than not drawing them.
  Depth peeling was tried and changes nothing — the cost is coverage, not draw
  order.

- **PyCodeKG code-health reports are no longer tracked.** The repo carried them
  under two competing conventions — a version-named `docs/analysis_v1.2.0.md`
  frozen since v1.2.0 and eleven releases stale, and dated
  `analysis/gutenberg_kg_analysis_<date>.md` files. Both describe code that git
  already records, and they regenerate in about six seconds
  (`pycodekg analyze .`), so tracking dated snapshots was pure churn: one past
  release bumped a report as its only doc change. The version-named file is
  deleted, the dated ones are untracked but left on disk, and
  `analysis/gutenberg_kg_analysis_*.md` is now gitignored.

  The experiment results beside them stay tracked deliberately — the
  `similar_to_*` sweeps behind the cap-8 / `discover_similar=False` decision,
  `embedder_benchmark_*`, and `front_matter_assessment.json`. Those cost real
  compute, cannot be regenerated cheaply, and are the evidence for conclusions
  this changelog asserts elsewhere.

- **Docs audit against the shipped v1.14.0 code.** `docs/CHEATSHEET.md` gained
  the two sections the README had been pointing at without them existing —
  **Querying the Corpus** (`gutenkg query`) and **Visualisation and Light-Field
  Rendering** (`gutenkg viz3d`, `quilt`, `viz-timeline`, every option with its
  default) — and its File Layout tree now matches the tree on disk (`scene.py`,
  `layout_organic.py`, `vector_store.py`, `audit.py`, `model_setup.py`,
  `diary/`, `serve/`, six new `cmd_*.py`; `docker/chat.py` and
  `docker/handler.py` moved to `serve/` some releases ago). The vector store is
  described as `vectors.sqlite` (sqlite-vec), not `lancedb/`, in
  `CHEATSHEET.md`, `DOWNLOAD_PIPELINE.md`, `ingestion-pipeline.md`,
  `RUNPOD.md`, and `APPLE_CONTAINERS.md`, and `ingestion-pipeline.md`'s Stage 4
  now records that SIMILAR_TO discovery is off by default and that the FTS5
  lexical index is built in the same phase. `docs/INSTALLATION.md` lists what
  the `viz3d` extra actually installs (kgmodule-utils and quiltwright, not
  pycode-kg) and notes that `gutenkg quilt` needs Python < 3.13.
  `SIMILAR_TO_CAP_RECOMMENDATION.md` carries a status banner: its cap-8 finding
  stands, its default-on recommendation does not. `docs/CHAT_UI.md`'s link to
  `serve/chat.py` now points at `serve/Chat.py`.

### Removed

- **`docs/NATURAL_TREE_LFD_PLAN.md`**, and the README link to it. The plan
  described the organic tree, the seasons, the Qt-free scene builder, and the
  `quilt` CLI as unbuilt work; all of it shipped in v1.14.0, so the document
  described the code's past as its future. Its §5 also carried a corpus size
  (249 books) the corpus never had. The design rationale that survives
  implementation now lives in the cheatsheet's visualisation section and in the
  docstrings of `layout_organic.py` and `scene.py`; the copy in
  `kgrag_priv/docs/` is untouched, since a grant document cites it there.

- **`docs/release-notes.md`** — stranded at v1.1.0 (May 2026) and unreferenced.
  The release workflow reads the root `release-notes.md`, which is at v1.14.0.

### Added

- **`scripts/check_pins.py`** — verifies the four cross-pinned KG packages agree
  across every file that names them: `pyproject.toml` floors, `poetry.lock`,
  `docker/Dockerfile` ARGs, and `runpod/requirements.txt`. A prerequisite of
  `make build` in both runtime branches, and a step in the CI lint job.

  The floor comparison is the point. `docker/Dockerfile` pre-installs the pinned
  stack and then runs `pip install .`, which re-resolves against pyproject — so
  an ARG below its floor is silently upgraded rather than failing the build. The
  pin becomes a number no image runs, and nothing anywhere goes red. That is how
  `KGMODULE_UTILS_VERSION` sat at 0.10.0 against a `>=0.11.0` floor unnoticed.

  On its first run it found a second instance of that same drift, which the
  manual audit had missed: `runpod/requirements.txt` also floored
  `kgmodule-utils` at `>=0.10.0`, so the serverless worker could install a
  version the package itself rejects. Fixed alongside.

  Stdlib-only (`tomllib` + `re`, with a local `_version_key` rather than
  `packaging.version`) so a build gate never depends on what the install
  resolved — which also matters for the ordering it tests, since `"0.9.0" >
  "0.11.0"` under a string compare. `corpus_pepys` carries a sibling that
  deliberately omits the floor check: that project is `package-mode = false`
  with no `pip install .` step, so its Dockerfile pins are the last word.

### Fixed

- **`make up` died on any host without Apple Silicon.** `IMAGE_BACKEND` defaulted
  to `flux`, so `up` ran `make image-server` unconditionally — which builds
  `.venv-image` from `docker/requirements-image.txt` and installs mflux. mflux's
  own metadata pins `mlx ; sys_platform == "darwin"` and
  `mlx[cuda13] ; sys_platform == "linux"`, with no Windows entry at all, so on an
  ordinary x86 host the pip install failed and took `up` with it — *after* the
  worker and chat had already started, so the whole stack looked broken when only
  the image backend was unavailable.

  The default is now conditional: FLUX where mflux can run, **SDXL-Lightning**
  everywhere else. That is a real fallback rather than a skip, because
  `gutenberg_kg.serve.sdxl_server` resolves `cuda → mps → cpu` and so runs on any
  host (slowly on CPU, but it runs). On Apple Silicon nothing changes.
  `make up IMAGE_BACKEND=flux|sdxl` still forces either. Asking for FLUX where it
  cannot run now fails with a message naming the requirement and pointing at the
  SDXL alternative, instead of a pip resolution error, and `FORCE_IMAGE_SERVER=1`
  overrides the probe for the CUDA 13 Linux case it cannot detect.

  Starting the image server is also best-effort in both runtime branches now: it
  is one optional button in the chat UI, so its failure warns rather than
  failing a stack whose worker and chat are already serving.

- **SDXL-Lightning was undocumented.** `make sdxl-server` and the `:8091` server
  appeared only in architecture diagrams and file listings — never in
  `docs/INSTALLATION.md`'s target table or its image-generation section. It is
  the only local image backend that runs off Apple Silicon, so the one option a
  Linux or Windows user needs was the one nobody could find. Documented in
  `INSTALLATION.md` and `CHAT_UI.md`, including a table of what each server
  requires.

- **`docs/INSTALLATION.md` called OpenAI "the one provider path that works
  identically on Linux and Windows".** Ollama already covers text synthesis
  there, and SDXL-Lightning covers images; OpenAI's actual distinction is
  needing nothing installed locally. Also flagged the collision between the
  *Make* variable `IMAGE_BACKEND` (`flux`/`sdxl` — which server to start) and the
  *environment* variable of the same name in `docker/.env`
  (`mflux-serve`/`mflux-local`/`openai` — which backend the worker generates
  through). They are unrelated and the Make one is not passed into the container.

Four further defects were surfaced by a consistency audit of `corpus_pepys`,
which used this repo as its reference implementation. Written up in full in
`HANDOFF-corpus-pepys-audit.md`.

- **The chat sidebar crashed with a `KeyError` whenever `HANDLER_SECRET` was
  set.** Two independent causes compounded. First, the secret never reached the
  chat container: `Chat.py` and `pages/1_Browse.py` read `HANDLER_SECRET` and put
  it in every request, but the compose `chat` service and the Apple `chat` target
  both omitted it while their worker counterparts set it. Second, `_fetch_stats`
  and `_corpus_options` built their payloads by hand and never sent it at all, so
  fixing the first alone would not have helped.

  The crash itself came from the error envelope. The worker rejects a bad secret
  with a **200 carrying** `{"error": "unauthorized"}`, so `raise_for_status()`
  does not fire; `_fetch_stats` returned that dict verbatim, it was *truthy*, and
  the sidebar took its success branch straight into `stats['books']`. The
  "corpus stats unavailable — worker offline" fallback was unreachable, because
  it was written for a falsy `{}`. Any worker-side error reproduced it, not just
  an auth failure. `_corpus_options` failed more quietly, collapsing the corpus
  dropdown to `["all", "diary"]` and hiding every genre.

  Both fetches now go through one `_worker_op` helper that sends the secret and
  normalises an error payload to `{}`; the sidebar reads totals with `.get` so a
  partial payload costs a number rather than the page; and both deployment paths
  forward `HANDLER_SECRET`. `pages/1_Browse.py` sends it too — every op on that
  page was returning `unauthorized`, which rendered as an empty corpus rather
  than a rejected request.

- **The Dockerfile pinned `kgmodule-utils` below its own declared floor.**
  `ARG KGMODULE_UTILS_VERSION=0.10.0` against a `>=0.11.0` floor in
  `pyproject.toml` and 0.11.0 in the lock. The Dockerfile's own comment predicts
  the consequence: the later `pip install .` re-resolved and upgraded it, so the
  ARG was fiction — no build ever ran the version it named, the pre-install layer
  fetched that package twice per cold build, and the four `==`-pinned KG packages
  were no longer verified as the set that actually ships. Now 0.11.0.

- **The cross-pin comment block was three releases stale**, naming doc-kg 0.20.0
  and kgmodule-utils 0.9.0 directly above ARGs reading 0.21.1 and 0.11.0. Since
  that block is the documentation of record for why the four move together, a
  stale copy is worse than none. Rewritten from the lock's actual constraints.

- **A failed synthesis threw away a search that had already succeeded.**
  `synthesize_rag` was called unguarded, so an unreachable LLM server, an
  unloaded model or a timeout propagated out of the handler and failed the whole
  request. It is now caught and returned as `synthesis_error` alongside the hits
  — the key `Chat.py`'s "Answer generation failed" branch has always rendered,
  and which was unreachable because nothing ever set it. `corpus_pepys` carried
  the identical dead path and is fixed the same way, so the two workers keep the
  same response contract.

- **CI collection no longer dies when the `viz3d` extra is absent.**
  `tests/test_scene.py`, `tests/test_layout_organic.py`, and
  `tests/test_seasons.py` imported `gutenberg_kg.scene` / `.layout_organic` at
  module scope, and those modules import `pyvista` at module scope in turn. CI
  installs no optional extras, so all three failed at *collection*, which
  aborts the entire run rather than skipping three files — the rest of the
  suite never executed. Each now calls `pytest.importorskip("pyvista")` before
  the import, matching how the suite already guards pyvista inside test
  bodies. Without the extra: 419 passed, 3 skipped; with it: 496 passed.

---

## [1.14.0] - 2026-08-11

### Added

- **Organically grown knowledge trees** (`gutenberg_kg.layout_organic`). Where
  the existing `ForestLayout` places nodes on a golden-angle spiral — right for
  exploring the whole corpus — this module *grows* a skeleton that reaches the
  data. A book's chunk positions become attraction points and the branch
  structure is produced by space colonization (Runions, Lane & Prusinkiewicz
  2007), so every limb is a real structural path document → section → chunk
  cluster and the canopy's shape is the book's shape rather than decoration.
  Branch radii follow the pipe model (da Vinci's rule, exponent 2.2), limbs are
  swept tubes along Catmull-Rom root-to-tip paths, and leaves are glyphed
  (never per-node meshes) with orientation biased away from the trunk.

  Everything is deterministic: `seed_from_slug()` derives a stable 32-bit seed
  from the book slug — Python's salted builtin `hash()` cannot be used for
  geometry that must reproduce between sessions, renders, and printed figures.

  Two departures from textbook colonization, both needed because a book's
  crown is clumpy where a plant's attractor cloud is not. When no attractor is
  within the influence radius, the algorithm as published simply stops — which
  strands the rest of the canopy as a stump under a cloud of unattached
  leaves; instead a limb is bridged across the gap and growth continues. And
  an isolated attractor can stay in range for the entire run yet never win a
  node, because the averaged pull always goes to the crowd — a book's
  one-chunk front-matter sections are exactly that case — so each survivor is
  given its own twig at the end. Every chunk hangs on wood.

- **`gutenkg quilt`** — renders one book's tree as a Looking Glass light-field
  quilt (still or `--orbit` turntable video), off-screen and Qt-free, with
  `--cast` to push the result to Looking Glass Bridge. Presets cover the 16"
  Gen3 Landscape (default), portrait, Go, 27", 32", and 65" devices.

  The **depth budget is printed before every render**, not after: the scene
  bounding box is projected onto the view axis and the near/far disparities are
  reported in pixels. Above roughly 5 px reads soft, past ~8 px ghosts visibly
  — so a blown budget shows up at zero cost instead of after a full quilt
  render.

- **Seasonal foliage** (`SEASONS`, selectable in the viewer and via
  `--season`). Spring/summer/autumn/winter each carry a foliage palette
  sampled per leaf — a canopy varies the way a real one does instead of reading
  as one flat green — plus wood colour and sky gradient. Winter additionally
  drops 90% of the leaves, which is the point: bare wood is where the pipe
  model shows.

- **Viewer controls for the above**: an "Organic tree (one book)" checkbox, a
  season selector, and a "Cast to LG" button that renders the current view as a
  quilt and casts it. Organic mode requires exactly one selected book and says
  so plainly when more are loaded; picking is disabled there, since the scene
  is swept wood and glyphed leaves rather than per-node actors.

- **`tests/test_scene.py`, `tests/test_layout_organic.py`,
  `tests/test_seasons.py`** — 77 tests over the extracted scene builder,
  the growth pipeline (seed stability, crown spacing, colonization,
  pipe radii, sweeps), and the seasonal/leaf-placement geometry. These are
  Qt-free and run headless, which is what the extraction below buys.

- **10 tests in `tests/test_gutenberg.py`** covering the sura heading pattern
  (including the prose cases it must *not* match) and the bilingual heading
  gate, plus end-to-end `text_to_markdown()` checks that a Quran and an
  Analects excerpt now produce sections.

### Changed

- **Scene construction extracted from the Qt viewer into
  `gutenberg_kg.scene`** — corpus scanning, `BookMeta`, `ForestLayout`, glyph
  and edge geometry, `build_forest_scene()`, and the new `build_tree_scene()`
  now compose into a plain `pv.Plotter` with no PyQt import and no
  `QApplication.processEvents()`. Progress reporting is a plain
  `Callable[[str], None]`, so a Qt caller can pump its event loop and a
  headless one can print or ignore.

  `viz3d.py` is now one caller of that module (down ~680 lines) and the
  off-screen quilt renderer is another. Without this split, light-field
  rendering would have needed a live `QApplication`.

- **`quiltwright>=0.3.0` added to the `viz3d` extra**, marker-gated to
  `python_version < '3.13'`: quiltwright pins `requires-python <3.13` while
  this project supports `<3.14`, and without the marker Poetry rejects the
  whole resolution rather than just that package. Drop the marker once
  quiltwright widens its floor.

- **Casting from the viewer renders at half the preset's pixel size**
  (`CAST_SCALE`), giving an exactly-tiling 3840×2160 quilt instead of
  7680×4320. Measured, the local pipeline is only ~1.5 s end to end (scene
  0.4 s, 48 views 0.6 s, PNG 0.6 s) — the wait is Bridge loading a
  33-megapixel PNG, and that cost scales with area, so this quarters it. Files
  written by `gutenkg quilt` stay at full resolution.

  The button also reports four phases (`Cast 2/4 — rendering 48 views at
  480x360...`), disables itself while running, and prints elapsed time, so a
  slow Bridge handoff never looks like a hang.

- **Apple `container` runtime memory caps lowered**: `WORKER_MEM` 8g → 2g,
  `CHAT_MEM` 4g → 512m. The old defaults were unmeasured guesses; the new
  values follow the sibling `corpus_pepys` repo's `container stats`
  measurements for the same worker/chat container shape. Memory is a lazy
  upper bound, not a reservation, so this only lowers the ceiling — override
  with `WORKER_MEM=`/`CHAT_MEM=` if a larger corpus needs more headroom.
  `docs/APPLE_CONTAINERS.md` documents the re-measurement procedure to use
  if that cap is ever hit.

### Removed

- **Routine ingest reports ignored** (`reports/ingest_*.md`). One is written per
  real `gutenkg ingest` run, so partial rebuilds would pile up in every diff.
  They remain good provenance — host, flags, embedder, per-book timings — so
  the ones worth keeping are kept deliberately with `git add -f`; the existing
  full-corpus report stays tracked.

- **Stale LanceDB ignore rules** (`**/.dockg/lancedb*`, `**/.diarykg/lancedb*`)
  dropped from `.gitignore`. The sqlite-vec migration means those directories
  are no longer produced; `renders/` is ignored in their place, since that is
  where `gutenkg quilt` writes.

### Fixed

- **Sacred-text headings were being lost during text→Markdown conversion**,
  collapsing whole works into a single section. Two unrelated causes, both in
  `text_to_markdown()`:

  - **Quran**: none of the 114 sura headings matched a pattern, because Rodwell
    prints a footnote digit against the word or numeral and an edition-order
    marker in brackets — `SURA1 XCVI.-THICK BLOOD, OR CLOTS OF BLOOD [I.]`. All
    2,586 body chunks therefore hung under a section named "PREFACE". A `SURA`
    pattern now covers them; it requires a separator after the numeral so prose
    like "SURA I saw ..." is not promoted to a heading.
  - **Analects**: `BOOK I.  HSIO R.` *did* match, but headings are only honoured
    after a blank line and Legge's bilingual edition prints the Chinese heading
    (`學而第一`) directly above the English one. Every `BOOK` heading in the
    volume was swallowed. A preceding line carrying no Latin letters now counts
    as a break, since it is not prose in these editions.

  Verified against the texts themselves: the Quran goes from 4 headings to 118
  and the Analects from 3 to 26. Heading counts are unchanged on Frankenstein,
  Moby Dick, Pride and Prejudice, Alice, Hamlet, and Tao Te Ching, so the
  relaxed gate does not invent structure elsewhere.

  The two affected books have been re-downloaded and re-ingested, and their
  corrected Markdown is committed: the Quran now carries 120 sections instead
  of 7 (PREFACE drops from 2,586 chunks to 99, and Sura II *The Cow* becomes
  the heaviest limb at 183 — correctly, it is the longest sura) and the
  Analects 28 instead of 8. The diffs are heading lines only, +113 and +21,
  with no body text touched. Other machines need no re-download, since the
  Markdown is tracked; only the gitignored `.dockg/` indices must be rebuilt.

- **`gutenkg ingest --dry-run` no longer writes an ingest report.** A dry run
  changes nothing, so leaving behind a file that says so was the one thing
  reliably filling `reports/` with noise.

---

## [1.13.0] - 2026-08-03

### Added

- **`gutenberg_kg.vector_store.resolve_vector_paths()`** — resolves a KG store
  directory to `(vectors_path, lancedb_path)`, preferring sqlite-vec and falling
  back to LanceDB. Exactly one is non-`None`, so a migrated store never carries
  a stale LanceDB pointer beside its sqlite-vec one.

  The precedence deliberately matches `handler._open_vector_source`, which
  already read on that rule. The bug below was the *read* path and the
  *register* path disagreeing.

- **`tests/test_vector_store.py`**, kept free of any `kg_rag` import so it runs
  in CI — `tests/test_ingest.py` skips wholesale when kg_rag is absent, which is
  how the registration paths went untested.

### Changed

- `dev`'s `pillow` floor raised `>=10.0.0` → `>=10.4.0` to match `chat`/`image`,
  removing the one genuinely divergent duplicate constraint.


- **Dependency floors raised to a co-installable set:** `doc-kg>=0.20.0` and
  `pycode-kg>=0.21.2`, alongside the existing `kg-rag>=0.11.0`. The previous
  floors admitted doc-kg 0.18.x / pycode-kg 0.20.x, which pin `transformers<4.57`
  and so contradict kg-rag 0.11.0's `transformers>=5.5.0`. `runpod/requirements.txt`
  carried the same stale floors and is bumped to match.

- **Container pins are declared once**, in `docker/Dockerfile`'s `ARG` defaults.
  `docker-compose.yml` overrode `KGMODULE_UTILS_VERSION` with `0.4.6` while the
  Dockerfile said `0.5.0`, so a compose-triggered build and `make build`
  produced different images from the same Dockerfile; the `args:` block is gone.
  Because these are `==` pins, a stale one is now a hard resolution failure at
  build time rather than a silent upgrade by the later `pip install .`.

- **`diary-kg>=0.96.0`** (was `>=0.93.2`), bringing it in line with the rest of
  the set — it requires `doc-kg>=0.20.0` and `kgmodule-utils>=0.9.0`, the same
  floors declared above. Functionally it also pins `vector_backend="sqlite-vec"`
  internally and writes `.diarykg/vectors.sqlite` rather than `lancedb/`;
  under 0.93.2 the sqlite-vec output was incidental, produced by doc-kg's old
  `"auto"` default resolving that way rather than by any diary-kg guarantee.

- **`build-corpus` names the sqlite-vec store directly.** doc-kg 0.20.0 accepts
  `vectors_path`, so both `DocKG` constructions now pass it alongside an
  explicit `vector_backend="sqlite-vec"` and no longer pass `lancedb_dir` at
  all. Previously the sqlite-vec path could only be *derived* — `lancedb_dir`
  had to be supplied purely as an anchor whose parent the sidecar hung off
  (`sqlite_vectors_path()`), which meant naming a directory the build never
  created. Matches how diary-kg 0.96.0 drives DocKG.

- **`rich>=14.3.3,<15`** (was `>=13.0.0`), matching the rest of the fleet —
  pycode-kg, kg-rag and diary-kg all require `>=14.3.3`, and every KG package
  caps at `<15`. `runpod/requirements.txt` also moves
  `sentence-transformers>=3.0.0` → `>=5.4.1,<6`, the floor doc-kg 0.20.0 and
  kg-rag 0.11.0 already forced.

### Removed

- **The `full` and `all` aggregate extras.** They were the reason `poetry lock`
  took over eight minutes.

  Re-listing a package inside an aggregate makes it a *second* declaration under
  different markers. Poetry reports that as `Duplicate dependencies … Different
  requirements found` and resolves it by discarding the entire resolution,
  adding an override, and starting over — with the override set accumulating, so
  each restart is a bigger problem than the last. A `-vvv` lock showed **1,278
  restarts across 1,321 solver runs**, 309s of it inside the solver, and *zero*
  package downloads. Twelve packages triggered it.

  Removing the two aggregates takes the lock from **503s to 9.6s**, resolving to
  a byte-identical package set (253 packages before and after).

  The obvious fix — `full = ["gutenberg-kg[kgdeps,viz,viz3d,mcp]"]` — poetry
  rejects outright: `Package 'gutenberg-kg[…]' is listed as a dependency of
  itself`. So there is no way to keep the aggregates and the speed.

  **Migration:** `--extras full` → `--extras "kgdeps viz viz3d mcp"`;
  `.[full]` → `.[kgdeps,viz,viz3d,mcp]`; `--all-extras` is unchanged and now
  covers what `all` did.


- **`_DOCKG_LANCEDB` / `_DOCKG_VECTORS`** module constants in `serve/handler.py`,
  now that the paths are derived. `_DOCKG_VECTORS` was already dead.

- **`docker/Dockerfile.sqlite`** — its premise ("like the main image, but
  sqlite-vec and no LanceDB") is what `docker/Dockerfile` now does by default.
  Nothing built it: no Make target, no CI. It was also a liability — it built
  `FROM egsuchanek/kgrag-worker:latest`, an external base needing a manual
  rebuild and push from the KGRAG repo, and installed everything `--no-deps`, so
  its real dependency set was whatever that base happened to carry (it never
  installed kg-rag or diary-kg at all).

### Fixed

- **`APPLE_HOST_GW` fell back to the wrong vmnet gateway.** The constant was
  `192.168.65.1`, with a comment claiming CLI 0.1.0 used `192.168.64.0/24` and
  1.1.0 moved to `192.168.65.0/24`. That is wrong: the
  `container-network-vmnet` plugin allocates `192.168.64.0/24` — macOS's vmnet
  framework default — verified on CLI 1.1.0 against a network created fresh by
  `container system start`, so it is the current allocation and not a leftover
  from an older CLI. `192.168.65.x` is *Docker Desktop's* gateway subnet, the
  likely source of the number.

  It also contradicted this repo's own `docs/APPLE_CONTAINERS.md`, which
  documents `192.168.64.1` in three places. The docs were right.

  Live detection already covered the normal path, so this only bit on a cold
  start — runtime not yet running, probe returns nothing, constant used. In
  that window every host-facing endpoint (oMLX, Ollama, the image servers)
  pointed at an unreachable address, and the failure was silent: answers came
  back with no synthesis rather than an error. Fixed alongside the same bug in
  `corpus_pepys`.

- **The chat model picker silently reverted to the provider default.** Neither
  the Provider nor the Model selectbox in `serve/Chat.py` carried a `key`, so
  Streamlit derived each widget's identity from its parameters — including
  `options` and `index`. Anything that changed those made it a *new* widget and
  reset the selection: switching provider, or hitting **🔄 Refresh models**,
  which clears the cache and refetches, potentially with a different order or
  `default`.

  The reset was invisible. The sidebar showed the default, and `cfg["model"]`
  carried it into both the query and the image-prompt rewrite — so answers came
  back from a model you had not chosen, with nothing indicating the swap.

  Both selectboxes now use explicit keys (`synth_provider`, `synth_model`) so
  their values live in `st.session_state` and survive reruns. A reconcile step
  runs *before* the Model widget renders: Streamlit raises if `session_state`
  holds a value absent from `options`, which is exactly what a provider switch
  causes, so the stored choice is validated first — kept when still available,
  and replaced by the provider default only when it genuinely vanished.

  Found in `corpus_pepys`, which carries a near-identical copy of this file;
  fixed in both.


- **The image shipped ~3.8 GB of unusable CUDA runtime.** torch's default PyPI
  wheel for `linux/aarch64` is now a CUDA build (`2.13.0+cu130`), pulled in
  transitively via sentence-transformers — so `docker/Dockerfile` installed
  2.9 GB of `nvidia-*` packages plus 652 MB of `triton` into an arm64 image that
  reports `torch.cuda.is_available() == False` under both Docker Desktop and
  Apple's `container`. Nothing in the config asked for this; it arrived when
  torch changed its aarch64 packaging.

  A dedicated `RUN` now installs torch from the PyTorch CPU index before the KG
  stack that pulls it. It must be its own layer: `--index-url` replaces PyPI for
  the whole command and that index does not host kg-rag/doc-kg/diary-kg.
  Not a downgrade — the CPU index carries the same `2.13.0` for cp312 aarch64,
  and the floors it must satisfy are low (`sentence-transformers` needs
  `torch>=1.11.0`, `transformers` `torch>=2.4`), so the later install leaves it
  alone. `nvidia/` 2970 MB → 0, `triton` 652 MB → 0, `torch` 914 MB → 635 MB.

  `runpod/Dockerfile` is deliberately unchanged: RunPod serverless is amd64 on
  real GPUs, where the CUDA build is the correct one.

- **`build-corpus` never removed a pre-migration LanceDB store.** Phase 2 has
  written sqlite-vec since the migration, but nothing deleted the `lancedb/`
  directory beside it, so a freshly rebuilt bundle still carried ~2.8 GB of index
  from an earlier build — and `docker/Dockerfile`'s blanket
  `COPY bundles/gutenberg-all/` baked every byte of it into the image. Reads were
  unaffected (`resolve_vector_paths` and the handler both prefer
  `vectors.sqlite`), so it was pure weight. `run_build_corpus` now purges it,
  `bundle_diaries` skips any `lancedb/` a pre-0.94 diary-kg left behind, and
  `.dockerignore` excludes `**/lancedb` as a pack-time backstop. Build context
  drops 7.8 GB → 5.0 GB.

- **Phase 1 of `build-corpus` left `vector_backend` on `"auto"`** while phase 2
  pinned `sqlite-vec`. `auto` resolves by probing the filesystem, and an existing
  `lancedb/` with no `vectors.sqlite` yet — exactly the state a `--wipe` rebuild
  starts from — resolves to `lancedb`. Latent today (`build_graph` never touches
  the lazy `.index`), but the two phases disagreeing is a trap. Both now pin
  `sqlite-vec`.

- **`.diarykg/corpus` shipped into the image as a dangling symlink.** It is
  DiaryKG's back-pointer to its source `.diary` directory, an absolute host path
  that `bundle_diaries` copies verbatim via `copytree(symlinks=True)`; Docker
  copies symlinks as-is, so it landed in the image pointing at a path that does
  not exist there. Nothing reads it at serve time. Now excluded at pack time.

- **`bundles/` was not gitignored**, despite `build_corpus`'s docstring saying so.
  The `**/.dockg/*.sqlite` rules caught the multi-GB databases by coincidence,
  which left `catalog.json` — and anything a future bundle format adds —
  committable. The whole tree is ignored now.

- **Registration recorded no vector store for migrated KGs.** All four sites
  that build a `KGEntry` probed only for a `lancedb/` directory and passed
  `lancedb_path`, with no `vectors_path` — so against a store that had moved to
  sqlite-vec the probe missed and the entry registered with **both** vector
  columns empty. Silently: `None` is legal for both, so nothing raised, and the
  registry simply lost the pointer.

  Affects `ingest.register_book`, `ingest.register_diary_book`, and the two
  bootstrap entries in `serve/handler.py` (the DocKG bundle one passed
  `_DOCKG_LANCEDB` unconditionally, recording a directory that need not exist).

  Two independent triggers, not one:

  * **Diaries** — diary-kg >=0.96.0 writes `.diarykg/vectors.sqlite` and no
    longer creates `lancedb/`. This was the reported case. (Earlier drafts of
    this note cited ">=0.94.0", a version that was never published — the line
    runs 0.93.2 → 0.93.4 → 0.96.0. Under 0.93.2 the sqlite-vec output came from
    doc-kg's old `"auto"` default resolving that way, not from diary-kg.)
  * **Books** — `build_dockg` constructs `DocKG(book_dir, embedder=...)` with no
    `vector_backend`, leaving it on `"auto"`, which resolves to sqlite-vec for a
    fresh corpus. So *every freshly built book* already wrote `vectors.sqlite`
    and registered nothing, independent of diary-kg. An earlier note in the
    KGRAG TODO judged the book path "correct until doc_kg Phase 4"; that was
    wrong — `auto` had already migrated it.

  `cli/cmd_imagine.py` and `build_corpus.py` are **not** affected despite naming
  `lancedb`: they pass `lancedb_dir=` to `DocKG` on `"auto"`, and `make_backend`
  derives the sidecar as `<lancedb_dir>.parent/vectors.sqlite`, which lands
  exactly on the migrated file. Left alone deliberately.

## [1.12.0] - 2026-07-29

### Added

- **Import-level MCP server tests** (`tests/test_mcp_server.py`). `mcp_server.py`
  builds its `FastMCP` instance and registers both tools at module import, so an
  incompatible `fastmcp` breaks `gutenkg-mcp` at import time. The tests skip when
  the `mcp` extra is absent, but fail — rather than skip — when `fastmcp` is
  present at an incompatible major.

### Changed

- **`fastmcp` bounded to `>=3.0,<4`** (was an unbounded `>=2.0`). GutenbergKG is
  the only KG in the family on the standalone `fastmcp` package rather than the
  SDK's bundled `mcp.server.fastmcp`, so it was untouched by the mcp 2.0 break —
  but it tracks a project that has already shipped 2.x and 3.x on its own
  schedule. The floor moves to `3.0` because that is what the lock already
  resolved to (3.4.4) and what the server is verified against; freezing at `<3`
  would have been a downgrade away from the known-good state. Applies to both the
  `mcp` and `full` extras.

- **Dependency floors lifted to the currently published releases** —
  `kgmodule-utils[synthesis,sqlite-vec]>=0.8.0`, `doc-kg>=0.18.1`,
  `pycode-kg>=0.20.0` (including the three `viz3d`/image extras that still
  floored `0.19.3`); lock regenerated. kgmodule-utils 0.8.0 defaults
  `vector_backend` to `"auto"`: sqlite-vec for fresh or already-migrated
  stores, LanceDB only when an un-migrated store already exists on disk, so
  existing corpora keep working untouched.

### Removed

### Fixed

- **`serve/sdxl_server.py` now imports cleanly in the main env.** The `diffusers`
  imports were at module top-level, so importing the module without the isolated
  `.venv-sdxl` (docs, tests, CLI) raised `ModuleNotFoundError` — the pdoc docs
  build hit this during submodule discovery. The three `diffusers` imports are
  now deferred into `_load_pipeline()` (with an actionable error pointing at
  `make sdxl-server`), mirroring how `image_server.py` defers its mflux import.
  `diffusers` remains isolated in `docker/requirements-sdxl.txt`, not the main
  Poetry env.

## [1.11.0] - 2026-07-24

**Headline — a fully Apple-native, Apple-Silicon, purely local stack.** The
worker and chat services now run end-to-end on Apple's native `container`
runtime (macOS 26, Apple Silicon): no Docker Desktop, no cloud, no external
LLM. Local MLX (oMLX) or Ollama models are reached over the vmnet gateway, and
with container CLI ≥ 1.1.0 the services publish to `localhost` exactly like the
Docker path. `make up RUNTIME=apple` is all it takes.

### Added

- **Apple `container` runtime support** — the local worker/chat stack can now
  run on Apple's native `container` CLI (macOS 26, Apple Silicon) instead of
  Docker Desktop: `make build|run|chat|up|down|logs|clean RUNTIME=apple`.
  The Docker/compose path remains the default and RunPod builds still require
  Docker. Assessment and usage notes in `docs/APPLE_CONTAINERS.md`.
- **`GUTENKG_IN_CONTAINER=1`** baked into both corpus images as an explicit
  in-container marker, since Apple's runtime creates no `/.dockerenv`.
- **`LICENSE`** — the Elastic License 2.0 text now ships in the repo root
  (it was declared in `pyproject.toml` and badged in the README, but the
  file itself was missing; GitHub could not display the license).
- **`docs/PARTNERS.md`** — the full partnership/sponsorship prospectus,
  moved out of the README.
- **`gutenkg query`** — a first-class CLI command for searching the locally
  ingested corpus without Docker. It delegates to `kgrag corpus query`
  (defaulting to the `gutenberg-all` corpus, `-k 8`) and supports `--corpus`,
  `--k`, `--registry`, and `--json`. A missing KGRAG install raises a clear
  `ClickException` instead of a bare `FileNotFoundError`. Wired into the CLI in
  `cli/main.py` and covered by `tests/test_cmd_query.py`.
- **Expected-title relevance gating in `scripts/check_standard_queries.py`** —
  each standard query now carries the work(s) it should surface, and a new
  `--expected-rank` flag (default 3) fails a query unless one of those titles
  appears within the top N hits. This upgrades the check from "did we get any
  hits" to "did we get the *right* book," with a `_has_expected_title` helper
  covered by `tests/test_check_standard_queries.py`.
- **Agent skills** — `.agents/skills/gutenkg/` (CLI reference for downloading,
  ingesting, and managing the corpus) and `.agents/skills/sync-corpus-docs/`
  (keeping README badges and corpus-count surfaces in sync with the live
  corpus).
- **`poetry.toml`** pinning the virtualenv in-project, and a `.codex/`
  gitignore entry for local Codex MCP config.

### Changed

- **README restructured** for readability: "What It Does" now precedes the
  quickstart; a table of contents added; the requirements table collapsed
  to a one-liner pointing at `docs/INSTALLATION.md`; the corpus table
  folded into a `<details>` block sorted by book count; the querying
  section now explains that `dockg`/`kgrag` ship baked-in as dependencies
  and how they relate to `gutenkg` and the chat UI; the partners section
  reduced to a summary linking `docs/PARTNERS.md`; the duplicated
  "No LLM required" paragraph deduplicated. Badges: live CI and Docs
  workflow badges added, decorative DocKG/KGRAG/imagine badges retired,
  license badge now links to the local `LICENSE` file. Corpus figures
  updated to 241 books across 20 genres, with terminal usage leading on
  `gutenkg query`.
- **`scripts/sync_corpus_docs.py`** sorts the README genre table by book
  count (descending, stable ties); `docs/CORPUS.md` keeps the canonical
  `GENRE_ORDER`.
- **Chat UI container detection** (`serve/Chat.py`, `serve/pages/1_Browse.py`)
  now checks `GUTENKG_IN_CONTAINER` in addition to `/.dockerenv`, so
  `host.docker.internal` is selected correctly under either runtime.
- **Docs refreshed to the current corpus and query path.** `INSTALLATION.md`
  now shows `gutenkg query` (replacing the raw `dockg`/`kgrag` invocations),
  `CHAT_UI.md` and `ingestion-pipeline.md` update counts to 241 books / 20
  genres, and the pipeline's static "Corpus at a Glance" table is replaced by a
  routing summary that points to the live `CORPUS.md` catalog.

- **Self-contained worker image** — `docker/Dockerfile` now builds from
  `python:3.12-slim` instead of extending `egsuchanek/kgrag-worker:latest`.
  Everything the worker imports comes from PyPI pins plus this checkout (with
  `libgomp1`/`libglib2.0-0` for the sentence-transformers / lancedb wheels),
  so a clean build no longer depends on a separately-published base image.
  Only the sqlite-vec variant (`docker/Dockerfile.sqlite`) still uses the
  kgrag-worker base.

### Removed

### Fixed

- **Apple `container` port publishing restored.** With container CLI ≥ 1.1.0,
  the worker (`:8000`) and chat UI (`:8501`) are published to the host via
  `--publish` and reachable at `localhost`, matching the Docker path. The
  interim 1.0.x workaround (raw vmnet IPs, since `--publish` was unsupported)
  is no longer needed.
- **Host services reachable from Apple containers.** `host.docker.internal`
  does not resolve on this runtime, so the worker's LLM and image endpoints
  (oMLX `:8080`, Ollama `:11434`, image server `:8090`) are rewritten to the
  vmnet gateway; without this the worker silently saw no LLM.
- **Gateway subnet no longer hardcoded.** Apple's `container` shifts its
  default vmnet subnet across CLI versions (0.1.0 → `192.168.64.0/24`,
  1.1.0 → `192.168.65.0/24`), which silently broke worker→LLM access on
  upgrade. `APPLE_HOST_GW` now auto-detects the gateway from the live
  `default` network, falling back to the current default when the runtime
  isn't up yet.

---

## [1.10.0] - 2026-07-16

### Added

- **`.github/workflows/docs.yml`** — GitHub Pages is now built and deployed
  by CI instead of a committed-HTML branch deploy: builds the pdoc API
  reference (`poetry run make docs`) and publishes via
  `actions/deploy-pages` on every push to `main`. Live at
  https://flux-frontiers.github.io/gutenberg_kg/.

### Changed

- **`make docs` now outputs to a gitignored `site/`** instead of committing
  generated HTML under `docs/`; `docs/` returns to hand-written markdown
  only (44 pdoc HTML files removed). This also fixed the prior deployment,
  which the legacy Jekyll branch-builder failed to process — a literal
  `{{...}}` Plotly template string in `viz_timeline.html` broke Liquid
  parsing, and the publish root had no `index.html`.
- **Docs CI installs every extra pdoc's imports actually need** —
  `dev chat image mcp viz viz3d kgdeps`, plus a plain `pip install runpod`
  (deliberately outside any extra — see the `pyproject.toml` note) and
  `PDOC_ALLOW_EXEC=1` (pdoc sandboxes subprocess execution during import;
  `runpod`'s import-time `cpuinfo` probe crashes on the suppressed output
  on Linux, though not on macOS). `gutenberg_kg.serve.handler` bootstraps
  its full KG registry and embedder at import time, so pdoc — which
  imports every documented module to render it — exercises this whole
  startup path.
- **pdoc's logo now resolves.** `--logo` points at the Pages-absolute URL
  and the real asset (`assets/logos/logo_256.png`) is copied into `site/`
  at build time; the previous `./logo.png` referenced a file that was
  never committed to the repo.
- **`/release` gained a docs-build verification step** — `poetry run make
  docs` now runs as a release gate before tagging, so a broken docs
  environment is caught locally instead of surfacing only after the tag
  reaches `main`.

### Removed

### Fixed

- **`gutenberg_kg/__init__.py` had no module docstring** — since `pdoc`'s
  generated `index.html` redirects here, the docs site's landing page
  rendered empty. Added a docstring describing the project generally
  (it ingests from Project Gutenberg, the Internet Archive, and other
  public-domain sources — not affiliated with or limited to Project
  Gutenberg specifically).
- **`CITATION.cff` was stale** — the abstract still quoted an old corpus
  snapshot (79 works / 9 genres / 448,139 nodes) and listed `lancedb` as a
  keyword after the sqlite-vec migration. Now reads the live corpus totals
  (241 works / 20 genres / 1,270,591 nodes / 5,094,446 edges) and
  `sqlite-vec`. Note: `scripts/sync_corpus_docs.py` doesn't touch this file
  yet, so it will drift again on the next corpus growth — folding it in is
  a follow-up.

---

## [1.9.0] - 2026-07-16

### Added

- **KnowledgePress macOS app (Phase 1 thin client)** — `app/GutenbergKGKit/`,
  a SwiftPM package with two targets: `GutenbergKGKit` (async `WorkerClient`
  for the RunPod worker's `/runsync` ops — `search`, `stats`, `list_genres`,
  `list_books`, `get_chapters`, `get_chapter` — plus typed response models and
  `WorkerError`) and `KnowledgePress` (SwiftUI app: chat view with retrieved-
  passage turns, corpus Browse view, settings sidebar for endpoint/API key).
  Unit tests cover model decoding and the client against a stubbed
  `URLProtocol`. See `app/README.md`; Phase 2 (local Core ML retrieval) is
  next.
- **`docker/Dockerfile.sqlite`** — sqlite-vec-only worker image: installs
  `kgmodule-utils==0.5.0` + `doc-kg==0.18.0` from PyPI plus
  `sqlite-vec==0.1.9`, and bakes only the sqlite-vec stores
  (`vectors.sqlite`) — the ~2.5 GB consolidated LanceDB dir is never sent to
  the image, and per-diary `lancedb/` dirs are stripped after COPY.
- **`scripts/sync_corpus_docs.py`** — one command keeps every public
  corpus-count surface aligned with the live corpus (the KGRAG registry, via
  `corpus_status`): the README badges, the "Corpus at a Glance" table
  (regenerated between `<!-- BEGIN/END corpus-table -->` markers), the intro
  prose, the "query N books" line, the partnership blurb, the BibTeX citation
  note, and `docs/CORPUS.md` (delegated to `regenerate_corpus_doc.py`). Genre
  ordering for the table is shared with CORPUS.md via
  `regenerate_corpus_doc.GENRE_ORDER`. Run with `--check` to report drift and
  exit non-zero (CI / pre-release gate); run with no flag to fix. The release
  version badge is deliberately left to the `/release` workflow.
- **`gutenberg_kg.serve` package** — the serving layer now ships inside the
  installed package instead of loose scripts under `docker/`:
  `serve/handler.py` (RunPod worker), `serve/chat.py` + `serve/pages/`
  (Streamlit UI), and `serve/image_server.py` (FLUX image server).
- **New entry points** — `gutenkg chat` (launches the Streamlit UI via
  `streamlit run` on the packaged app), `gutenkg-handler` (RunPod worker),
  and `gutenkg-image-server` (FLUX server, replaces
  `python docker/image_server.py`).
- **New optional extras** — `pip install 'gutenberg-kg[chat]'`
  (streamlit/httpx/watchdog/pillow) and `[image]`
  (fastapi/uvicorn/pydantic/pillow) mirror the chat and image serve modules.
  runpod is deliberately not an extra (its dependency tree stalls
  `poetry lock`); the RunPod container installs it via
  `runpod/requirements.txt`.
- **`tests/test_cmd_imagine.py`** — covers the `gutenkg imagine` command with
  the endpoint, VLM, and corpus retrieval mocked (no network/GPU/doc-kg): help
  registration, the `_resolve_prompt` prompt-building seam, `_vlm_rewrite`
  fallback, and the end-to-end flow (missing-endpoint usage error, param
  pass-through including `--size`, env-var endpoint, request-failure handling,
  `--open`, and `--corpus-only`).
- **Worker `stats` op + live chat header** — new `stats` op returns
  `{books, genres, diaries, nodes, edges, embed_model}` computed on demand from
  `catalog.json` and the consolidated `graph.sqlite`. `serve/chat.py` now
  fetches its sidebar counts, the intro caption's book count, and the
  corpus-scope dropdown live from the worker (`stats` + `list_genres`) instead
  of hardcoded strings — so adding a book or genre flows into the UI with no
  code change (nodes/edges are omitted from the header, since the served
  consolidated graph deduplicates entities and drops `SIMILAR_TO`, so its
  totals differ from the per-book sum the README reports).

### Changed

- **Vector store migrated LanceDB → sqlite-vec** across the serving and build
  paths. Motivation (see `benchmarks/SQLITE_VEC_RESULTS.md`): the production
  LanceDB IvfFlat index averaged **0.825 recall@10** at default settings
  ("pillar of salt": 0.4), while sqlite-vec brute force is exact (recall 1.0)
  at comparable latency and ~10× smaller (2.5 GB → 1.1 GB fp32 for the full
  688 K-vector store).
  - Both workers (`serve/handler.py`, `runpod/handler.py`) open vector
    sources via `_open_vector_source`: `vectors.sqlite`
    (`kg_utils.vector_backend.SqliteVecBackend`) preferred, LanceDB kept as
    a transition fallback for un-converted corpora — including every diary KG.
  - The LanceDB fallback path gains the **`nprobes(128)` recall stopgap**
    (0.825 → 0.992 recall@10 at ~+5 ms).
  - `build_corpus` phase 3 now builds the bundle with
    `vector_backend="sqlite-vec"` (doc-kg 0.18.0), emitting
    `<bundle>/.dockg/vectors.sqlite`.
  - `runpod/push_indices.sh` excludes `lancedb/` dirs from the rsync
    (~2.3 GB less per deploy); README + `docs/APP_ARCHITECTURE.md` updated —
    the macOS app now reads the *same* `vectors.sqlite` the worker serves.
- **`doc-kg` floor raised `>=0.16.0` -> `>=0.18.0`** and
  **`kgmodule-utils[synthesis]` `>=0.4.6` -> `>=0.5.0`** (`pyproject.toml`,
  `poetry.lock`, `runpod/requirements.txt`; 0.18.0/0.5.0 bring the
  `VectorBackend` seam with the sqlite-vec backend). Docker images pin
  `KGMODULE_UTILS_VERSION=0.5.0` / `DOC_KG_VERSION=0.18.0`.
- `docker/Dockerfile` no longer COPYs `handler.py`/`chat.py`/`pages/`/
  `image_gen.py` into `/app` — the `pip install .` of the repo package carries
  them; `CMD` is now `python -u -m gutenberg_kg.serve.handler`, and the
  compose chat service runs `gutenkg chat --port 8501 --address 0.0.0.0`.
- `make image-server` installs the package (`--no-deps`) into `.venv-image`
  and runs `gutenkg-image-server`.
- **KG dependencies now install from PyPI, not git/local wheels** — the
  Docker image installs `kgmodule-utils[synthesis]==0.4.6` and
  `doc-kg==0.16.0` by version (pre-installed in a cached layer so source-only
  changes don't re-resolve the torch stack), and the RunPod build only builds
  the `gutenberg-kg` wheel locally — `kg-rag>=0.9.1` and the KG packages come
  from `runpod/requirements.txt`. `build_image.sh`/README no longer assume a
  sibling `kgrag/` checkout.
- **`viz3d`/`full`/`all` extras use plain `pyvista`, not `pyvista[jupyter]`** —
  viz3d renders to a desktop Qt window, so the `[jupyter]` trame/browser stack
  was unused and massively bloated `poetry lock`.
- **Image generation takes an explicit `--size WIDTHxHEIGHT`, not `--ratio`** —
  the fixed `_ASPECT_SIZES` lookup (`1:1`, `3:2`, `16:9`, …) is replaced by a
  free-form pixel size parsed by `image_gen._parse_size()`, so any dimensions
  are allowed (default `1536x1024`, overridable via `GUTENKG_IMAGE_SIZE`). The
  `size=` parameter now flows through `generate`, `generate_via_server`,
  `generate_auto`, the `generate_image`/`corpus_imagine` MCP tools, and
  `serve/image_server.py` (which passed `req.size` straight through instead of
  snapping it to the nearest known ratio). `serve/chat.py` drops its now-unused
  `aspect_ratio` plumbing.
- **Worker genre validation derived from the catalog** — `serve/handler.py`'s
  `_ALL_GENRES` was a hardcoded set (missing `horror`, so filtering the chat by
  it would have been rejected as an unknown corpus). It is now populated from
  `catalog.json` at startup, so every genre in the live corpus is accepted as a
  filter automatically.

### Removed

- **`docker/image_gen.py`** — a diverged fork of `gutenberg_kg/image_gen.py`
  (it still read the old `IMAGE_STEPS` env var and lacked the server/VLM
  paths). `serve/image_server.py` now imports the canonical
  `gutenberg_kg.image_gen`; explicit `steps` passing keeps the served
  behaviour identical.

### Fixed

- **Stale corpus counts across README and `docs/CORPUS.md`** — the badges,
  intro prose, "Corpus at a Glance" table, partnership blurb, and citation
  advertised 230 books / 1.2M nodes / 4.9M edges / 19 genres; the live corpus
  is **241 books / 1,270,591 nodes / 5,094,446 edges / 20 genres**. All
  surfaces are now regenerated from live data.
- **Horror genre silently dropped from generated docs** — `regenerate_corpus_doc.py`
  hardcoded a `GENRE_ORDER`/`GENRE_LABELS` list that never included `horror`,
  so its 16 books were omitted from `docs/CORPUS.md` even on regeneration (and
  Science Fiction had drifted 18 → 13). Added the genre; both lists now cover
  the full corpus.
- **Worker crash-loop on the sqlite-vec bundle** — `docker/Dockerfile` (the
  default compose image) installed only `kgmodule-utils[synthesis]`, but the
  baked bundle now ships a `vectors.sqlite` store, so the handler selected the
  `SqliteVecBackend` and died at startup with
  `SqliteVecBackend requires sqlite-vec`, restart-looping the worker (the chat
  UI reported "Cannot connect to worker"). The image now installs
  `kgmodule-utils[synthesis,sqlite-vec]`, matching `Dockerfile.sqlite`.
- **`pyproject.toml` missing the `sqlite-vec` extra** — same root cause as the
  Docker crash-loop above, but for the package itself: a plain `pip install
  gutenberg-kg` / `poetry install` pulled `kgmodule-utils[synthesis]` without
  `sqlite-vec`, so any non-Docker environment (e.g. the macOS app) reading a
  `vectors.sqlite` bundle hit the same `SqliteVecBackend requires sqlite-vec`
  failure. Now depends on `kgmodule-utils[synthesis,sqlite-vec]`.
- **`diaries` genre missing from ingest reports** — `gutenkg ingest` routes
  `diaries` through a separate DiaryKG pipeline (`ingest_diaries()`) that ran
  *before* the main per-genre loop and dropped its results on the floor, so
  the console summary and saved `reports/ingest_*.md` under-reported "Genres
  processed" (19 instead of 20) and omitted the diary books' node/edge counts
  entirely — even though the diaries built and registered successfully.
  `run_build_diaries()`/`ingest_diaries()` now return per-book results as a
  `GenreSummary` that folds into the same report as every other genre.

---

## [1.8.0] - 2026-07-10

### Added

- **`gutenkg init` command** (`src/gutenberg_kg/cli/cmd_init.py`,
  `src/gutenberg_kg/model_setup.py`) — fetches the local ML models (spaCy +
  embedder) the pipeline needs, run once after cloning + `poetry install`. It
  catches a missing model up front instead of failing mid-run during
  `chunk-diaries` / `ingest` / `build-corpus`. Pass `--check` to report model
  status without downloading. Docker builds don't need it — the image
  pre-downloads the embedder at build time.
- **Corpus browser** — a new "Browse" page (`docker/pages/1_Browse.py`) lets you
  list every book by genre and read it chapter by chapter, reconstructed from
  the DocKG section/chunk nodes already baked into the worker's index (no raw
  corpus text needs to ship in the deployed image). Backed by four new
  `docker/handler.py` ops — `list_genres`, `list_books`, `get_chapters`,
  `get_chapter` — served through the existing `/runsync` endpoint alongside
  search. Streamlit's multi-page auto-discovery means `chat.py` itself needed
  no changes; `docker/Dockerfile` now also copies `docker/pages/` into the image.
- **Synthesis model blocklist** (`docker/chat.py`) — reasoning models (e.g.
  Agents-A1, DeepSeek-R1, gpt-oss) and non-chat utility models (document
  converters, embedders) are now filtered out of the model dropdown, since their
  chain-of-thought prose isn't strippable and truncates RAG answers before the
  actual response.
- **Title/content mismatch detection in `gutenkg audit`** (`src/gutenberg_kg/audit.py`)
  — compares each book's `reference.md` title against the quoted title in its
  auto-generated `## Summary` (sourced from the real fetched text) and flags a
  divergence as an error, catching a wrong Gutenberg ID that silently mislabels
  a whole book. A curated `KNOWN_TITLE_VARIANTS` allowlist (by ebook ID) exempts
  legitimate alternate titles/translations (e.g. *The Quran* / *The Koran*,
  *Faust Part I* / *Faust: Der Tragödie erster Teil*) from being flagged.

### Changed

### Removed

### Fixed

- **Corpus relabel/re-fetch for mislabeled books** surfaced by the new audit
  check — wrong-ID or mismatched entries were replaced with the correct text
  across `ancient-classical`, `biography`, `drama`, `english-literature`,
  `german-literature`, `letters`, `russian-literature`, `science-fiction`, and
  `travel` (e.g. *Oresteia (Aeschylus)* → *The House of Atreus* (Agamemnon,
  Libation Bearers, Furies); *A Journey to Other Worlds (Astor)* → *A Journey in
  Other Worlds: A Romance of the Future*). `corpus/authors/` gained ~40 new
  author pages and `docs/CORPUS.md` was regenerated to match.

---

## [1.7.1] - 2026-07-02

### Added

- **`hf-transfer` dependency** — enables accelerated Hugging Face Hub downloads.
- `analysis/gutenberg_kg_analysis_20260703.md` — PyCodeKG architectural analysis
  snapshot (complexity hotspots, module coupling, docstring coverage) captured
  after the docstring pass below.

### Changed

- **Docstring coverage raised from 67.3% to 95.3%** (PyCodeKG-measured). Added
  Google/NumPy `:param:`/`:return:`-style docstrings to ~100 previously
  undocumented functions and methods across `docker/chat.py`, `docker/handler.py`,
  `docker/image_server.py`, `runpod/build_kg.py`, `runpod/handler.py`, and
  `src/gutenberg_kg/{authors,cmd_snapshot,cmd_status,corpus,genres,gutenberg,
  ingest,mcp_server,viz3d,viz_timeline}.py`. Pure documentation insertions — no
  behavioral changes.
- **`kgdeps` extra** now installs `pycode-kg` instead of the already-core
  `doc-kg`/`diary-kg` pins.

---

## [1.7.0] - 2026-06-24

### Added

- **`src/gutenberg_kg/diary_meta.py`** — shared module for diary slug derivation
  (`diary_slug()`) and static author/title/genre metadata (`DIARY_META`). Both
  handler workers now import from this single source of truth; adding a new diary
  requires editing one file only.
- **`docs/RUNPOD.md`** — comprehensive RunPod serverless deployment guide covering
  the two-image architecture, network volume setup, `push_indices.sh` workflow,
  endpoint configuration, request reference, and corpus update procedure.
- **Hybrid (dense + lexical) retrieval in `docker/handler.py`** — a new FTS5/BM25
  channel (`_open_dockg_store`, `_rrf_fuse`) is fused with cosine kNN via
  reciprocal rank fusion (RRF, `k=60`), recovering exact-term matches the embedder
  buries (e.g. "circles of Hell" → Dante's *Inferno*). Both channels honour the
  same genre/content-kind scope, and the semantic floor is now gauged against the
  best *dense* hit only. Degrades gracefully to pure dense ranking when a corpus
  carries no `nodes_fts` index.

### Changed

- **`doc-kg` dependency floor raised to `>=0.16.0`** across all dependency groups
  (`dependencies`, `kgdeps`, `full`, `all`) in `pyproject.toml`, ensuring the
  hybrid FTS5/BM25 lexical-retrieval support is present in the installed doc_kg.
- **Consolidated `build-corpus` no longer discovers SIMILAR_TO edges by default.**
  `BuildCorpusOptions.discover_similar` now defaults to `False`, and the CLI flag
  flipped from opt-out `--no-similar` to an opt-in `--similar/--no-similar` pair
  (default `--no-similar`). The served `docker/handler.py` is semantic-first
  (dense cosine + BM25 RRF) and never traverses the edges table, so the ~800k
  SIMILAR_TO edges a full build produced (245 books × ~2.8k) were pure dead weight
  in the shipped `graph.sqlite`. The cap-8 SIMILAR_TO retrieval gains apply only to
  `DocKG.query()`'s hop-expansion path — per-book `gutenkg ingest` still builds
  cap-8 edges for viz3d arcs and hop queries. Pass `--similar` to opt a consolidated
  bundle back in.
- **README restructured** — Docker local app (`make build-corpus → make build →
  make up → localhost:8501`) promoted to the primary quick-start path; CLI demoted
  to developer/power-user section; RunPod section removed (see `docs/RUNPOD.md`).
- **`runpod/handler.py` rewritten** to use the same direct LanceDB cosine-search
  path as `docker/handler.py` (no KGRAG orchestrator), adding DiaryKG support and
  eliminating the startup hang on large corpora.
- **`runpod/push_indices.sh`** — fixed source path from repo-root `.dockg/` (the
  project documentation KG) to `bundles/gutenberg-all/` (the literary corpus
  bundle); destination corrected to `/workspace/gutenberg_kg/` to match handler
  expectations.
- **`runpod/test_local.py`** — symlink target fixed from repo root to
  `bundles/gutenberg-all/`; added clear error if bundle does not exist.
- **`runpod/requirements.txt`** — pinned to `doc-kg>=0.15.8`, `diary-kg>=0.93.2`,
  `kgmodule-utils>=0.4.3` to match the docker stack.
- **`docker/Dockerfile` installs the local repo package** (`pip install .` of
  `pyproject.toml` + `src/gutenberg_kg`) instead of hot-copying a single
  `image_gen.py` over the PyPI install, so runtime imports always match the
  checkout being built.
- **`src/gutenberg_kg/build_corpus.py` embed path is device-aware** — CPU now
  fans out across `cpu_count/2` worker processes (`.json` cache → doc_kg's
  multi-process `CorpusEmbedder`, with `KG_EMBED_DEVICE=cpu` pinned so workers
  don't each grab the GPU and OOM), while MPS/CUDA keep the single-process
  streaming (`.jsonl`) path. The startup banner reports the resolved mode.

### Removed

- **Mislabeled / duplicate Dante editions in `corpus/world-literature/`** — the
  three entries split across translation fragments were consolidated: *Paradiso*
  → **The Divine Comedy (Cary)**, *Inferno* → **The Divine Comedy (Longfellow)**,
  and the duplicate *Purgatorio* directory dropped.

### Fixed

- **`build-corpus --embed-device auto` now resolves to CPU, not MPS.** The full
  consolidated build embeds 700k+ nodes, and MPS single-process streaming OOMs on
  Apple's unified-memory watermark (`other allocations: ~80 GiB` partway through
  the pass). `auto` now picks the reliable parallel-CPU path; pass
  `--embed-device mps` explicitly only for a small corpus that fits in GPU memory.
- **FTS5 lexical index now rebuilt over the full consolidated graph** at the end
  of `run_build_corpus` (`store.rebuild_fts`), so the handler's hybrid retrieval
  reliably activates instead of depending on the per-strategy-group rebuild; an
  absent `nodes_fts` silently degraded retrieval to dense-only.

---

## [1.6.0] - 2026-06-10

### Added

- **`scripts/check_standard_queries.py`** — a validation harness that runs the
  eight standard chat queries (one per genre plus a diary) against a live worker
  and asserts each returns at least one hit, printing the top results and scores.
- **`full` install extra (recommended)** — installs everything except dev tooling
  (kgdeps + viz + viz3d + mcp) in one step: `pip install -e ".[full]"` or
  `poetry install --extras "full"`.
- **`docs/INSTALLATION.md`** — full prerequisites, platform notes, the complete
  environment-variable reference, and troubleshooting.
- **`docs/CHAT_UI.md`** — walkthrough of the Streamlit *Knowledge Press* chat UI:
  search scopes, controls, synthesis providers, corpus-grounded image rendering,
  and troubleshooting.
- **README** — a `Requirements` table plus split `Quick Start — CLI` and
  `Quick Start — Docker` sections covering the full
  `make build-corpus → build → up → query` flow.
- **MCP servers** — `pycodekg` and `dockg` entries in `.mcp.json` for in-repo
  knowledge-graph tooling.

### Changed

- **Hybrid-retrieval stack pinned to `doc-kg==0.15.8` and `diary-kg==0.93.2`**,
  aligned across the `pyproject.toml` floors, `poetry.lock`, and the
  `docker/Dockerfile` `DOC_KG_VERSION` / `DIARY_KG_VERSION` args. These carry the
  FTS5/BM25 lexical channel + reciprocal-rank fusion that fixes exact-phrase
  queries (e.g. "pillar of salt") for both the book and diary corpora. Previously
  the lock floated below the Docker pins, so `poetry install` silently downgraded
  local dev to an older retrieval stack than the image shipped.
- `poetry.lock` refreshed for the new `full` extra and the pinned KG dependencies.
- `.gitignore` now excludes the local `.mcp.json` (developer-specific server paths).
- **`kgmodule-utils` bumped to `0.4.3`** (pyproject floor, `poetry.lock`, Docker
  `KGMODULE_UTILS_VERSION`, and `docker-compose.yml`) for the image-size fix below.
- **Worker retrieval is now semantic-first** (`docker/handler.py`). Book/genre/
  diary/`all` queries rank chunks by their own cosine distance via a direct
  LanceDB search (`metric("cosine")`, content-kind/genre/`reference.md` filters
  pushed into a pre-filter) instead of `DocKG.query()`'s graph-hop expansion.
  Diaries get the same treatment across their per-book DiaryKG vector tables, so
  the `all` corpus ranks both collections on one comparable scale. The KGRAG
  orchestrator is no longer on the query path. Clean passage text and diary
  timestamps are hydrated from SQLite (the LanceDB `text` column holds prefixed
  embed-text, not the clean passage).

### Removed

- **KGRAG orchestrator from the worker query path** — `handler.py` no longer
  initialises `KGRAG` or routes queries through `query`/`query_corpus`; retrieval
  is served directly from the LanceDB tables (see semantic-first change above).

### Fixed

- **Named-book queries returned zero or wrong hits** (e.g. "What does the Quran
  say about Moses?" surfaced *The Three Musketeers* / *Confucius* and no Quran
  passages, failing the genre check). Root cause: `DocKG.query()`'s hop-1
  expansion made every chunk inherit its seed's distance, collapsing each book
  into a flat score plateau and burying the true top matches below `max_nodes`.
  The semantic-first path ranks each chunk on its own cosine score, so all eight
  standard genre queries now return the correct book on top.
- **`all` corpus surfaced diaries above better book matches** — diary hits came
  through the orchestrator's flat-plateau scoring (~0.88) and out-sorted true
  cosine book scores. Both corpora now share the cosine scale, so books rank
  correctly (e.g. Plato's *Republic* tops a justice query; diaries fall to ~0.62).
- **Image Resolution selector was inert** — the chat UI's Resolution choice
  (Preview / Standard / Full) was displayed in the caption but never sent to the
  image backend, so every render came back at 1536×1024 regardless of selection.
  The selected pixel size is now threaded end-to-end (chat → worker `imagine`
  op → `ImageSynthesizer`) via a new `size` parameter, honored by the mflux
  local and serve backends.

---

## [1.5.0] - 2026-06-08

### Fixed

- **8 corpus books contained completely wrong text due to bad Gutenberg IDs** — catalog
  files held incorrect PG IDs that caused `gutenkg download` to fetch entirely different
  books. Affected titles:

  | Book | Wrong ID (fetched) | Correct ID |
  |---|---|---|
  | Flatland (Abbott) | 11 (Alice in Wonderland) | 201 |
  | A Princess of Mars (Burroughs) | 10662 (The Night Land) | 62 |
  | At the Earth's Core (Burroughs) | 62 (mislabeled; was Princess of Mars) | 123 |
  | The First Men in the Moon (Wells) | 18857 (Journey to Centre of Earth) | 1013 |
  | The Food of the Gods (Wells) | 1635 (Ion, Plato) | 11696 |
  | The Sea-Wolf (London) | 1608 (La Dame aux Camélias) | 1074 |
  | Germinal (Zola) | 5765 (Insectivorous Plants, Darwin) | 56528 |
  | On the Eve (Turgenev) | 11571 (Mr. Punch's History of WWI) | 6902 |

  All 5 catalog files corrected (`science-fiction.txt`, `science-fiction-additions.txt`,
  `american-literature.txt`, `french-literature.txt`, `russian-literature.txt`). Books
  re-downloaded with correct IDs; stale `.dockg/` per-book indices wiped and rebuilt via
  `gutenkg ingest` across all 4 affected genres (8 rebuilt, 59 skipped, 0 failed).

- **`scripts/regenerate_corpus_doc.py`** — refactored `main()` to extract `_collect_rows()`
  and `_render()` helpers; narrowed `except Exception` to `except ImportError` in
  `_gutenkg_version()`; fixed `import-outside-toplevel` lint suppression comment.

- **`docs/CORPUS.md`** — regenerated with provenance block (script, version, timestamp,
  host, elapsed time) at top and as an HTML comment at the bottom.

### Added

- **`gutenkg imagine --endpoint` option** — new CLI flag to specify the image
  server base URL at runtime. Falls back to `GUTENKG_IMAGE_ENDPOINT` env var;
  raises `UsageError` if neither is set.

### Changed

- **`imagine-local` extra removed** — `mflux` and its heavy ML dependencies
  (accelerate, mlx, sentencepiece, opencv-python, piexif, twine, etc.) have
  been dropped from `pyproject.toml` and `poetry.lock`. Local Apple Silicon
  generation was incompatible with the KG embeddings `transformers<4.57` pin.
  Image generation now exclusively targets the `mflux-serve` HTTP endpoint.

- **`gutenkg imagine` now requires an HTTP endpoint** — `cmd_imagine.py`
  replaces the local `image_gen.generate()` call with
  `image_gen.generate_via_server(server_url=endpoint, …)`. The previous
  `mflux` import fallback (with `sys.exit(1)`) is removed.

- **`GUTENKG_IMAGE_ENDPOINT` is now the canonical image endpoint env var** —
  `docker/.env.example` and `docker/docker-compose.yml` updated; `IMAGE_ENDPOINT`
  kept as a backward-compatible alias in Compose so existing deployments are
  unaffected.

- **`kg-rag` dependency moved from GitHub source to PyPI** — `pyproject.toml`
  now pins `kg-rag>=0.9.1` from PyPI; the `git+https://github.com/…` source
  reference is removed. `poetry.lock` updated accordingly.

- **Makefile: `start` added as alias for `up`** — `make start` and `make up`
  both launch the worker + chat Docker stack.

- **README install instructions simplified** — `pip install -e ".[imagine]"` is
  now the correct incantation; references to the removed `imagine-local` extra
  have been removed.

- **`.gitignore`: `.vscode/` excluded** — IDE settings directory added to the
  ignore list so editor-local configs are no longer tracked.

- **`.vscode/settings.json`: pytest args simplified** — removed `--tb=short`
  from `python.testing.pytestArgs`.

---

### Added

- **`kgmodule-utils[synthesis]` integration (v0.4.2)** — both `docker/handler.py`
  and `runpod/handler.py` now delegate synthesis and image generation to `kg_utils`
  rather than maintaining inline implementations:
  - `kg_utils.synthesis.TextSynthesizer` / `text_synthesizer_from_env()` — LLM text
    synthesis (`list_models`, `synthesize_rag`, `rewrite_for_image`) across oMLX,
    Ollama, and OpenAI backends; replaces inline `_synthesize()` / `_list_models()`.
  - `kg_utils.synthesis.ImageSynthesizer` / `image_synthesizer_from_env()` — image
    generation proxy (mflux-serve HTTP); replaces inline `_imagine()`.
  - `kg_utils.retrieval.hit_to_dict` + `attach_content_by_sqlite` — shared hit
    serialization and SQLite content-fetching; deduplicates code across both handlers.
  - `kg_utils.worker.WorkerClient` — HTTP client abstraction used by `chat.py`
    for `query`, `rewrite`, `imagine`, and `list_models`; replaces ad-hoc `httpx`
    calls and inline JSON error parsing.
  - `kg_utils.worker.handle_aux_ops` — dispatches `op=models` and `op=imagine`
    requests in the Docker handler.

- **Multi-provider synthesis** — chat UI sidebar shows a "Provider" dropdown
  (oMLX / Ollama / OpenAI) when synthesis is enabled. The selected backend is
  forwarded to the worker on every `query`, `rewrite`, and `imagine` call.
  Per-request backend routing in `handler.py` via `_synth_for_backend()` /
  `_image_for_backend()`.

- **`OLLAMA_ENDPOINT` and `OPENAI_API_KEY` env vars** — added to
  `docker/.env.example` and `docker/docker-compose.yml`. `OLLAMA_ENDPOINT`
  defaults to `http://host.docker.internal:11434/v1`; `OPENAI_API_KEY` empty
  by default.

- **`imagine-local` optional-dependency group** — `mflux>=0.17.5` split out from
  the `imagine` extra to avoid version conflicts between mflux (`transformers>=5.x`)
  and KG embeddings (`<4.57`). Install with `pip install -e ".[imagine,imagine-local]"`.

- **`docker/requirements-image.txt`** — new isolated requirements file for the
  mflux image server, used by `make image-server` to populate `.venv-image`.

- **`scripts/test_synthesis.py`** — standalone smoke test for `kg_utils.synthesis`
  backends. Tests `list_models`, `synthesize_rag`, and `rewrite_for_image` across
  oMLX (env default), Ollama, and OpenAI independently; connection failures are
  reported and the script continues to the next backend.

- **`docs/KG_UTILS_EXTRACTION_PLAN.md`** — design document for the `kg_utils`
  synthesis/retrieval/worker extraction: module layout, interface contracts, and
  migration plan.

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

- **`docker/image_gen.py` simplified** — `vlm_rewrite()`, `generate_via_server()`,
  and `generate_auto()` removed; those paths now live in `kg_utils.synthesis`.
  The module is now local Apple Silicon generation only (`generate()` via mflux),
  used exclusively by `docker/image_server.py`.

- **`make image-server`** — now creates an isolated `.venv-image` virtual environment
  and installs `docker/requirements-image.txt` before starting `image_server.py`,
  preventing mflux/transformers version conflicts with the main project venv.

- **Chat UI: Save/Render buttons moved to sidebar** — "💾 Save result" and
  "🎨 Render response" now operate on the most recent result from the sidebar
  rather than appearing inline per result card. Image generation and VLM rewrite
  route through `_imagine_via_worker()` and `_rewrite_via_worker()` (no direct
  `image_gen` or `openai` imports in `chat.py`).

- **`VLLM_ENDPOINT_URL` default now includes `/v1` suffix** — updated in
  `docker/.env.example` and `docker/docker-compose.yml`
  (`http://host.docker.internal:8080` → `http://host.docker.internal:8080/v1`).

- **`kgmodule-utils` bumped to `[synthesis]>=0.4.2`** — `pyproject.toml`
  dependency updated from `>=0.2.4` (no extras) to enable `kg_utils.synthesis`,
  `kg_utils.retrieval`, and `kg_utils.worker`. Build arg
  `KGMODULE_UTILS_VERSION: 0.4.2` added to `docker-compose.yml`.

- **`.gitignore` streamlined** — removed framework-specific boilerplate (Django,
  Flask, Scrapy, PyBuilder, Celery, SageMath, pixi, Marimo, LaTeX, Cursor,
  Abstra). Added `.claude/` and `.venv**` to project-local excludes.

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
