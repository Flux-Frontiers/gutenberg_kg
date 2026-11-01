# Release Notes -- v1.31.0

> Released: 2026-11-01

A corpus and security release: the catalog IDs checked against Gutenberg's
own catalog, Tolstoy's trilogy completed (255 books), and the two critical
Dependabot alerts cleared. Rebuild the worker image to pick up the new
dependency floors.

### Added

- **`gutenkg download` refuses an ID that names a different book.** A catalog
  or `--title` override was trusted blindly, so a wrong ID downloaded the
  wrong book under the right name: `8799  The Divine Comedy: Purgatorio` in
  `world-literature.txt` would have shelved the Doré *Paradise* as Purgatorio.
  The override is now compared with the title from the ID's metadata, and an
  entry sharing fewer than half its words is refused before any text is
  fetched; a catalog run reports it and carries on. `--dry-run` runs the
  check, and `--no-title-check` (on `download book` and `download catalog`)
  skips it for a deliberate rename.

### Fixed

- **Wrong Gutenberg IDs in the catalogs and wishlist.** Checked against
  Gutenberg's catalog on 2026-10-31. Removed three catalog lines whose IDs
  name other books: `35 Medea` (*The Time Machine*), `1658 The Island of
  Doctor Moreau` (*Phaedo*) and `8799 Purgatorio` (#8800, already held, is the
  complete Cary *Divine Comedy*). The right copies were already held under
  #35451 and #159, and `159`'s title is re-cased to match its directory, which
  clears the one `gutenkg audit` error. In `docs/CORPUS_WISHLIST.md`, 12 of the
  13 unchecked IDs named the wrong book or part of it; each now carries the
  right ID or is marked as not on Gutenberg, and Byron's *Letters and Journals*
  and Mungo Park are checked off, as both are already held.
- **Tolstoy's trilogy is complete.** #2450, held as "Childhood, Boyhood,
  Youth", is *Boyhood* alone; it is renamed `Boyhood (Tolstoy)`, and
  *Childhood* (#2142) and *Youth* (#2637) are added to `russian-literature`.
  The `ancient-classical` catalog line for #47001 is retitled *De Officiis*,
  Gutenberg's own title, so the download title check accepts it.

### Changed

- **kgmodule-utils 0.29.1.** `check_pins.py --bump` moves the floor, lock,
  Dockerfile ARG and runpod pin together. Its two fixes are in the code-KG
  store's symbol-stub resolution (kg_utils #46). The DocKG and DiaryKG
  paths this repo uses are unchanged.
- **Phones and tablets as worker origins (docs).** A browser on another
  device opens the forest's dev server as `http://<your-mac>.local:5173` and
  sends that origin, which the default `GUTENKG_CORS_ORIGINS` does not
  include, so live moots fail while every other op works. The LAN checklist
  in `docs/INSTALLATION.md` gains that step, and `docs/MOOTS.md` notes it
  under the setting (#216).

### Removed

- **`scratch_embed_bench.py`**, a one-off probe of embedding throughput over
  time. Nothing referenced it.

### Security

- **Dependabot alerts cleared in `poetry.lock`.** `pillow` 12.3.0 -> 13.0.0
  (critical: FlashPix heap overflow, plus the 12.x advisories) and `certifi`
  2026.7.22 -> 2026.10.23 (critical: emSign roots with compromised
  intermediates), with `filelock` 3.32.5 -> 4.2.6, `setuptools` -> 84.2.1 and
  `virtualenv` -> 21.15.2. The `pillow` floor moves to `>=13.0.0` in the `chat`
  and `image` extras, the dev group and both image-server requirement files.
  `streamlit` moves to `>=1.66.1` with it: through 1.66.0 it capped
  `pillow<13`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
