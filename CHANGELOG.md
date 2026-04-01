# Changelog

All notable changes to GutenbergKG are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added

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
  - `fetch-genre` subcommand — search → confirm → download → report in one step
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

- LanceDB vector indices are now **local-only** (gitignored). Only `graph.sqlite`
  is committed, keeping push sizes manageable. Rebuild with `gutenkg rebuild-lancedb`
  after cloning.
- Git push strategy changed from single monolithic push to **per-genre batched commits**
  via `gutenkg ingest --push`.

### Fixed

- `graph.sqlite` corruption crash — `ingest.py` now detects and auto-wipes corrupt
  or empty sqlite files before attempting a build, preventing `sqlite3.DatabaseError`
  on partial builds.
- `--force-build` now wipes `.dockg/` before rebuilding, preventing stale-state errors.
