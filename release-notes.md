# Release Notes -- v1.0.0

> Released: 2026-05-03

### Added

- **Internet Archive ingestion** -- `gutenkg ia` CLI group with `search`, `download`,
  `catalog`, and `survey` subcommands. Fetches books from archive.org, converts OCR
  text to structured Markdown (same pipeline as Gutenberg), and deposits under `corpus/`.
- **`scripts/download_ia.py`** -- promoted from `audel_kg/` sub-project into the main
  scripts directory as a first-class source alongside `download_gutenberg.py`.
- **`src/gutenberg_kg/cli/cmd_ia.py`** -- Click command group for IA operations.
- **`ALL_IA_GENRES`** in `cli/options.py` -- separate genre registry for IA-sourced corpora
  (`audel-electric` initial entry).
- **`HANDOFF_IA.md`** -- architecture handoff document for the IA integration work.
- **`gutenkg` CLI** -- full Click-based command-line interface (`src/gutenberg_kg/`),
  matching the code_kg/doc_kg package pattern. Entry point: `gutenkg`.
  - `gutenkg ingest` -- build DocKG indices, register with KGRAG, push per-genre
  - `gutenkg download book/catalog/search/fetch-genre/survey` -- all download operations
  - `gutenkg rebuild-lancedb` -- rebuild LanceDB vector indices after clone
  - `gutenkg list-genres` -- print all known genres
- **`pyproject.toml`** -- Poetry package scaffold; `poetry install` installs `gutenkg`
- **`CHEATSHEET.md`** -- full quick-reference for all CLI commands and workflows
- **`scripts/ingest.py`** -- major upgrade with Rich reporting, `--push`, `--list-genres`,
  auto-wipe on corrupt sqlite, force-build wipes stale `.dockg/`
- **`scripts/download_gutenberg.py`** -- major upgrade with `survey`, `fetch-genre`,
  `--genre`, `--force`, `--dry-run`, idempotent downloads, science-fiction genre
- **Science-fiction genre** -- 14 books ingested (445K nodes, 4.5M edges total corpus)

### Changed

- **Re-framed as "The Knowledge Press"** -- universal ingestion engine for digitized
  text corpora. Any public domain text source (Project Gutenberg, Internet Archive,
  local files) feeds the same pipeline.
- **`pyproject.toml`** description and classifier updated (Alpha -> Production/Stable).
- **README.md** -- broader scope, Project Gutenberg logo removed, affiliation disclaimer
  added, "Public Domain" badge no longer links to gutenberg.org.
- LanceDB indices are now local-only (gitignored); only `graph.sqlite` is committed.
- Per-genre batched commits via `gutenkg ingest --push`.

### Fixed

- `graph.sqlite` corruption crash on partial builds.
- `--force-build` stale-state error when `.dockg/` was not wiped first.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
