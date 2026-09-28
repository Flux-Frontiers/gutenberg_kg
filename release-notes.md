# Release Notes -- v1.26.0

> Released: 2026-09-28

### Added

- Diaries grow as timelines in `viz3d` and `quilt`. The trunk runs up to the
  diary's last year, and each calendar year forks from it as a limb, turning
  half the golden angle from the one before, so the years climb the trunk in
  a spiral and a year the diarist skipped leaves bare trunk. Each entry hangs
  on its year's limb at its fraction of the year; before, all of a period's
  entries were clustered at the limb tip, about 900 of them for each Pepys
  year. Limbs are sized by the square root of their share of entries, so a
  heavy year no longer wraps the trunk. A one-year diary (the Hebrides
  journal) spaces its parts in file order.
- `gutenkg quilt --still` renders one square PNG of a book's tree, the
  quilt's center view, instead of a full light-field quilt. `--size` sets the
  edge in pixels; `--plain`, `--season` and `--zoom` apply; `--orbit` and
  `--cast` are refused.
- The web catalog export writes two new fields. `book` is the corpus folder
  name the worker looks books up by; for 9 of 253 books it differs from the
  title (The Sea-Wolf is in `The Sea-Wolf (London)`), so the forest could not
  open them. `periods`, on diary books, carries each year's chunk counts in 53
  slices along its limb, so the web forest grows the same diary limbs as
  `viz3d` without the graph.
- `make stale-books` lists books whose text (`*.md` or `reference.md`) is
  newer than their index, and the bundle when a book's index is newer than
  it. It prints the `refresh-text` command for the stale genres and exits 1
  when anything is stale.
- `make refresh-text GENRE="..."` carries changed book text to every local
  surface: it force-rebuilds those genres' indices, runs a full `gutenkg
  build-corpus`, checks with `stale_books.py`, then exports the Swift packs,
  builds the image under every installed runtime and exports the web forest
  catalog. `build-corpus --update` is not enough after a text change: it
  matches on node ids, so an edited book keeps its old vectors. Pushing the
  image to Docker Hub stays a separate step. The author fixes below rewrote
  about 50 `reference.md` files and the OCR fix rewrote the Audel text; this
  release's bundle, packs and image were refreshed that way across 16 genres.

### Fixed

- The worker can browse diaries. `get_chapters` and `get_chapter` looked
  every book up in the consolidated DocKG, which does not hold the four
  diaries, so the forest reader and the Browse page answered "book not found"
  for Pepys, both Evelyn volumes and the Hebrides journal. For diaries they
  now read the book's DiaryKG: one chapter per dated entry, in the same
  scheme as the app's `PassagePack.diaryEntries`.
- Internet Archive text is cleaned properly, and the eight Audel volumes are
  regenerated with it. Hyphenated words were never rejoined, because the
  Archive's OCR ends every line with a space; about 6,800 now are. Running
  titles printed with a page number ("304 Dynamo and Motor Experiments") and
  page numbers such as "4.047" are removed. Drawings and rotated captions
  that OCR read as characters, about 34,000 lines across the set, are removed
  by a new debris filter; lines of this kind fell from 22 to 4 percent, at a
  cost of under 1 percent of real words, mostly labels inside drawings. Every
  IA book's `reference.md` now ends with a Text notes section giving the OCR
  engine, a count for each cleanup step, and what was not repaired. The
  Audel scans are cropped into the binding, so letters are missing at line
  starts and ends; that cannot be fixed from these scans, and
  `docs/IA_OCR_TEXT.md` records the measurements and the other scans that
  were considered. Carry the new text downstream with `make refresh-text
  GENRE=audel-electric` (see Added).
- Books with more than one author are credited to all of them, primary
  author first. Only the first author in Gutenberg's OPDS feed was kept, and
  the feed lists co-authors in reverse, so The Count of Monte Cristo and The
  Three Musketeers were credited to Auguste Maquet instead of Alexandre Dumas,
  The Travels of Marco Polo to Rusticiano da Pisa, Grimms' Fairy Tales to
  Wilhelm Grimm alone, and The Federalist Papers to James Madison alone.
  Authors now come from the RDF record's creators, which leave out
  translators and editors. Born/Died/Wikipedia always describe the first
  author; Monte Cristo's had been Dumas's under Maquet's name.
- Author names read the way readers know them. "Tolstoy, Leo, graf" was
  displayed as "Leo, graf Tolstoy", "Marcus Aurelius, Emperor of Rome" as
  "Emperor of Rome Marcus Aurelius", and "Wells, H. G. (Herbert George)" as
  "H. G. (Herbert George) Wells"; they are now Leo Tolstoy, Marcus Aurelius
  and H. G. Wells. Twenty authors across 39 books changed.
- Internet Archive books have their author. Their `reference.md` records it
  as a Publication Author line, which the parser never read, so the eight
  Audel manuals showed no author (or "Unknown"); they are by Frank D. Graham
  and Theo Audel & Company.
- A book whose Gutenberg record names no author is credited to "Various"
  instead of nobody, so it can be found by author. That covers the five
  sacred texts now in the corpus and any future download like them.
- The Wikipedia link is the English article when Gutenberg has one. Aristotle,
  Dante, Euripides, Hesse, Sun Tzu, Wilde and Zola linked to Greek, Italian,
  German, Chinese or French Wikipedia.
- `gutenkg authors --refresh` works again. It imported a script that no longer
  exists. It now re-fetches the RDF for every book and rewrites each
  `reference.md` Author section from it (leaving the rest of the file alone),
  which is how the corpus picked up the fixes above. `gutenkg authors` lists a
  co-written book under each author and removes pages for authors no longer in
  the corpus: 31 stale pages went.
- The King James Bible (#10) converts to all 66 books. Fifteen books the
  edition titles with a bare name (Ezra, The Proverbs, Ecclesiastes and the
  twelve minor prophets) were not recognized as headings, so their text was
  folded into 2 Chronicles, Psalms and Daniel. 3 John was folded into 2 John
  the same way. The "Otherwise Called:" subtitles of Samuel and Kings no
  longer open a second, mislabeled section, so 1 Samuel's text is no longer
  filed under "The First Book of the Kings". Bare titles count only when at
  least five stand alone in one book, so Hobbes's marginal note "The
  Proverbs" in Leviathan stays body text. The corrected text ships in this
  release; rebuild an existing local index with `make refresh-text
  GENRE=sacred-texts`.
- `gutenkg build-corpus` no longer crashes with `FileNotFoundError` when a
  registered genre (such as `curiosities`) has no directory under `corpus/`.
- An exact-phrase match now wins a reciprocal-rank-fusion tie against the
  dense channel's hit of the same rank. "pillar of salt" has one BM25 hit,
  Genesis 19:26, which tied Ruskin's "pillar of sand" (the dense top hit) at
  1/60 and lost on insertion order. The worker and `export_swift.rrf_fuse`
  change together; the app's Swift `LocalRetrieval.fuse` changes in
  knowledge_press, and `golden.json` needs a fresh `gutenkg export-swift`.

### Removed

- `scripts/resync_catalog_fix.sh`, a one-off resync for an old branch. It
  rebuilt the bundle with `build-corpus --update`, which keeps stale vectors
  for books whose text changed.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
