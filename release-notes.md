# Release Notes -- v1.33.0

> Released: 2026-11-04

### Changed

- **The Knowledge Press app is on the App Store.** Version 1.32.0 was
  accepted for iPhone, iPad and Mac on 2026-11-03. The README and docs that
  called it "in development for App Store deployment" now link to
  [its listing](https://apps.apple.com/us/app/the-knowledge-press/id6812116080).
- **doc-kg floor is 0.30.0** in `pyproject.toml`, the Dockerfile's
  `DOC_KG_VERSION` and `runpod/requirements.txt`. doc-kg 0.30.0 stores each
  chunk as the source text it spans, so a play's speaker cues keep their own
  lines ("DUNCAN." no longer runs on from "battlements."). Chunk ids and
  counts are unchanged. The corpus needs a re-ingest to pick it up.

### Added

- **`gap_after` in `gutenberg.pack`.** `export-swift` records, for each book
  chunk, the source's whitespace between it and the next chunk: spaces
  verbatim, otherwise one newline or two. It is NULL when the chunks overlap
  or a heading sits between them. Browse used to put a blank line at every
  seam, and 236,000 of those seams are really a space or a line break, so
  paragraphs and verse broke in the middle ("And choke their art." / "The
  merciless Macdonwald" is one line of *Macbeth*). The Knowledge Press reader
  reads the column when the pack has it. Filling it reads `corpus/`; an export
  without the corpus leaves it empty. Diaries carry none yet.

### Fixed

- **The worker image no longer ships bundle backups.** `.dockerignore`
  drops `bundles/*/.dockg.bak*` and `bundles/*/swift-*`, which `COPY
  bundles/` had baked in: a 4.3 GB index backup and 678 MB of old Swift packs
  grew the bundle layer from 6.2 GB to 11.6 GB.
- **The web forest's book text no longer repeats a sentence at each seam.**
  `export-web-books` joined a chapter's chunks with a blank line and kept
  both copies of the text two chunks overlap. It now uses `gap_after` and
  drops an overlap when the two chunks' text agrees. Every chapter outside
  the sacred texts is now the source verbatim, apart from 156 that skip a
  heading inside the chapter.

- **Local FLUX image generation works again.** Pillow 13 imports the
  `IntegralLike` alias in its private `PIL._typing` only on Python 3.15+, so
  mflux 0.18, which imports that module, failed on Python 3.12 and every image
  request returned 500. `docker/requirements-image.txt` now floors mflux at
  0.24.0, which no longer imports it.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
