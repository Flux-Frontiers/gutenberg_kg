---
name: gutenkg
description: >
  Expert knowledge for the gutenkg CLI — the GutenbergKG Knowledge Press tool for
  downloading, ingesting, and managing a Project Gutenberg text corpus. Use this skill
  when the user asks about: downloading books (single book, batch catalog, search,
  fetch-genre), managing genres (init, add, list), building DocKG knowledge graph
  indices (gutenkg ingest), rebuilding indices after a clone, managing the author
  index, surveying corpus download/ingest status, adding new genres, running batch
  corpus expansion workflows, or troubleshooting gutenkg errors. Also triggers for
  questions about the catalog file format, corpus directory layout, the
  text-to-markdown conversion pipeline, or which Gutenberg IDs to use for specific
  works. Repo lives at /Users/egs/repos/gutenberg_kg/.
---

# gutenkg Skill

`gutenkg` is the CLI for GutenbergKG. Run from repo root after `poetry install`.

Repo: `/Users/egs/repos/gutenberg_kg/`
Catalog files: `scripts/catalogs/<genre>.txt`
Corpus: `corpus/`

---

## Standard Batch Workflow (add books from wishlist)

```bash
# 1. Download a catalog
gutenkg download catalog scripts/catalogs/philosophy.txt --genre philosophy

# 2. Build DocKG indices + register with KGRAG
gutenkg ingest --genre philosophy

# 3. Refresh author pages
gutenkg authors

# 4. Commit
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
gutenkg download survey            # all genres: md=✓/✗  ref=✓/✗  kg=✓/✗
gutenkg download survey --genre russian-literature
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
| `ingest` | `--genre` (repeatable), `--force-build`, `--force-register`, `--push`, `--dry-run` |
| `genres add <name>` | `--source gutenberg\|ia` |
| `authors` | `--refresh`, `--dry-run` |
| `rebuild-indices` | `--genre` |

---

## Catalog File Format

```
# Lines starting with # are comments
600     Notes from Underground      # id[TAB title_override]
52263   Twilight of the Idols
2680                                # id only — title pulled from OPDS
```

Three columns: `<gutenberg_id>[\t<title_override>[\t<genre_override>]]`

---

## Corpus Layout

```
corpus/
├── genres.json                 # genre registry (single source of truth)
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

## Key Gutenberg IDs (provenance experiment — missing works)

| Work | Gutenberg ID | Genre |
|---|---|---|
| Tolstoy *Death of Ivan Ilyich* | 600 | russian-literature |
| Nietzsche *Twilight of the Idols* | 52263 | philosophy |
| Seneca *Letters to Lucilius* | search: `gutenkg download search --author "Seneca"` | ancient-classical |
| Seneca *De Providentia* | not standard on PG — manual search needed | ancient-classical |

Note: The **Long and Hays translations** of *Meditations* are under copyright and not on Gutenberg. The corpus file (#2680) uses the **Casaubon translation** — this is the only public-domain English MA on PG. Quotes cited from Long/Hays will fail substring verification against the corpus.

---

## Pitfalls

- `--force` required to re-download a book whose `<slug>.md` already exists.
- `ingest` skips books with an existing `.dockg/` — use `--force-build` to rebuild.
- `.dockg/` is gitignored — always run `rebuild-indices` after a fresh clone.
- `download search` is slow — prefer catalog files for known IDs.
- `gutenkg download search` → `download fetch-genre` for whole-genre interactive flow.
