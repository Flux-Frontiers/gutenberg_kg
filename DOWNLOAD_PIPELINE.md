# Download Pipeline

A technical reference for how a raw Project Gutenberg text becomes a
structured Markdown file with full author provenance under `corpus/`.

This document covers **download only** — the ingest pipeline (DocKG build +
KGRAG registration) is described in [`README.md`](README.md).

---

## 1. End-to-End Flow

```
                        ┌─────────────────────────────────┐
                        │  Project Gutenberg (network)    │
                        │  ─────────────────────────────  │
                        │   OPDS feed .opds               │
                        │   RDF catalog pg<id>.rdf        │
                        │   Plain text pg<id>.txt         │
                        └────────────────┬────────────────┘
                                         │
                                         ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │ fetch_metadata(id)   ──┐                                        │
     │   ├─ OPDS → title, author, subjects, summary, language, rights  │
     │   └─ RDF  → author_birth, author_death, author_url,             │
     │            author_agent_id                                      │
     └─────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │ download_book(id)                                                │
     │   1. idempotence check  (skip if <slug>.md already exists)       │
     │   2. fetch plain text                                            │
     │   3. strip_boilerplate()    — remove PG header/footer markers    │
     │   4. text_to_markdown()     — detect structure, emit headings    │
     │   5. write_reference()      — metadata sidecar                   │
     └─────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │ corpus/<genre>/<Title>/                                         │
     │   ├── <slug>.md        — full text with Markdown heading tree   │
     │   └── reference.md     — author provenance + Gutenberg metadata │
     └─────────────────────────────────────────────────────────────────┘
                                         │
                 (periodically, after a batch of downloads)
                                         │
                                         ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │ build_author_index.py                                            │
     │   ├─ parse every corpus/*/*/reference.md                        │
     │   ├─ [--refresh] re-fetch RDF for books missing provenance       │
     │   │             and patch their reference.md in place            │
     │   ├─ write corpus/authors/<slug>/author.md    (one per author)   │
     │   └─ write corpus/authors/index.md            (master table)     │
     └─────────────────────────────────────────────────────────────────┘
```

---

## 2. Entry Points

| Command | Does |
|---|---|
| `gutenkg download book <id> [--genre G]` | Single book |
| `gutenkg download catalog <file> [--genre G]` | Batch from a catalog file |
| `gutenkg download search "<query>" [--author A] [--title T]` | Gutenberg catalog search |
| `gutenkg download fetch-genre <G>` | Search + confirm + download, whole genre |
| `gutenkg download survey [--genre G]` | Show what's downloaded/indexed |
| `python scripts/build_author_index.py [--refresh]` | Rebuild author pages |

The `gutenkg` CLI is a thin Click wrapper around the two engine scripts:

- [`scripts/download_gutenberg.py`](scripts/download_gutenberg.py) — download engine
- [`scripts/build_author_index.py`](scripts/build_author_index.py) — author-corpus post-processor

---

## 3. Data Sources

Every book pulls from up to three Gutenberg endpoints:

| Endpoint | URL pattern | Used for |
|---|---|---|
| **OPDS feed** | `https://www.gutenberg.org/ebooks/{id}.opds` | Title, author name, subjects, summary, language, rights, published date |
| **RDF catalog** | `https://www.gutenberg.org/cache/epub/{id}/pg{id}.rdf` | Author birth year, death year, Wikipedia URL, Gutenberg agent ID |
| **Plain text** | `https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt` | The book itself (UTF-8 with BOM) |
| **Search** | `https://www.gutenberg.org/ebooks/search.opds/?query=…` | Used only by `download search` / `fetch-genre` |

All four live in module-level constants at the top of
[`download_gutenberg.py`](scripts/download_gutenberg.py).

---

## 4. Downloading One Book

### 4.1 Metadata fetch — `fetch_metadata(ebook_id)`

Fetches the OPDS atom entry and extracts:

- `title` — `<atom:title>`
- `author` — `<atom:author><atom:name>`, reversed from `"Last, First"` → `"First Last"`
- `published` — `<atom:published>` (date Gutenberg added the ebook, not original publication)
- `rights` — `<atom:rights>`
- `subjects` — all `<atom:category term="...">`
- `language` — `<dcterms:language>`
- `summary`, `note` — parsed from the XHTML block inside `<atom:content>`
- `gutenberg_url` — synthesized (`/ebooks/{id}`)

