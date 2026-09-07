# Release Notes — v1.18.1

> Released: 2026-09-06

### Fixed

- **`regenerate_corpus_doc.py`'s `GENRE_ORDER` silently dropped a whole
  genre.** The list is hand-maintained rather than derived from `corpus/`,
  and `curiosities` was never added to it, so `_collect_rows()` walked past
  its directory entirely: `docs/CORPUS.md` reported "252 books across 20
  genres" when `gutenkg audit` confirmed 253 books across 21, all clean. Both
  `GENRE_ORDER` and `GENRE_LABELS` now include it, and a new
  `tests/test_regenerate_corpus_doc.py` asserts every genre directory on disk
  has an entry in `GENRE_ORDER` — confirmed to fail without the fix and pass
  with it, so a future new genre can't vanish from the catalog the same way.

- **Stale corpus counts had spread across five docs and the citation
  metadata.** `README.md`, `docs/index.md`, `docs/CHAT_UI.md`,
  `docs/PARTNERS.md`, `docs/ingestion-pipeline.md` and `CITATION.cff` all
  quoted book/genre totals from before the corpus reached its current 253
  books across 21 genres — some from as far back as 241/20, none caught by
  the v1.18.0 release, which corrected the README/`CITATION.cff` badge
  numbers but not the prose scattered through the rest of the docs. Every
  figure above was cross-checked against `gutenkg audit` (253 books, 0
  warnings, 0 errors), `gutenkg status`, and a plain count of `reference.md`
  files on disk before being corrected, rather than assumed.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
