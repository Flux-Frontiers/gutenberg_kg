# Release Notes -- v1.40.1

> Released: 2026-11-19

### Changed

- **The logo is redrawn in Art Techno.** The brain is replaced by an open
  book drawn as four traces notched at the gutter, with a die in the gutter
  and a graph fan rising from it. `scripts/build_logo.py` draws the square
  mark, a 64 px icon and a banner as SVG and writes every PNG size under
  `assets/` and `docs/assets/`; the 64 px and smaller sizes, the small badges
  and the docs logo and favicon now come from the icon. The README header
  shows the banner.

- **The banner lettering is larger.** The name is set as large as the
  space beside the mark allows, the part line at the same width, and the pair
  is centered on the banner's height; `scripts/build_logo.py` draws it this
  way and the banner is redrawn.

- **`assets/brand-system/` describes the Art Techno mark.** A new
  `README.md` covers the mark, its files and sizes, how to use it, the
  palette and how to rebuild it. The August 2026 brand board for the brain
  logo moves to `assets/brand-system/archive/2026-08-brain/`, unchanged.

### Removed

- **The RunPod serverless pipeline.** It was never deployed, and since 1.40.0
  the worker no longer uses RunPod's server. Gone: `runpod/` (its Dockerfile,
  handler, build and index-push scripts), `.runpod/` and `docs/RUNPOD.md`.
  `scripts/check_pins.py` now compares three files instead of four, and the
  tests, docs, CI comments and skills that named the RunPod worker are
  updated. The `/runsync` request and reply format is unchanged.
- **`scripts/process_logo.py`**, the raster pipeline for the old brain
  logo. `scripts/build_logo.py` draws the Art Techno logo and writes every
  size, so nothing uses it, and it would overwrite the new files.

### Fixed

- **Four books had chapters as plain text.** A chapter's numeral and title
  sat on plain lines instead of a heading, so each such chapter ran into the
  section before it. *At the Earth's Core* (9 of 15 chapters, which left 9
  story sections instead of 17) and *The Great God Pan* (5 of 8) now have a
  `###` heading per chapter. In *The Food of the Gods* none of the 12
  chapters ("CHAPTER THE FIRST.") were headings; they are now `###` under
  their `##` books, with each chapter's numbered parts moved down to `####`,
  where before all 62 parts sat side by side and their numbers restarted
  without a chapter to tell them apart. In *Second Treatise of Government*
  none of the 19 chapters were headings, so the whole treatise was one
  650-chunk section; each chapter is now a `###` heading. Corpus scans for
  these patterns found no other story chapters; the remaining hits are
  contents lists, an appendix list in *The Travels of Marco Polo* and
  front-matter essays in *Fathers and Sons*, left as they are. The four books
  are re-ingested and the corpus bundle is rebuilt with them.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
