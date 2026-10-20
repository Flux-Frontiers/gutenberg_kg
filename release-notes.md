# Release Notes -- v1.27.0

> Released: 2026-10-20

### Added

- `gutenkg export-web-books` (also `make export-web-books`) writes each
  book's chapters as `<slug>.json` in the knowledge_press forest's
  `web/public/books/`, from the Swift packs, with chapters built the way the
  worker's `get_chapter` builds them. The published forest on GitHub Pages
  can then read books without a worker.
- `docs/KNOWLEDGE_PRESS.md` describes the readers in the knowledge_press
  repo: the web forest, live, and the iPhone, iPad and Mac app, in
  development for App Store deployment. It lists what each needs from this
  repo. The docs index, Installation, On-device packs, the site nav and the
  README link to it.

### Changed

- Three scripts are now `gutenkg` commands, so they work from an installed
  package and share the CLI's corpus root:
  - `gutenkg stale` (was `scripts/stale_books.py`) lists books whose text is
    newer than their index; `make stale-books` and `make refresh-text` call it.
  - `gutenkg export-web-catalog` (was `scripts/export_web_catalog.py`) writes
    the web forest's catalog, next to `gutenkg export-swift`;
    `make export-web-catalog` calls it.
  - `gutenkg audit --sections` (was `scripts/check_sections.py`) adds the
    oversized-section report to the audit, with `--baseline` and `--csv-out`.
    It is advisory and does not change the audit's exit code.
- **KG pin set moved to kg-rag 0.17.1, kgmodule-utils 0.27.0 and doc-kg
  0.28.0** (#186), by `scripts/check_pins.py --bump` across the pyproject
  floors, `poetry.lock`, `docker/Dockerfile` and `runpod/requirements.txt`.
  None of the three changes the index, so a bundle built on the old set stays
  valid. The PDF fix below moves it again, to 0.27.1 and 0.28.1.
- **Dependencies refreshed to clear 22 Dependabot alerts**: pyjwt 2.15.1,
  urllib3 2.8.0, mcp 1.30.0 and virtualenv 21.14.11 (dev), all transitive.

### Removed

- The SIMILAR_TO cap study's scripts: `setup_similar_to_analysis.py`,
  `run_similar_to_cap_sweep.py`, `run_retrieval_cap_ab.py`,
  `summarize_retrieval_ab.py`, `evaluate_similar_to_value.py` and
  `build_gold_from_retrieval.py`. The cap-8 decision is settled; their
  results stay in `analysis/`.
- `scripts/synth_replay.py` and `scripts/make_tokenizer_fixture.py` moved to
  the knowledge_press repo, the app they serve.
- `scripts/build_corpus_by_genre.py` and `scripts/benchmark_embedders.py`,
  which need LanceDB; the bundle has been sqlite-vec since doc-kg 0.18.0.
- `scripts/catalog.txt`, the pre-genre book list, whose usage line named a
  script that no longer exists, and `scripts/catalogs/science-fiction-additions.txt`,
  whose four IDs are all in the genre catalogs.
- `scripts/make_app_icon.py`, which drew the app's old "G badge" icon into
  `app/`. The app moved to knowledge_press, whose `make icons` renders the
  press-seal icon from SVG.

### Fixed

- **PDF ingest on a fresh install, and the image pins moved with it.**
  kgmodule-utils 0.27.0's `[pdf]` resolved to the empty pymupdf4llm 2.0
  placeholder, leaving no PDF code (kgrag_priv sweep item 86). The KG pin
  set moves to kgmodule-utils 0.27.1 and doc-kg 0.28.1 in the pyproject
  floors, `docker/Dockerfile` ARGs and `runpod/requirements.txt`, via
  `scripts/check_pins.py --bump`; the lock takes pymupdf 2.0.

- Chapter numbers printed as a bare numeral with no period ("I", "II",
  "IV") now become headings. Only three-character numerals such as III and
  XII did before, by way of the ALL-CAPS rule, so chapters like I, II, IV,
  V, X, XL and L merged into the chapter before them. A lone numeral counts
  only as part of a sequence that counts up and may restart at I, so stray
  capitals in plays and dialogues are left alone. Checked against the raw
  text of all 245 Gutenberg books: 25 gain headings (Cellini, My Antonia,
  Tess, The Possessed, the Upanishads and others), no words change in any
  book, and the other 220 convert identically. The 25 books need
  re-downloading and a full `gutenkg build-corpus`.

- The README no longer says the published forest cannot open a book; it
  reads static chapter files and needs no worker.

- **Every corpus-count surface is synced, and a test keeps it that way**
  (#179). At 1.26.0 six files still said 21 genres after the corpus had 20:
  `sync_corpus_docs.py` missed the README's "**N texts in G genres**" wording
  and never touched `docs/index.md`, `docs/CHAT_UI.md`,
  `docs/ingestion-pipeline.md` or the `CITATION.cff` abstract, while
  reporting success. One pattern list now covers README and every surface
  file, and `tests/test_sync_corpus_docs.py` fails if any "N genres" on disk
  sits outside a pattern. `regenerate_corpus_doc.py` ends `docs/CORPUS.md`
  with a newline.

- **Audel volume dates and rights basis** (#185). Vols 8 and 9 now carry
  the 1930 and 1931 dates on their scanned copyright pages instead of the
  Internet Archive's 1929, and every volume's `reference.md` states its US
  public-domain basis (published 1929-1931 with notice, no renewal found in
  the 1956-1970 renewal records). `gutenkg stale` flags all eight volumes;
  they re-ingest at the next corpus rebuild.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
