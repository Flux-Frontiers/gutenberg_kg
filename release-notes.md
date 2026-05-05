# Release Notes — v1.1.0

> Released: 2026-05-05

## Highlights

### Click CLI is now the sole entry point

The argparse CLI layers that had grown inside `gutenberg.py` and `ia.py` (~290
lines of redundancy) are gone. Every operation — download, ingest, search,
genre management — runs through `gutenkg`. The library modules are now pure
Python APIs. Scripts that wrapped the old `main()` functions have been deleted.

### Genre registry — manage genres without touching code

A new `corpus/genres.json` file is the single source of truth for all genres.
The `gutenkg genres` command group lets you manage it from the CLI:

```bash
gutenkg genres list                              # see all registered genres
gutenkg genres add medieval-literature --source gutenberg
gutenkg genres init                              # seed from built-in defaults
```

All library modules (`gutenberg.py`, `ia.py`, `ingest.py`, `cli/options.py`)
now import from `genres.py` instead of each maintaining their own hardcoded list.

### Cleaner ingest orchestration

`ingest.py` now exports a `run_ingest()` function that centralises the entire
ingest loop — corpus setup, genre iteration, registry management, and job
summary. `gutenkg ingest` is three lines of glue code on top of it.

### New corpus content

- **Aristophanes** — three texts added to `ancient-classical`: *The Frogs*,
  *The Eleven Comedies Vol. 1* (six plays), *The Eleven Comedies Vol. 2* (five
  plays). Combined: 11,105 nodes, 151,966 edges.
- **`audel-electric` genre** — three Audel electrical engineering volumes from
  the Internet Archive (1929–1962): 22,922 nodes, 168,745 edges across 3 books.

### Test suite

228 tests across eight modules covering the full library surface:
`gutenberg.py`, `ia.py`, `ingest.py`, `genres.py`, CLI commands, options, and
version. CI runs lint + type-check + tests on every push to main.

### Ingest summary table — wider columns

`print_summary()` now uses 10-character columns for node and edge counts,
handling corpora with millions of edges without overflowing the box border.

## Fixed

- **Internet Archive search** — `mediatype=texts` moved into the Solr query
  string (`AND mediatype:texts`). IA searches now return results correctly.

## Removed

Five scripts deleted — their functionality is fully covered by the CLI:

| Removed | Replaced by |
|---|---|
| `scripts/download_gutenberg.py` | `gutenkg download` |
| `scripts/download_ia.py` | `gutenkg ia` |
| `scripts/ingest.py` | `gutenkg ingest` |
| `scripts/rebuild_lancedb.sh` | `gutenkg rebuild-lancedb` |
| `scripts/push.sh` | `gutenkg ingest --push` |

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
