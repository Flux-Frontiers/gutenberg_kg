---
name: sync-corpus-docs
description: >
  Keep the public corpus-count surfaces in sync with the live corpus. Use whenever
  the README badges (corpus/nodes/edges), the "Corpus at a Glance" table, the intro
  prose, the partnership blurb, the BibTeX citation, or docs/CORPUS.md may be stale —
  e.g. after adding/removing/re-ingesting books, adding a new genre, or before a
  release. Also use to AUDIT for drift ("are our badges right?", "is CORPUS.md current?").
  Repo: /Users/egs/repos/gutenberg_kg/.
---

# Sync Corpus Docs

One command keeps every corpus-count surface aligned with the live corpus, so the
badges and book lists can never silently drift again.

## The single source of truth

- **Numbers** (books / nodes / edges / genre counts) come from the **KGRAG registry**
  via `corpus_status()` — the same data `gutenkg status` prints. No rebuild needed;
  it reads the per-book SQLite graphs directly.
- **Per-genre book lists** in `docs/CORPUS.md` come from the `corpus/` directory tree.
- **Genre ordering** for both the README table and CORPUS.md comes from
  `scripts/regenerate_corpus_doc.py:GENRE_ORDER` — one canonical order for both docs.

## Commands

```bash
# Audit — report drift, exit 1 if anything is stale (good before a release / in CI)
poetry run python scripts/sync_corpus_docs.py --check

# Fix — rewrite every stale surface, then print a summary
poetry run python scripts/sync_corpus_docs.py
```

That's the whole workflow. Run `--check` first if you just want to know; run without
it to apply. Both are idempotent — a clean corpus produces no diff (CORPUS.md's
provenance timestamp is ignored when detecting drift).

## What it updates

`scripts/sync_corpus_docs.py` rewrites, from live data:

| Surface | Location |
|---|---|
| corpus / nodes / edges badges | `README.md` (top) |
| "Corpus at a Glance" table | `README.md`, between `<!-- BEGIN corpus-table -->` markers |
| intro prose "N texts across G genres — X nodes, Y edges" | `README.md` |
| "query N books" line | `README.md` |
| "corpus stands at N works" blurb | `docs/PARTNERS.md` |
| BibTeX citation note | `README.md` |
| full per-genre book list | `docs/CORPUS.md` (delegates to `regenerate_corpus_doc.py`) |

## What it deliberately does NOT touch

- **The version badge** (`version-1.8.0`) and the CITATION version — those track the
  release version and are owned by the `/release` skill, not the corpus.
- **Per-genre labels / ordering** — to change these, edit `GENRE_ORDER` /
  `GENRE_LABELS` in `scripts/regenerate_corpus_doc.py`, then re-run the sync.

## Adding a new genre

When a new genre appears in the corpus, add its slug to **both** `GENRE_ORDER` and
`GENRE_LABELS` in `scripts/regenerate_corpus_doc.py` (this is the fix that was missing
when the Horror genre silently dropped out of the docs). Then run the sync — the new
genre flows into the table and CORPUS.md automatically.

## When to run it

- After `gutenkg ingest` / adding / removing / re-ingesting books
- After adding a new genre
- Before cutting a release (pair with `--check` in your pre-release checklist)
- Any time someone asks "are the badges / corpus counts right?"
