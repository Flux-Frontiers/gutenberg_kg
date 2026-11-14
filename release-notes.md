# Release Notes -- v1.36.0

> Released: 2026-11-14

### Added

- **Each book in the forest catalog carries its author's voice.**
  `gutenkg export-web-catalog` reads `corpus/authors/voices.json` and writes
  `voice: { gender, accent }` on every book whose author is known, for the
  Knowledge Press forest's read-aloud. 252 of the 265 books have one; the
  rest are "Various" and the Audel handbooks.
- **Each book in `core.pack` carries its author's voice too.**
  `gutenkg export-swift` writes `gender` and `accent` columns on the books
  table from the same `voices.json`, so the app's reader can read a book in
  a voice that matches its author. Both are NULL for an unknown author; an
  app that does not read them is unaffected.
- **Four more authors in the voice table**: Charles Lamb, J. M. Synge,
  Marcus Tullius Cicero and Mary Wortley Montagu, whose author pages were
  newer than the table. Synge's accent is set by hand to `en-GB`: Wikidata
  lists no citizenship for him.

### Changed

- **`voice_for` reads a joint work's authors one by one.** "Alexander
  Hamilton, John Jay, and James Madison" now takes Hamilton's voice, where it
  had none; the same for Dumas and Maquet, the Grimms, and Polo and
  Rusticiano. Moot packs get the same voices.

### Fixed

- **Stale corpus counts in the docs.** The README forest section said 253
  trees and `docs/ingestion-pipeline.md` described a 253-book bundle; both
  now match the 265-book corpus and the current consolidated bundle
  (745,627 nodes). `scripts/sync_corpus_docs.py` now keeps the forest tree
  count and the bundle catalog count in sync, and the `gutenberg-all` row
  in `docs/BUNDLES.md` carries the current book, node and size figures.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