Immediately after the OPDS parse, `fetch_metadata` calls `_fetch_rdf_author(id)`
and merges the result into the same `meta` dict (silent failure — a missing
RDF doesn't break the download).

### 4.2 RDF enrichment — `_fetch_rdf_author(ebook_id)`

The RDF catalog exposes the data the OPDS feed omits. Parses the first
`<pgterms:agent>` element and extracts:

| Field | Source |
|---|---|
| `author_birth` | `<pgterms:birthdate>` (year as string, may be negative for BCE) |
| `author_death` | `<pgterms:deathdate>` |
| `author_url` | First `<pgterms:webpage rdf:resource="…wikipedia.org…">` |
| `author_agent_id` | Integer extracted from `rdf:about="2009/agents/N"` |

BCE years are stored as negative integers (Homer: `-750 / -650`).

### 4.3 Idempotence check

Before downloading text, `download_book()` checks whether
`corpus/<genre>/<title>/<slug>.md` already exists. If yes, it prints `[=] already
downloaded` and returns early. Use `--force` to override.

Metadata fetch happens **before** the idempotence check because it provides the
title needed to compute the output path.

### 4.4 Text download

Hits `pg{id}.txt` with retries + exponential backoff (`fetch_url()`:
3 attempts, 2×/4× backoff). Always decodes as `utf-8-sig` to transparently
strip the Gutenberg BOM.

### 4.5 Boilerplate stripping — `strip_boilerplate()`

Removes everything before `*** START OF THE PROJECT GUTENBERG EBOOK … ***` and
everything after `*** END OF THE PROJECT GUTENBERG EBOOK … ***`. If markers
aren't found the full text is kept (better to have noise than to lose content).

### 4.6 Structure detection — `text_to_markdown()`

Two pre-passes before heading detection:

1. **Front-matter skip** — drops "Produced by…", "Transcribed by…",
   "E-text prepared by…" credit blocks if they appear at the top.
2. **Table-of-contents skip** — detects a `CONTENTS` / `TABLE OF CONTENTS`
   block in the first ~200 lines and excludes it from the output (redundant
   once headings are emitted structurally).

Heading detection (`_is_heading()`) walks the `HEADING_PATTERNS` list in
priority order. Supported patterns:

| Pattern | Example | Level |
|---|---|---|
| `THE FIRST/SECOND/… BOOK` | `THE FIRST BOOK` (Meditations) | `##` |
| `VOLUME/BOOK/PART` + numeral | `BOOK THE FIRST`, `VOLUME II`, `PART III` | `##` |
| `Book the First — Recalled to Life` | Dickens style | `##` |
| `ACT` + numeral | `ACT III` | `##` |
| `CHAPTER` + numeral | `CHAPTER XIV.`, `Chapter 3` | `##` |
| `SCENE` + numeral | `SCENE II` | `###` |
| `LETTER` + numeral | `Letter 4` (epistolary novels) | `##` |
| Bible books | `The First Book of Moses: Called Genesis` | `##` |
| Old/New Testament divider | `The Old Testament` | `##` |
| `STAVE` + numeral | `STAVE I` (A Christmas Carol) | `##` |
| `I. A SCANDAL IN BOHEMIA` | Roman + ALL-CAPS titled | `##` |
| Bare roman numeral | `IV.` | `###` |
| Standalone ALL-CAPS line | `THE END` (with filters to reject sentences) | `###` |

Multi-line titles are merged: e.g. `CHAPTER I.` followed by `HOW MANY KINDS
OF ANIMALS…` becomes one `##` with the two lines joined. Short Title-Case
lines following a heading become *italic subtitles*.

Illustration markers (`[Illustration …]`) are stripped throughout.

### 4.7 Reference generation — `write_reference()`

Writes `corpus/<genre>/<title>/reference.md` with sections:

- **Source** — Project Gutenberg ID, URL, rights
- **Author** — Name, Born, Died, Wikipedia, Gutenberg Agent ID
- **Gutenberg Published** — ebook submission date
- **Language**
- **Subjects** — bulleted list
- **Summary** — if OPDS provided one
- **Notes** — e.g. "Wikipedia page about this book: …"

All Author fields except Name are emitted conditionally — if the RDF didn't
yield a birth year for that agent, no `**Born**` line appears.

---

## 5. Batch Download

Catalog files live in [`scripts/catalogs/`](scripts/catalogs/) and use a simple
tab-separated format:

```
# Ancient & Classical
1727    The Odyssey
6130    The Iliad
228     The Aeneid
…
```

- Column 1: Gutenberg ebook ID (required)
- Column 2: Title override (optional)
- Column 3: Genre override (optional; otherwise taken from `--genre`)
- Lines starting with `#` are comments

`fetch-genre` is the interactive variant: it searches Gutenberg for the genre
keyword, presents the results, prompts per book, downloads the confirmed set,
and writes a Markdown report to `reports/fetch_genre_<genre>_<timestamp>.md`.

---

## 6. Output Layout

```
corpus/
├── <genre>/                         # ancient-classical, shakespeare, …
│   └── <Book Title>/
│       ├── <slug>.md                # full text with Markdown heading tree
│       ├── reference.md             # author provenance + Gutenberg metadata
│       └── .dockg/                  # created later by ingest (gitignored)
│           ├── graph.sqlite
│           └── lancedb/
└── authors/                         # built by build_author_index.py
    ├── index.md                     # master alphabetical table
    ├── jane_austen/
    │   └── author.md
    ├── homer/
    │   └── author.md
    └── …
```

**Slug rules** — `slugify()` lowercases, strips non-alphanumerics, collapses
runs of whitespace/hyphens into a single `_`. For both book titles and author
names. (Book titles themselves remain cased and spaced — only the filename
inside the dir is slugified.)

---

## 7. Author Index Build

[`scripts/build_author_index.py`](scripts/build_author_index.py) is a
standalone post-processor. It does not fetch anything on its own unless
`--refresh` is set.

Steps (in order):

1. **Scan** — glob `corpus/*/*/reference.md`
2. **Parse** — `parse_reference(path)` extracts title, ebook_id, genre,
   author, author_birth, author_death, author_url, author_agent_id by regex
3. **Refresh** (only with `--refresh`) — for any book whose reference.md has
   no Born/Died fields, call `_dg._fetch_rdf_author(ebook_id)` and call
   `patch_reference()` to insert the missing lines after `**Name**:`
4. **Group** — books are grouped by the `author` string (the OPDS-reversed
   display name) via a `defaultdict(list)`
5. **Write per-author pages** — `corpus/authors/<slug>/author.md` with
   `# Name`, era line (*born – died*), Wikipedia, agent ID, and a
   "Works in Corpus" table
6. **Write index** — `corpus/authors/index.md` with a master table

Rate-limiting: `--refresh` sleeps `0.3 s` between RDF fetches to be polite.

---

## 8. Refresh Workflow

When you add a book manually, the new `download_book()` call already fetches
the RDF, so new books land with full provenance in `reference.md`.

For any book whose `reference.md` predates the RDF fetch (or if a refresh has
been skipped by network failure), run:

```bash
python scripts/build_author_index.py --refresh
```

This:
1. Finds all `reference.md` files missing Born/Died
2. Re-fetches the RDF for each
3. Inserts the missing lines into `reference.md` in place
4. Regenerates `corpus/authors/` from the now-complete metadata

Safe to run repeatedly — books that already have provenance are skipped.

---

## 9. Failure Modes

| Failure | Behavior |
|---|---|
| OPDS 404 / network error | `fetch_metadata` returns `{"ebook_id": id}` — title falls back to `Book_<id>` |
| RDF 404 / network error | `_fetch_rdf_author` returns `{}` — book still downloads, just without Born/Died/Wikipedia |
| Plain-text 404 | `fetch_url` raises after 3 retries; the `download` CLI catches and reports an error per book |
| START/END markers missing | Boilerplate not stripped — full text (including Gutenberg header) is kept |
| TOC not detected | No skip — TOC ends up in the body. Cheap to ignore; the heading detector still works downstream |
| Author field missing from RDF | Book downloads normally; `author_birth`/`author_death`/`author_url` simply aren't in the reference. Happens for e.g. *The Bible* (ID 10) |
| Idempotence collision | `[=] already downloaded` — skipped unless `--force` |
| Bad title characters for filesystem | `slugify()` strips them; the book dir name itself uses the raw title |

---

## 10. Adding a Single New Book

```bash
# 1. Find it
gutenkg download search --author "Herman Melville"

# 2. Download into the right genre
gutenkg download book 2701 --genre american-literature

# 3. (optional) refresh the author index if you care about the author page
python scripts/build_author_index.py
```

The book dir `corpus/american-literature/Moby Dick/` appears immediately with
a fully-populated `reference.md` — no separate refresh needed for new
downloads.

---

## 11. Related Files

- [`scripts/download_gutenberg.py`](scripts/download_gutenberg.py) — download engine
- [`scripts/build_author_index.py`](scripts/build_author_index.py) — author-corpus builder
- [`src/gutenberg_kg/cli/cmd_download.py`](src/gutenberg_kg/cli/cmd_download.py) — `gutenkg download *` Click subcommands
- [`src/gutenberg_kg/cli/options.py`](src/gutenberg_kg/cli/options.py) — `REPO_ROOT`, `CORPUS_ROOT`, `ALL_GENRES`
- [`scripts/catalogs/`](scripts/catalogs/) — batch download catalogs
- [`README.md`](README.md) — corpus contents + ingest pipeline
- [`CHEATSHEET.md`](CHEATSHEET.md) — command quick-reference
