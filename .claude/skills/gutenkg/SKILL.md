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

### Move a book between genres / remove a duplicate

There is **no `gutenkg` deregister command** — the KGRAG registry bakes the genre into each
KG name (`gutenberg-<genre>-<slug>-doc`), so moving a book's dir leaves a stale registry
entry pointing at the old genre. Fix it with the **`kgrag`** CLI:

```bash
# 1. Deregister the old-genre entry (name from: kgrag list, or the registry)
kgrag unregister gutenberg-science-fiction-the-call-of-cthulhu-doc --yes

# 2. Move the whole dir with plain mv (carries .dockg/ along — no rebuild needed)
mv "corpus/science-fiction/The Call of Cthulhu" "corpus/horror/The Call of Cthulhu"

# 3. Re-register under the new genre (upsert-only; skips books lacking .dockg)
gutenkg re-register --genre horror

# 4. Update BOTH catalog files (source of truth) + verify
#    - remove the id from scripts/catalogs/<old-genre>.txt
#    - add    the id to   scripts/catalogs/<new-genre>.txt
gutenkg audit                       # 0 errors = no duplicate Gutenberg IDs across genres
```

For a pure **duplicate** (same id already built in the target genre): `kgrag unregister` the
losing entry, `rm -rf` its dir, drop its catalog line, then `gutenkg audit`.

`gutenkg audit` catches cross-genre duplicate Gutenberg IDs — run it after any move.
`kgrag list` shows all registered KG names; `kgrag unregister <name|uuid> --yes` removes one.

### First run after install

```bash
gutenkg init                               # fetch the spaCy + embedder models
```

Do this before `chunk-diaries` / `ingest` / `build-corpus`, or they download models
mid-build.

### After cloning (indices are gitignored)

```bash
gutenkg rebuild-indices                      # rebuilds EVERYTHING: prose → .dockg/, diaries → .diarykg/
gutenkg rebuild-indices --genre philosophy   # single prose genre
gutenkg rebuild-indices --genre diaries      # diaries only (routes to the DiaryKG pipeline)
```

`rebuild-indices` (and `ingest`) auto-detect the `diaries` genre and route it through the
DiaryKG pipeline — `chunk-diaries` (`.md` → `.diary_source.psv` → `.diary/`, Gutenberg parser)
then `build-diaries` (`.diary/` → `.diarykg/`, no SIMILAR_TO) — instead of the standard
`.dockg/` build. So one command reconstructs the whole corpus after a clone. You can also run
the diary stages directly:

```bash
gutenkg chunk-diaries                        # .md → .diary/  (per-book format from .diary_format)
gutenkg build-diaries                        # .diary/ → .diarykg/
```

`chunk-diaries` needs the spaCy model: `python -m spacy download en_core_web_sm` (once).
Per-book date format comes from a committed `.diary_format` file (`pepys` | `evelyn` | `boswell`).

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

`viz-timeline` plots the snapshots `snapshot save` wrote — no snapshots, no chart.

### Light-field output (Looking Glass)

One book's knowledge tree, grown by space colonization so its limbs reach its own
text chunks: the canopy's shape is the book's structure, not decoration.

```bash
gutenkg quilt --book Hamlet                # rasterise via PyVista -> quilt
gutenkg quilt --book Hamlet --season autumn --cast
gutenkg pov   --book Hamlet                # same tree as analytic POV-Ray SDL
gutenkg pov   --book Hamlet --render       # ...and ray-trace it (needs povray)
```

`quilt` prints the depth budget before every render — a blown disparity budget shows
up there, for free, rather than after the render. `pov` writes primitives rather than
triangles, so the scene is one to two orders of magnitude smaller with exact
silhouettes at any zoom. Both need the `viz3d` / `pov` extras.

### Query, chat, imagine

```bash
gutenkg query "whale"                      # search the local corpus; no Docker
gutenkg chat                               # Streamlit UI ([chat] extra + worker)
gutenkg imagine --query "Ahab"             # corpus text -> scene -> image
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
| `audit` | `--genre`, `--json`, `--registry` |
| `re-register` | `--genre`, `--dry-run`, `--registry` |
| `rebuild-indices` | `--genre`, `--force-build` |
| `kgrag unregister <name>` | `--yes`, `--registry` (deregister a moved/removed book) |
| `snapshot save/list/show/diff` | — |
| `status` | `--json`, `--update-readme`, `--registry` |
| `viz3d` | `--corpus`, `--width`, `--height` |
| `viz-timeline` | `--snapshots`, `--type [2d\|3d]` |
| `quilt` | `--book`, `--spec`, `--season`, `--entities`, `--zoom`, `--orbit`, `--cast` |
| `pov` | `--book`, `--season`, `--render` |
| `build-corpus` | `--genre`, `--embed-device`, `--embed-batch-size` |
| `build-diaries` / `chunk-diaries` | — (stages of the diary pipeline) |
| `query <q>` | — (local search; no Docker) |
| `chat` | — (Streamlit UI; `[chat]` extra) |
| `imagine` | `--prompt`, `--query` |
| `init` | — (fetch spaCy + embedder models) |

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
├── .snapshots/                 # <tree-hash>.json + manifest.json (gitignored)
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
- Registry KG names embed the genre (`gutenberg-<genre>-<slug>-doc`), so moving a book's dir
  orphans its old entry. There is no `gutenkg` deregister — use `kgrag unregister <name> --yes`,
  then `gutenkg re-register --genre <new>`. Run `gutenkg audit` to catch cross-genre duplicate IDs.
