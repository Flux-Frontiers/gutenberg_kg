# Monolithic sections: why Franklin is one 885-chunk block, and the fix

Written 2026-09-03 on branch `fix/monolithic-sections`. Plan only; nothing
below is implemented yet.

## The symptom

Browse -> biography -> *Autobiography of Benjamin Franklin* shows three
sections. The third is the entire book: 885 chunks, 375,758 characters, one
scrollbar. The first is a publisher's imprint line masquerading as a chapter.

| section (what Browse lists) | chunks | chars |
|---|---:|---:|
| `CHARLES W ELIOT LLD P F COLLIER & SON COMPANY NEW YORK` | 1 | 175 |
| `INTRODUCTORY NOTE` | 12 | 4,766 |
| `BENJAMIN FRANKLIN HIS AUTOBIOGRAPHY` | 885 | 375,758 |

This is not a display bug and not a diary bug (Franklin is in `biography/`,
not `diaries/`, and was never diary-processed). It is how the book is
indexed, and it comes straight from the Markdown the downloader wrote.

## It is systemic, not Franklin

Measured against `bundles/gutenberg-all/swift/gutenberg.pack` (2026-09-03
export). Full table: `analysis/monolithic_sections_20260903.csv`, one row per
book.

**15 books have more than 90% of their text in a single section that is
itself over 100K characters:**

```
100.0%   1 sec    598,071 ch  [world-literature]  One Thousand and One Nights (Lane)
100.0%   1 sec    458,337 ch  [german-literature] The Trial (Kafka)
100.0%   1 sec    179,568 ch  [philosophy]        The Symposium (Plato)
100.0%   1 sec    127,330 ch  [natural-history]   Autobiography of Charles Darwin
100.0%   1 sec    102,239 ch  [horror]            The Dunwich Horror
 99.4%   2 secs   180,521 ch  [drama]             Hedda Gabler
 99.2%   2 secs   222,389 ch  [natural-history]   The Chemical History of a Candle
 98.7%   3 secs   451,772 ch  [biography]         Incidents in the Life of a Slave Girl
 98.7%   3 secs   375,758 ch  [biography]         Autobiography of Benjamin Franklin
 98.2%   5 secs   309,016 ch  [philosophy]        Second Treatise of Government
 98.0%   5 secs   124,579 ch  [philosophy]        Common Sense
 97.9%   4 secs   167,761 ch  [drama]             The Master Builder
 97.4%   3 secs 1,212,771 ch  [biography]         The Life of Samuel Johnson (Boswell)
 95.5%   3 secs   120,207 ch  [ancient-classical] The Birds (Aristophanes)
 91.5%   2 secs   179,308 ch  [german-literature] Faust Part I
```

The 100K-character floor matters. Seven more books are >90% in one section
but *under* it (*Sleepy Hollow*, *The Colour Out of Space*, *The Shunned
House*, *Civil Disobedience*, ...): short stories and essays with no internal
divisions. One section is correct for those. The defect is long works whose
divisions exist in the text and were never marked. *The Dunwich Horror* sits
on the line and needs a look before it goes on either list.

Boswell's *Johnson* is the worst case by volume: 1.2 million characters,
effectively unbrowsable.

## Three root causes, all in `text_to_markdown` (`src/gutenberg_kg/gutenberg.py`)

Verified against the code and against the raw `pg148.txt` fetched from
Gutenberg on 2026-09-03.

### A. `HEADING_PATTERNS` does not know these shapes

The list (L67-207) recognises `CHAPTER`/`BOOK`/`PART`/`ACT`/`SCENE`/
`LETTER`/`STAVE`/`SURA` followed by a roman or arabic numeral, ordinal
`THE FIRST BOOK`, the Bible book names, `I. A SCANDAL IN BOHEMIA`, a bare
`IV.`, and a short ALL-CAPS line. Nothing else becomes a heading. What the
15 books actually use:

| shape | example | book | pattern present? |
|---|---|---|---|
| word-numeral chapter | `Chapter One` ... `Chapter Ten` | The Trial | **no** (`Chapter` requires `[IVX]+` or `\d+`) |
| Title-Case story title | `The Story of the Merchant and the Genius` | 1001 Nights (hundreds of them) | **no** |
| editorial hinge line | `Continuation of the Account of my Life, begun at Passy, near Paris,` | Franklin | **no** |
| Title-Case standalone | `Preface`, `Introduction.` | 1001 Nights, Symposium | **no** (only ALL-CAPS) |
| cardinal PART | `PART ONE` / `PART TWO` | (common) | **no** (accepts `FIRST`..`TWELFTH`, not `ONE`..) |

Confirmed from the Markdown on disk: *The Trial* has all ten `Chapter One`
.. `Chapter Ten` lines present as plain text at L14, 894, 1424, 2146, 2384,
2599, 3234, 4812, 5738, 6467. *1001 Nights* has `The Story of ...` at L242,
413, 543, 657, 789, 866, 913, 1270, 1406, ... The structure is there; the
converter walks past it.

### B. The title page is promoted to headings

