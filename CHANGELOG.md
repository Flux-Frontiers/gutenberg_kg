# Changelog

All notable changes to GutenbergKG are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added

### Changed

### Removed

### Fixed

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
