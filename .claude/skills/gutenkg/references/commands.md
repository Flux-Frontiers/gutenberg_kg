# gutenkg Command Reference

Full flag reference for the `gutenkg` CLI. All commands run from the repo root.

---

## Table of Contents

1. [download book](#download-book)
2. [download catalog](#download-catalog)
3. [download search](#download-search)
4. [download fetch-genre](#download-fetch-genre)
5. [download survey](#download-survey)
6. [ingest](#ingest)
7. [genres](#genres)
8. [authors](#authors)
9. [rebuild-indices](#rebuild-indices)

---

## download book

Download a single book by its Gutenberg ebook ID.

```bash
gutenkg download book <id> --genre <genre>
gutenkg download book <id> --genre <genre> --dry-run    # preview only
gutenkg download book <id> --genre <genre> --force      # re-download if exists
```

**Idempotent** — skips if `corpus/<genre>/<title>/<slug>.md` already exists, unless `--force`.

---

## download catalog

Batch download from a catalog file.

```bash
gutenkg download catalog scripts/catalogs/philosophy.txt --genre philosophy
gutenkg download catalog scripts/catalogs/philosophy.txt --genre philosophy --dry-run
gutenkg download catalog scripts/catalogs/philosophy.txt --genre philosophy --force
```

**Catalog format:**
```
# comment
<gutenberg_id>[\t<title_override>[\t<genre_override>]]
600     Notes from Underground
52263   Twilight of the Idols
```

Each book is idempotent — already-present books are skipped unless `--force`.

---

## download search

Search the Project Gutenberg catalog. **Slow** — prefer catalogs for known IDs.

```bash
gutenkg download search "science fiction"
gutenkg download search --author "Mary Shelley"
gutenkg download search --title "Frankenstein"
gutenkg download search --subject "dystopia" --max-results 10
gutenkg download search --author "Seneca"
```

---

## download fetch-genre

Interactive search → confirm → download for an entire genre.

```bash
gutenkg download fetch-genre science-fiction          # interactive (Enter=yes, n=skip, q=quit)
gutenkg download fetch-genre science-fiction --query "dystopia"  # custom query
gutenkg download fetch-genre science-fiction --yes    # download all without prompts
gutenkg download fetch-genre science-fiction --dry-run
```

Reports saved to `reports/fetch_genre_<genre>_<timestamp>.md`.

---

## download survey

Show download and ingest status across the corpus.

```bash
gutenkg download survey                    # all genres
gutenkg download survey --genre philosophy
```

Output columns: `md=✓/✗  ref=✓/✗  kg=✓/✗`
(`md` = text file, `ref` = reference.md, `kg` = .dockg/ index)

---

## ingest

Build DocKG indices and register with KGRAG. Skips books whose `.dockg/` already exists.

```bash
gutenkg ingest                              # all genres
gutenkg ingest --genre philosophy           # single genre
gutenkg ingest --genre philosophy --genre shakespeare  # multiple genres

gutenkg ingest --force-build                # wipe existing .dockg/ and rebuild
gutenkg ingest --force-build --genre philosophy

gutenkg ingest --force-register             # re-register with KGRAG, skip rebuild
gutenkg ingest --force-register --genre philosophy

gutenkg ingest --push                       # auto-commit per genre after ingest
gutenkg ingest --force-build --push

gutenkg ingest --dry-run                    # preview only
```

Reports auto-saved to `reports/ingest_YYYY-MM-DD_HHMMSS.md`.

---

## genres

Manage the `corpus/genres.json` registry.

```bash
gutenkg genres init                                       # seed genres.json (first time)
gutenkg genres list                                       # show all registered genres
gutenkg genres add medieval-literature --source gutenberg # add Gutenberg genre
gutenkg genres add my-ia-collection --source ia           # add Internet Archive genre
```

`genres add` auto-creates `genres.json` if it doesn't exist.
`--source` values: `gutenberg` | `ia`

---

## authors

Build or refresh `corpus/authors/` from `reference.md` files in the corpus.

```bash
gutenkg authors                  # rebuild from existing reference.md files
gutenkg authors --refresh        # also re-fetch RDF for books missing Born/Died
gutenkg authors --dry-run
gutenkg authors --refresh --dry-run
```

`--refresh` sleeps 0.3 s between RDF fetches to be polite to Gutenberg.
Use `--refresh` only for books that predate the RDF fetch or had a network failure.
New downloads already land with full provenance — no refresh needed for fresh downloads.

---

## rebuild-indices

Rebuild DocKG knowledge graph indices after cloning. Does not re-download text.

```bash
gutenkg rebuild-indices                      # all genres
gutenkg rebuild-indices --genre philosophy
gutenkg rebuild-indices --genre philosophy --genre shakespeare
```

Use this immediately after `git clone` — `.dockg/` directories are gitignored.

---

## Data Sources (download pipeline)

Each book pull from up to three Gutenberg endpoints:

| Endpoint | URL | Used for |
|---|---|---|
| OPDS feed | `https://www.gutenberg.org/ebooks/{id}.opds` | Title, author, subjects, language, rights |
| RDF catalog | `https://www.gutenberg.org/cache/epub/{id}/pg{id}.rdf` | Author birth/death, Wikipedia URL, agent ID |
| Plain text | `https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt` | The book text (UTF-8 with BOM) |

---

## text_to_markdown Heading Patterns

The download pipeline auto-detects structure using these patterns (priority order):

| Pattern | Example | Heading level |
|---|---|---|
| `THE FIRST/SECOND/… BOOK` | `THE FIRST BOOK` | `##` |
| `VOLUME/BOOK/PART` + numeral | `VOLUME II`, `PART III` | `##` |
| `ACT` + numeral | `ACT III` | `##` |
| `CHAPTER` + numeral | `CHAPTER XIV.`, `Chapter 3` | `##` |
| `SCENE` + numeral | `SCENE II` | `###` |
| `LETTER` + numeral | `Letter 4` | `##` |
| Bible books | `The First Book of Moses: Called Genesis` | `##` |
| `STAVE` + numeral | `STAVE I` | `##` |
| Roman + ALL-CAPS title | `I. A SCANDAL IN BOHEMIA` | `##` |
| Bare roman numeral | `IV.` | `###` |
| Standalone ALL-CAPS line | (filtered to reject sentences) | `###` |

Multi-line titles are merged. Short Title-Case lines following a heading become *italic subtitles*.
Illustration markers `[Illustration …]` are stripped.

---

## Failure Modes

| Failure | Behavior |
|---|---|
| OPDS 404 / network error | Title falls back to `Book_<id>` |
| RDF 404 | Book downloads normally; no Born/Died/Wikipedia in reference.md |
| Plain-text 404 | Error reported after 3 retries; book not written |
| START/END markers missing | Full text kept (including PG header) |
| TOC not detected | TOC stays in body — harmless |
| Idempotence collision | `[=] already downloaded` — skipped unless `--force` |
