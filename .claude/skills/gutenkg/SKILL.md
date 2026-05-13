---
name: gutenkg
description: >
  Expert knowledge for the gutenkg CLI — GutenbergKG Knowledge Press for downloading,
  ingesting, and managing a Project Gutenberg text corpus. Use when asked about:
  downloading books (book/catalog/search/fetch-genre), Internet Archive downloads
  (ia download/catalog/search/survey), genre management (init/add/list/list-genres),
  building DocKG indices (ingest), rebuilding indices after clone, author index,
  corpus status/survey, snapshots (save/list/show/diff), live stats (status),
  3-D visualiser (viz3d), growth timeline (viz-timeline), batch workflows, catalog
  file format, corpus layout, text-to-markdown pipeline, or Gutenberg IDs.
  Repo: /Users/egs/repos/gutenberg_kg/.
---

# gutenkg Skill

`gutenkg` is the CLI for GutenbergKG (v1.2.0). Run from repo root after `poetry install`.

Repo: `/Users/egs/repos/gutenberg_kg/`
Catalog files: `scripts/catalogs/<genre>.txt`
Corpus: `corpus/`
Snapshots: `corpus/.snapshots/`

---

## Standard Batch Workflow (add books from wishlist)

```bash
# 1. Download a catalog
gutenkg download catalog scripts/catalogs/philosophy.txt --genre philosophy

# 2. Build DocKG indices + register with KGRAG
gutenkg ingest --genre philosophy

# 3. Refresh author pages
gutenkg authors

# 4. Save a corpus snapshot
gutenkg snapshot save

# 5. Commit
git add corpus/philosophy/
git commit -m "feat: add philosophy batch"
git push
```

Multi-genre: download all catalogs first, then `gutenkg ingest` once (skips already-built books).

---

## Common Operations

### Single book

```bash
gutenkg download search --author "Herman Melville"      # find ID
gutenkg download book 2701 --genre american-literature  # download
gutenkg ingest --genre american-literature
```

### Internet Archive book

```bash
gutenkg ia search "audel electricians"               # find IA identifier
gutenkg ia download audelselectriciansguide01ande --genre audel-electric
gutenkg ingest --genre audel-electric
```

### Add a brand-new genre

```bash
gutenkg genres add medieval-literature --source gutenberg
# Create scripts/catalogs/medieval-literature.txt
gutenkg download catalog scripts/catalogs/medieval-literature.txt --genre medieval-literature
gutenkg ingest --genre medieval-literature
```

### After cloning (indices are gitignored)

```bash
gutenkg rebuild-indices                      # all genres
gutenkg rebuild-indices --genre philosophy   # single genre
```

### Status check

```bash
gutenkg status                             # live Rich table (reads SQLite directly)
gutenkg status --json                      # machine-readable JSON
gutenkg status --update-readme             # also patch badge URLs in README.md
gutenkg download survey                    # per-book md=✓/✗  ref=✓/✗  kg=✓/✗
```

### Snapshots

```bash
gutenkg snapshot save                      # capture current metrics
gutenkg snapshot list                      # show all saved snapshots
gutenkg snapshot show                      # most recent snapshot
gutenkg snapshot diff                      # compare last two snapshots
```

### Visualisation

```bash
gutenkg viz3d                              # 3-D knowledge tree forest
gutenkg viz-timeline                       # corpus growth chart (2d default)
gutenkg viz-timeline --type 3d             # normalised 3-D scatter
```

### Force re-download / force rebuild

```bash
gutenkg download book 2701 --genre american-literature --force   # re-download
gutenkg ingest --force-build --genre philosophy                  # wipe + rebuild KG
```

---

## Command Reference

Full flags and options: see [references/commands.md](references/commands.md).

| Group | Key flags |
|---|---|
| `download book <id>` | `--genre`, `--force`, `--dry-run` |
| `download catalog <file>` | `--genre`, `--force`, `--dry-run` |
| `download search "<q>"` | `--author`, `--title`, `--subject`, `--language`, `--max-results` |
| `download fetch-genre <g>` | `--query`, `--yes`, `--dry-run` |
| `download survey` | `--genre` |
| `ingest` | `--genre` (repeatable), `--force-build`, `--force-register`, `--push`, `--dry-run`, `--registry` |
| `ia download <id>` | `--genre`, `--title`, `--force`, `--dry-run` |
| `ia catalog <file>` | `--genre`, `--force`, `--dry-run` |
| `ia search <q>` | `--max-results` |
| `ia survey` | `--genre` |
| `genres add <name>` | `--source gutenberg\|ia` |
| `genres init / list` | — |
| `list-genres` | — |
| `authors` | `--refresh`, `--dry-run` |
| `rebuild-indices` | `--genre`, `--force-build` |
| `snapshot save/list/show/diff` | — |
| `status` | `--json`, `--update-readme`, `--registry` |
| `viz3d` | `--corpus`, `--width`, `--height` |
| `viz-timeline` | `--snapshots`, `--type [2d\|3d]` |

---

## Catalog File Format

```
# Lines starting with # are comments
600     Notes from Underground      # id[TAB title_override]
52263   Twilight of the Idols
2680                                # id only — title pulled from OPDS
```

Three columns: `<gutenberg_id>[\t<title_override>[\t<genre_override>]]`

IA catalog format: `<ia_identifier>[\t<genre>]` (one per line, `#` comments OK)

---

## Corpus Layout

```
corpus/
├── genres.json                 # genre registry (single source of truth)
├── .snapshots/                 # snapshot-*.json files (gitignored)
├── <genre>/
│   └── <Book Title>/
│       ├── <slug>.md           # full text with Markdown heading tree
│       ├── reference.md        # author provenance + PG metadata
│       └── .dockg/             # gitignored — built by ingest
└── authors/
    ├── index.md
    └── <author_slug>/author.md
```

---

## Key Gutenberg IDs

| Work | Gutenberg ID | Genre |
|---|---|---|
| Tolstoy *Death of Ivan Ilyich* | 600 | russian-literature |
| Nietzsche *Twilight of the Idols* | 52263 | philosophy |
| Seneca *Letters to Lucilius* | search: `gutenkg download search --author "Seneca"` | ancient-classical |

Note: **Long and Hays translations** of *Meditations* are under copyright — not on Gutenberg. Corpus file #2680 uses the **Casaubon translation** (only public-domain English MA on PG).

---

## Pitfalls

- `--force` required to re-download a book whose `<slug>.md` already exists.
- `ingest` skips books with an existing `.dockg/` — use `--force-build` to rebuild.
- `.dockg/` is gitignored — always run `rebuild-indices` after a fresh clone.
- `download search` is slow — prefer catalog files for known IDs.
- `gutenkg download search` → `download fetch-genre` for whole-genre interactive flow.
- `snapshot` requires prior `gutenkg ingest` — viz-timeline needs at least one saved snapshot.
- `viz3d` shows only ingested books (with `.dockg/graph.sqlite`) — run `ingest` first.
- `status` reads SQLite directly — does not require a rebuild and is safe for CI.
