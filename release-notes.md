# Release Notes -- v1.20.0

> Released: 2026-09-10

### Changed

- **`gutenkg snapshot save` takes VERSION positionally, and `--key` is gone.**
  Every other KG module in the fleet declares the same argument -- verified in
  `doc_kg`, `pycode_kg`, `memory_kg`, `Metabo_kg`, `tscode_kg`, `ftree_kg` and
  `genealogy_kg` -- and the shared release workflow calls
  `<cli> snapshot save <version> --subject ...` on that basis. This repo took
  `--key` instead, so the documented release step failed here and nowhere else
  with "Got unexpected extra argument". It was inconsistent internally too:
  `snapshot show KEY` and `snapshot diff KEY_A KEY_B` were already positional.

  `--key` shipped in 1.19.0 and is removed rather than deprecated: it was a day
  old, and carrying two spellings of the fleet's own contract is the drift being
  fixed. Anything scripted against it becomes
  `gutenkg snapshot save <version>`. Omitting VERSION still keys on a UTC
  timestamp, which is the right default for a corpus -- the books change when
  something is ingested, not when the repo is tagged. A conformance test asserts
  the usage line so the next drift fails a test rather than a release.

- **Corpus snapshots are tracked in git.** They were excluded by a bare
  `corpus/.snapshots/` rule, which is exactly the pattern every sibling repo's
  `.gitignore` warns against beside its KG-artifact rules ("snapshots/ is
  TRACKED and must never be ignored"). A snapshot exists to be a permanent
  record of the corpus at a tag, which an ignored directory cannot be; this was
  the only repo in the fleet tracking none. The four pre-0.19.0 tree-hash-keyed
  captures stay out by pattern -- their keys name trees that were never
  committed -- and remain on disk.

  The 1.18.0 and 1.19.0 snapshots also recorded `subject: repo:gutenberg-kg`
  while holding corpus metrics. `gutenkg snapshot save` measures the corpus, not
  this package's source, so both are corrected to `corpus:gutenberg`.

### Fixed

- **DiaryKG connections were leaked, one per diary per corpus build.**
  `build_diary_index()` constructed a `DiaryKG` and never released it, and
  `DiaryKG` holds a lazily built `DocKG` and its SQLite connection. diary-kg
  added `close()` in 0.98.0 naming this call site as the reason; the floor here
  has required that release since 2026-09-06, so only the wiring was missing.

  Using it as a context manager also fixes an ordering wrinkle: `_clean_chunk_texts()`
  reopens `graph.sqlite` to rewrite chunk text, and did so while the DiaryKG's
  own connection was still live. It now runs after the store closes. Covered on
  both paths -- a failed rebuild returns a result rather than raising, so
  without this a broken diary's connection leaked for the rest of the run.

- **`site/` is excluded from the repo-root DocKG corpus.** `make docs` renders
  mkdocs into a gitignored `site/`, so the corpus differed between machines
  depending on who last built the docs. Nothing is double-indexed today, since
  `docs/` holds only `.md` and `.png` and mkdocs renders `.md` to `.html` -- but
  mkdocs copies anything it does not render straight through, so the first
  `.txt` or `.pdf` added under `docs/` would be indexed at both `docs/x.pdf` and
  `site/x.pdf`. A duplicate document double-counts in every ranking and returns
  the same passage twice. Same reasoning that already excludes `dist`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
