# gutenkg Command Reference

Full flag reference for the `gutenkg` CLI (v1.2.0). All commands run from the repo root.

---

## Table of Contents

1. [download book](#download-book)
2. [download catalog](#download-catalog)
3. [download search](#download-search)
4. [download fetch-genre](#download-fetch-genre)
5. [download survey](#download-survey)
6. [ingest](#ingest)
7. [ia download](#ia-download)
8. [ia catalog](#ia-catalog)
9. [ia search](#ia-search)
10. [ia survey](#ia-survey)
11. [genres](#genres)
12. [list-genres](#list-genres)
13. [authors](#authors)
14. [rebuild-indices](#rebuild-indices)
15. [snapshot](#snapshot)
16. [status](#status)
17. [viz3d](#viz3d)
18. [viz-timeline](#viz-timeline)
19. [Data Sources](#data-sources-download-pipeline)
20. [text_to_markdown Heading Patterns](#text_to_markdown-heading-patterns)
21. [Failure Modes](#failure-modes)

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

gutenkg ingest --registry /path/to/registry  # override KGRAG registry path
```

Reports auto-saved to `reports/ingest_YYYY-MM-DD_HHMMSS.md`.

---

## ia download

Download a single item by its Internet Archive identifier.

```bash
gutenkg ia download <identifier> --genre <genre>
gutenkg ia download audelselectriciansguide01ande --genre audel-electric
gutenkg ia download <id> --title "Override Title" --genre audel-electric
gutenkg ia download <id> --genre audel-electric --force
gutenkg ia download <id> --genre audel-electric --dry-run
```

**Idempotent** — skips if already present unless `--force`.

---

## ia catalog

Batch download from an IA catalog file.

```bash
gutenkg ia catalog scripts/catalogs/audel-electric.txt
gutenkg ia catalog scripts/catalogs/audel-electric.txt --genre audel-electric
gutenkg ia catalog scripts/catalogs/audel-electric.txt --force
gutenkg ia catalog scripts/catalogs/audel-electric.txt --dry-run
```

**IA Catalog format:**
```
# comment
<ia_identifier>[\t<genre>]
audelselectriciansguide01ande   audel-electric
```

---

## ia search

Search the Internet Archive catalog.

```bash
gutenkg ia search "audel electricians"
gutenkg ia search "tesla coil" --max-results 10
```

Default `--max-results` is 25.

---

## ia survey

Show download/ingest status for Internet Archive–sourced genres.

```bash
gutenkg ia survey                     # all IA genres
gutenkg ia survey --genre audel-electric
```

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

## list-genres

Print all known Gutenberg genres (reads from registry, no options).

```bash
gutenkg list-genres
```

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
gutenkg rebuild-indices --force-build        # rebuild even if .dockg exists
```

Use this immediately after `git clone` — `.dockg/` directories are gitignored.

---

## snapshot

Capture and review point-in-time corpus metrics.

```bash
gutenkg snapshot save            # capture current corpus metrics → corpus/.snapshots/snapshot-<ts>.json
gutenkg snapshot list            # list all saved snapshots
gutenkg snapshot show            # show full JSON for the most recent snapshot
gutenkg snapshot diff            # compare second-to-last vs last snapshot
```

Snapshots track: total books, authors, genres, nodes, edges, and per-genre breakdowns.
Run `snapshot save` periodically (after each ingest session) to build history for `viz-timeline`.

---

## status

Show live corpus statistics from the KGRAG registry. Reads per-book SQLite databases directly — no rebuild required. Safe for CI.

```bash
gutenkg status                             # Rich table output
gutenkg status --json                      # machine-readable JSON
gutenkg status --update-readme             # also patch badge URLs in README.md
gutenkg status --registry /path/to/reg    # override KGRAG registry path
```

---

## viz3d

Launch the 3-D Knowledge Tree Forest visualiser. Each ingested book renders as a tree (trunk = document, branches = sections, leaves = chunks), grouped by genre into groves.

```bash
gutenkg viz3d                              # defaults: corpus=corpus, 1500×950
gutenkg viz3d --corpus /path/to/corpus
gutenkg viz3d --width 1920 --height 1080
```

Only ingested books (with `.dockg/graph.sqlite`) are shown. Run `gutenkg ingest` first.
Navigate with mouse; right-click a node to read its text.

---

## viz-timeline

Visualise corpus growth across saved snapshots using an interactive Plotly chart.

```bash
gutenkg viz-timeline                       # 2-D four-subplot grid (default)
gutenkg viz-timeline --type 3d             # normalised multi-metric 3-D scatter
gutenkg viz-timeline --snapshots /path/to/.snapshots
```

Plots: total books, authors, nodes, edges over time.
Requires at least one saved snapshot (`gutenkg snapshot save`).

---

## Data Sources (download pipeline)

Each book pulls from up to three Gutenberg endpoints:

| Endpoint | URL | Used for |
|---|---|---|
| OPDS feed | `https://www.gutenberg.org/ebooks/{id}.opds` | Title, author, subjects, language, rights |
| RDF catalog | `https://www.gutenberg.org/cache/epub/{id}/pg{id}.rdf` | Author birth/death, Wikipedia URL, agent ID |
| Plain text | `https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt` | The book text (UTF-8 with BOM) |

IA downloads pull from `https://archive.org/download/<identifier>/`.

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
| IA 403 / unavailable | Error reported; item not written |
| snapshot diff with < 2 saves | Error: "need at least 2 snapshots" |
| viz-timeline with no snapshots | Error: no snapshot files found in `.snapshots/` |