`_skip_front_matter` (L530) skips only lines matching `FRONT_MATTER_SKIP`
(producer/transcriber credits). It does not skip a title page. The raw
#148 begins, after the START marker:

```
THE AUTOBIOGRAPHY OF BENJAMIN FRANKLIN

The Harvard Classics

WITH INTRODUCTION AND NOTES

EDITED BY

CHARLES W ELIOT LLD

P F COLLIER & SON COMPANY
NEW YORK
1909
```

Every ALL-CAPS line here passes `_is_heading`'s last pattern (<=60 chars,
<=8 words, no trailing `,`/`;`). Then the subtitle-absorption loop at L664
(`while ... lines[k].strip().isupper(): subtitle_lines.append(...)`) glues
consecutive ALL-CAPS lines together. That is exactly how
`### CHARLES W ELIOT LLD P F COLLIER & SON COMPANY NEW YORK` was
manufactured. It is a section in the index, it is a seed in retrieval, and
it is the front-matter contamination already tracked in
`analysis/front_matter_assessment.json`, now with its mechanism named.

The same loop is why the body's only heading reads
`BENJAMIN FRANKLIN HIS AUTOBIOGRAPHY`: raw L129 `BENJAMIN FRANKLIN` and
L131 `HIS AUTOBIOGRAPHY` were fused. Harmless there; harmful on the title
page.

### C. Gutenberg's own "Navigation" block is not recognised as a TOC

Raw L45-50 of `pg148.txt`:

```
Navigation

    Letter from Mr. Abel James.
    Publishes the first number of "Poor Richard's Almanac.
    Proposes a Plan of Union for the colonies
    Chief events in Franklin's life.
```

This is **in Gutenberg's source**, not scrape residue on our side: an
artefact of PG's HTML-to-text for this edition. `_detect_toc` (L553) looks
only for `CONTENTS` / `TABLE OF CONTENTS`, so the block sails through and
becomes the opening prose of chunk 0001 (`1909 Navigation Letter from Mr.
Abel James. ...`). Same class as B: junk at the top of the file that the
retrieval layer treats as content.

### What is *not* the cause

- **DocKG.** `doc_kg/chunker.py` `_split_by_headings` treats ATX headings
  as hard splits and does nothing else with structure. It reproduces the
  Markdown faithfully. A fallback that windows oversized sections would
  live there, but it is a safety net, not the fix (see Phase 3).
- **`export_swift.py`.** Section rows are DocKG's `section` nodes passed
  through (`SEARCHED_KINDS`, L109; empty sections deliberately kept, L397).
  Fix the Markdown and the pack follows without a change here.
- **The diary pipeline.** Not involved. Franklin is a biography.

## The fix, in phases

Each phase has a gate. Nothing advances on a green build alone, because the
failure mode of every heading rule is *over*-promotion in some other book,
and that is invisible to a build.

### Phase 0: make the measurement a check

Promote the inline query that produced the CSV into
`scripts/check_sections.py`:

- Reads a pack (or the DocKG store) and prints, per book: section count,
  share of text in the largest section, largest section size.
- Flags `share > 0.90 and largest > 100_000`.
- `--baseline FILE` diffs against a saved run and reports every book whose
  section count *changed*, up or down, so a new heading rule that fires
  spuriously in an unrelated book is caught by name.
- Save `analysis/monolithic_sections_20260903.csv` as the baseline.

**Gate:** the script reproduces the 15-book list above from the current
pack.

### Phase 1: stop promoting the title page (root cause B)

Smallest change, largest retrieval-quality effect, zero risk to body
headings.

1. Extend `_skip_front_matter` to skip a title page: from the START marker
   to the first substantial paragraph (>= 3 consecutive non-blank lines of
   prose) or the first recognised body heading, treat short standalone
   lines as title-page matter, not headings. The subtitle-absorption loop
   must not run in that region.
2. Recognise `Navigation` as a TOC start in `_detect_toc` (root cause C),
   alongside `CONTENTS`. The existing end-of-TOC logic then drops the
   four-line block.

**Tests** (`tests/test_gutenberg.py`, alongside the existing
`test_skip_front_matter_*`): a Harvard Classics-style title page produces
no `###` lines; `Navigation` + indented list is skipped; a book whose real
first heading is ALL-CAPS on the first line after the marker (many are)
still gets it.

**Gate:** `check_sections --baseline` shows section counts *drop by exactly
the number of title-page lines* in affected books and change nowhere else.
Spot-check three: Franklin loses the `CHARLES W ELIOT` section, the Darwin
and Faraday front pages lose theirs.

### Phase 2: teach the converter the missing shapes (root cause A)

One pattern at a time, each with its own gate, in order of how many books
it fixes against how easily it misfires:

1. **Word-numeral `Chapter One`.** Add `ONE..THIRTY` (and `FIRST..`) to
   the `Chapter`/`CHAPTER` numeral alternation. Also `PART ONE`. Low risk:
   the keyword anchors it. Fixes *The Trial* outright (10 chapters).
