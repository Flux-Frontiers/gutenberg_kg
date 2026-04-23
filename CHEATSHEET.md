# GutenbergKG Cheatsheet

Quick reference for downloading, ingesting, and managing the corpus.

**Preferred:** use the `gutenkg` CLI (after `poetry install`).
Script equivalents (`python scripts/...`) are shown for reference.

---

## Installation

```bash
deactivate          # make sure no other venv is active
poetry env use python3.12
poetry install
gutenkg --help
```

---

## Genres

```bash
gutenkg list-genres
# python scripts/ingest.py --list-genres
```

Current genres: `ancient-classical`, `shakespeare`, `english-literature`,
`american-literature`, `french-literature`, `russian-literature`,
`philosophy`, `spanish`, `science-fiction`

---

## Downloading Books

### Search

```bash
gutenkg download search "science fiction"
gutenkg download search --author "Mary Shelley"
gutenkg download search --title "Frankenstein"
gutenkg download search --subject "dystopia" --max-results 10

# Note: Gutenberg's search endpoint is slow — prefer catalogs (see below)
```

### Download a single book

```bash
gutenkg download book 84 --genre science-fiction
gutenkg download book 84 --genre science-fiction --dry-run
gutenkg download book 84 --genre science-fiction --force

# script equivalent
python scripts/download_gutenberg.py download 84 --genre science-fiction
```

### Batch download from catalog

Pre-built genre catalogs live in `scripts/catalogs/`. Preferred over search.

```bash
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction --dry-run
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction --force

# script equivalent
python scripts/download_gutenberg.py catalog scripts/catalogs/science-fiction.txt --genre science-fiction
```

Catalog format: one book per line, `<gutenberg_id>[TAB<optional title>]`. Lines starting with `#` are comments.

### Fetch an entire genre in one step

```bash
# Interactive (Enter=yes, n=skip, q=quit)
gutenkg download fetch-genre science-fiction

# Custom search query
gutenkg download fetch-genre science-fiction --query "dystopia"

# Download all without prompting
gutenkg download fetch-genre science-fiction --yes

# Preview only
gutenkg download fetch-genre science-fiction --dry-run

# script equivalent
python scripts/download_gutenberg.py fetch-genre science-fiction --yes
```

Reports saved to `reports/fetch_genre_<genre>_<timestamp>.md`.

### Survey what's downloaded

```bash
gutenkg download survey
gutenkg download survey --genre science-fiction

# script equivalent
python scripts/download_gutenberg.py survey --genre science-fiction
```

Output shows `md=✓/✗  ref=✓/✗  kg=✓/✗` per book.

---

## Building Knowledge Graphs (Ingest)

### Build all genres

```bash
gutenkg ingest
# python scripts/ingest.py
```

### Build specific genre(s)

```bash
gutenkg ingest --genre science-fiction
gutenkg ingest --genre shakespeare --genre philosophy

# script equivalent
python scripts/ingest.py --genre science-fiction
```

### Force rebuild (wipes existing .dockg first)

```bash
gutenkg ingest --force-build
gutenkg ingest --force-build --genre american-literature
```

### Build and push to git (per-genre commits)

```bash
gutenkg ingest --push
gutenkg ingest --force-build --push
gutenkg ingest --genre science-fiction --push
```

### Dry run (preview only)

```bash
gutenkg ingest --dry-run
gutenkg ingest --dry-run --push
```

### Re-register with KGRAG (without rebuilding)

```bash
gutenkg ingest --force-register
gutenkg ingest --force-register --genre philosophy
```

Reports are auto-saved to `reports/ingest_YYYY-MM-DD_HHMMSS.md` after every run.

---

## Author Index

Every `reference.md` carries author provenance (Born / Died / Wikipedia /
Gutenberg agent ID). `corpus/authors/` aggregates those per-book facts into
one page per author.

```bash
# Rebuild corpus/authors/ from existing reference.md files
python scripts/build_author_index.py

# Also re-fetch RDF and patch reference.md files missing provenance
python scripts/build_author_index.py --refresh

# Preview
python scripts/build_author_index.py --dry-run
python scripts/build_author_index.py --refresh --dry-run
```

New downloads already land with full provenance in `reference.md` — use
`--refresh` only for books that predate the RDF fetch or had a transient
network failure.

---

## After Cloning (Rebuild LanceDB)

LanceDB vector indices are not committed to git. After cloning, rebuild them:

```bash
gutenkg rebuild-lancedb
gutenkg rebuild-lancedb --genre science-fiction
gutenkg rebuild-lancedb --genre shakespeare --genre philosophy

# script equivalent
bash scripts/rebuild_lancedb.sh
bash scripts/rebuild_lancedb.sh science-fiction
```

---

## Git / Pushing

Pushes are handled automatically by `gutenkg ingest --push` (one commit per genre).
For manual pushes:

```bash
git add corpus/science-fiction/
git commit -m "chore: add science-fiction books"
git push
```

Only source Markdown and `reference.md` files are tracked. Knowledge-graph
artifacts (`.dockg/graph.sqlite` and `.dockg/lancedb/`) are gitignored — they
are regenerable from the source text via `gutenkg ingest --force-build`.

---

## Typical Workflows

### Add a new genre from scratch

```bash
# 1. Download via catalog (fastest)
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction

# 2. Survey what you have
gutenkg download survey --genre science-fiction

# 3. Build DocKGs and push
gutenkg ingest --genre science-fiction --push

# 4. Refresh the author index so the new authors appear
python scripts/build_author_index.py
```

### Rebuild a broken genre

```bash
gutenkg ingest --force-build --genre philosophy --push
```

### Full corpus rebuild and push

```bash
gutenkg ingest --force-build --push
```

### Check ingest status across corpus

```bash
gutenkg download survey
```

---

## File Layout

```
gutenberg_kg/
├── corpus/
│   ├── <genre>/                            # ancient-classical, shakespeare, …
│   │   └── <Book Title>/
│   │       ├── <slug>.md                   # Full text (Markdown)
│   │       ├── reference.md                # Author provenance + Gutenberg metadata
│   │       └── .dockg/                     # Built by ingest (gitignored)
│   │           ├── graph.sqlite            # DocKG graph
│   │           └── lancedb/                # Vector index
│   └── authors/                            # Built by build_author_index.py
│       ├── index.md                        # Master alphabetical author table
│       └── <author_slug>/author.md         # Born, died, Wikipedia, works
├── src/gutenberg_kg/
│   └── cli/
│       ├── main.py                         # gutenkg CLI entry point
│       ├── options.py                      # REPO_ROOT, CORPUS_ROOT, ALL_GENRES
│       ├── cmd_download.py                 # gutenkg download *
│       ├── cmd_ingest.py                   # gutenkg ingest
│       └── cmd_rebuild.py                  # gutenkg rebuild-lancedb
├── scripts/
│   ├── ingest.py                           # Ingest engine (called by CLI)
│   ├── download_gutenberg.py               # Download engine (called by CLI)
│   ├── build_author_index.py               # Author-corpus post-processor
│   ├── rebuild_lancedb.sh                  # Shell fallback for LanceDB rebuild
│   └── catalogs/                           # Per-genre batch download catalogs
│       └── science-fiction.txt
├── reports/
│   └── ingest_YYYY-MM-DD_HHMMSS.md         # Auto-saved ingest reports
├── DOWNLOAD_PIPELINE.md                    # End-to-end download-pipeline reference
├── pyproject.toml                          # Poetry package (gutenkg entry point)
└── .gitignore                              # Excludes .dockg/, __pycache__, etc.
```
