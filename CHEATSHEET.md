# GutenbergKG Cheatsheet

Quick reference for downloading, ingesting, and managing the corpus.

Use the `gutenkg` CLI (after `poetry install`).

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

Genres are stored in `corpus/genres.json`. Add new genres without touching code.

```bash
gutenkg genres init                              # seed corpus/genres.json (first time)
gutenkg genres list                              # show registered genres
gutenkg genres add medieval-lit --source gutenberg   # add a Gutenberg genre
gutenkg genres add my-ia-collection --source ia      # add an Internet Archive genre
```

`genres add` auto-initializes the file if it doesn't exist yet.

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
```

### Batch download from catalog

Pre-built genre catalogs live in `scripts/catalogs/`. Preferred over search.

```bash
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction --dry-run
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction --force
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
```

Reports saved to `reports/fetch_genre_<genre>_<timestamp>.md`.

### Survey what's downloaded

```bash
gutenkg download survey
gutenkg download survey --genre science-fiction
```

Output shows `md=✓/✗  ref=✓/✗  kg=✓/✗` per book.

---

## Building Knowledge Graphs (Ingest)

### Build all genres

```bash
gutenkg ingest
```

### Build specific genre(s)

```bash
gutenkg ingest --genre science-fiction
gutenkg ingest --genre shakespeare --genre philosophy
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
gutenkg authors

# Also re-fetch RDF and patch reference.md files missing provenance
gutenkg authors --refresh

# Preview
gutenkg authors --dry-run
gutenkg authors --refresh --dry-run
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
# 1. Register the genre (no code changes needed)
gutenkg genres add science-fiction --source gutenberg

# 2. Download via catalog (fastest)
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction

# 3. Survey what you have
gutenkg download survey --genre science-fiction

# 4. Build DocKGs and push
gutenkg ingest --genre science-fiction --push

# 5. Refresh the author index so the new authors appear
gutenkg authors
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
│   ├── genres.json                         # Genre registry — edit here to add genres
│   ├── <genre>/                            # ancient-classical, shakespeare, …
│   │   └── <Book Title>/
│   │       ├── <slug>.md                   # Full text (Markdown)
│   │       ├── reference.md                # Author provenance + Gutenberg metadata
│   │       └── .dockg/                     # Built by ingest (gitignored)
│   │           ├── graph.sqlite            # DocKG graph
│   │           └── lancedb/                # Vector index
│   └── authors/                            # Built by `gutenkg authors`
│       ├── index.md                        # Master alphabetical author table
│       └── <author_slug>/author.md         # Born, died, Wikipedia, works
├── src/gutenberg_kg/
│   ├── genres.py                           # Loads corpus/genres.json; exposes ALL_GENRES etc.
│   ├── authors.py                          # Author-index logic (gutenkg authors)
│   └── cli/
│       ├── main.py                         # gutenkg CLI entry point
│       ├── options.py                      # REPO_ROOT, CORPUS_ROOT, ALL_GENRES
│       ├── cmd_authors.py                  # gutenkg authors
│       ├── cmd_download.py                 # gutenkg download *
│       ├── cmd_genres.py                   # gutenkg genres init/list/add
│       ├── cmd_ingest.py                   # gutenkg ingest
│       └── cmd_rebuild.py                  # gutenkg rebuild-lancedb
├── scripts/
│   ├── process_logo.py                     # Logo transparency + variant generator
│   ├── benchmark_embedders.py              # Embedder benchmarking utility
│   └── catalogs/                           # Per-genre batch download catalogs
│       └── science-fiction.txt
├── reports/
│   └── ingest_YYYY-MM-DD_HHMMSS.md         # Auto-saved ingest reports
├── DOWNLOAD_PIPELINE.md                    # End-to-end download-pipeline reference
├── pyproject.toml                          # Poetry package (gutenkg entry point)
└── .gitignore                              # Excludes .dockg/, __pycache__, etc.
```