2. **`The Story of ...` and similar Title-Case standalone titles.** This is
   the risky one: a Title-Case line under 60 characters, standing alone
   between blank lines, is also what a one-line paragraph looks like. Gate
   it hard: must be preceded *and* followed by a blank line, must not end
   in `.,;:!?`, must not start with a pronoun/article that begins a
   sentence in context ... or, more robustly, only fire when the same
   shape repeats >= 5 times in the file (a story collection has dozens;
   prose has none). The repeat-count guard is the one to try first.
   Fixes *1001 Nights*.
3. **Title-Case `Preface` / `Introduction.` / `Epilogue`.** A short fixed
   vocabulary, standalone. Low risk.
4. **Editorial hinge paragraphs** (Franklin's `Continuation of the Account
   of my Life, begun at Passy` and `[Thus far written at Passy, 1784.]`).
   These are edition-specific and there are only two of them. Do *not*
   generalise; handle via Phase 4 if at all.

**Gate per pattern:** `check_sections --baseline` shows the *intended*
books gain sections and **no other book changes**. Any collateral change
is a misfire to be read, not accepted. Plus a `test_is_heading_*` per
pattern with a positive and a look-alike negative.

### Phase 3: the safety net, for texts with no marks at all

Some long works genuinely have no divisions the converter can find (the
Symposium, Darwin, *Common Sense*, Boswell in places). Two options; pick
one after Phases 1-2 land and the residual list is known:

- **Windowing in DocKG** (`doc_kg/chunker.py`): when a section exceeds N
  chunks, emit synthetic sub-sections (`Part 1 of 9` ...) at paragraph
  boundaries. Universal, boundaries meaningless, and it is a change in a
  different repo that every DocKG consumer inherits.
- **Windowing in `export_swift.py`**: same idea, applied only to the
  on-device packs at export time. Contained to this repo and to Browse,
  which is the only place the monolith is user-visible. Retrieval is
  unaffected either way, since it works on chunks.

The second is the smaller blast radius and is the recommendation.

### Phase 4: per-book overrides, sparingly

For the handful of edition-specific hinges (Franklin's four Parts) a
per-book heading list in the catalog (`scripts/catalogs/`) that the
converter applies as literal-line matches. Keep it to books where the
division is famous enough that a reader expects it. Not a general
mechanism.

## Applying it: the pipeline, end to end

There is no cached raw text; conversion happens at download. So a converter
fix reaches the corpus only by re-downloading:

```sh
gutenkg download book <id> --force        # re-fetch pg<id>.txt, re-convert
gutenkg build-corpus --update             # incremental: re-embed changed nodes only
gutenkg export-swift --verify             # packs + golden gate
make ios-deploy                           # push, verify, relaunch
```

`--update` (cmd_build_corpus.py L114) is what keeps this from being the
24-minute full rebuild. The `--force` re-download is per book, so the
affected 15 (plus whatever Phase 1 touches, which is *every* book with a
title page) can be scripted from the CSV.

Note the re-download is a network fetch from Gutenberg per book, and PG's
text for a given ID does change between "Most recently updated" dates
(#148: March 2024). A re-download can therefore move text for reasons
unrelated to this fix. Diff the resulting `.md` against the committed one
before ingesting, and treat unexpected body changes as their own event.

## Risks

- **Over-promotion is silent.** A new heading rule that fires in the middle
  of a paragraph somewhere splits a real section in two, and nothing fails.
  The `--baseline` diff in Phase 0 is the only thing that sees it. Do not
  skip it.
- **Retrieval seeds change.** Removing the title-page sections (Phase 1)
  removes retrieval seeds that currently exist. That is the intent, but the
  golden gate (`export-swift --verify`) replays twelve fixed queries and
  should be re-run after Phase 1 to confirm ranks hold.
- **Chunk ids move.** Re-converting a book shifts `char_start` for every
  chunk after the first change. Anything holding chunk ids (bookmarks, the
  `similar_to_*` analyses) is stale for those books afterwards.

## Open questions

1. *The Dunwich Horror* (102K, one section): Lovecraft's original is in ten
   numbered parts. Check the Gutenberg text for `I.`/`II.` markers before
   deciding whether it belongs on the fix list or the "correctly
   single-section" list.
2. Phase 2.2 (Title-Case story titles): repeat-count guard, or the stricter
   context rules? The guard is simpler and I would try it first, but it
   will not help a book with three or four such titles.
3. Phase 3: DocKG or export-time? Recommendation above is export-time.
4. Is a corpus-wide re-download (which Phase 1 implies, since every book
   has a title page) acceptable, or should Phase 1 be applied only to the
   books the CSV flags and the rest wait for their next natural re-fetch?

## References

- `src/gutenberg_kg/gutenberg.py`: `HEADING_PATTERNS` L67, `_is_heading`
  L483, `_skip_front_matter` L530, `_detect_toc` L553, `text_to_markdown`
  L583, subtitle absorption L651-693
- `../doc_kg/src/doc_kg/chunker.py`: `_split_by_headings` L276
- `src/gutenberg_kg/export_swift.py`: `SEARCHED_KINDS` L109, section
  passthrough L393-434
- `analysis/monolithic_sections_20260903.csv`: the measurement
- `analysis/front_matter_assessment.json`: the earlier front-matter finding
  this gives a mechanism to
