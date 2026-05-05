# Changelog

All notable changes to GutenbergKG are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

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
