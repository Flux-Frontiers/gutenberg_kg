# OCR text from the Internet Archive

A book downloaded with `gutenkg ia download` is not typeset text. It is the
Internet Archive's OCR of a page scan, the item's `_djvu.txt` file.
`ia.clean_ocr` cleans that text before it is converted to Markdown. This page
describes what the cleanup removes, the notes it leaves in each book's
`reference.md`, and what it cannot repair. It also records what was found for
the Audel Electric Library, the corpus's only Internet Archive books so far.

## What the cleanup does

`clean_ocr` runs these steps in order. Each is tested against lines quoted
from the Audel scans (`tests/test_ia.py`, `tests/fixtures/ia/`).

1. Strips trailing whitespace from every line. The Archive's Tesseract text
   ends each line with a space, so before this step no hyphenated word was
   ever rejoined.
2. Normalizes ligatures and curly quotes.
3. Rejoins words hyphenated across a line break: `in-` and `credible` become
   `incredible`. A break followed by a blank line is left alone.
4. Removes page numbers standing alone on a line, including the thousands
   forms of a continuously paginated set, such as `4,047` and `4.047`.
5. Removes the back-of-book index.
6. Removes running headers: lines that repeat exactly, and running titles
   that repeat with a changing page number, such as
   `304 Dynamo and Motor Experiments`. Numbered headings such as `CHAPTER 130`
   are never treated as headers.
7. Removes figure markers.
8. Blanks lines of OCR debris, which are drawings, rotated or mirrored
   captions, and specks read as characters (`is_ocr_debris`). A line is
   debris when fewer than half of its characters are letters or digits, or
   fewer than half of its tokens read as words, numbers or abbreviations.
   In a text of 10,000 words or more, a word of three or more letters counts
   only if it recurs in the book's prose (`recurring_words`), because OCR
   garbage such as `Carmoog` almost never repeats. Short lines of ordinary
   words, prose made of rare words, formulas such as `E = I X R`, and table
   rows such as `Buff limestone........ 40-60 20` are kept. Debris lines are
   blanked, not deleted, so the text on either side of a figure is not run
   together.
9. Removes a mark standing alone at the edge of a line of text, such as the
   `|` in `any known force; |`.
10. Collapses runs of blank lines.

## Notes in reference.md

Every Internet Archive book's `reference.md` ends with a `## Text notes`
section, which `ia.text_notes` writes at download time. It names the OCR
engine, gives a count for each cleanup step, and says what was not repaired.
From Audel Volume 1:

```markdown
## Text notes

- **Source**: the Internet Archive's DjVu text, OCR by tesseract 5.0.0-1-g862e. It has not been proofread.
- **Hyphenated words rejoined**: 632
- **Page numbers removed**: 128
- **Page headers removed**: 518
- **Lines of OCR debris removed**: 3,206 (drawings, rotated or mirrored captions and specks read as text)
- **Stray margin marks removed**: 247
- **Not repaired**: words the scan cuts off at the page edge, misread words, and tables, which OCR does not keep in columns. Figures are omitted; their captions are kept where OCR read them as text.
```

To regenerate a book with the current cleanup, download it again:

```bash
gutenkg ia download audels-electric-library-vol-1 --genre audel-electric \
  --title "Audels Electric Library Vol 1" --force
```

Then carry the new text to the index, the bundle, the Swift packs, the image
and the web forest with `make refresh-text GENRE=audel-electric`. The bundle
rebuild must be the full `gutenkg build-corpus`: `--update` matches on node
ids, so a book whose text changed keeps its old vectors.

## What the cleanup cannot fix

- **Words cut off in the scan.** Nothing restores letters the scan does not
  contain, and the cleanup does not guess at them.
- **Misread words.** OCR errors inside otherwise good lines stay, for
  example `Fias. 449` for `Figs. 449`.
- **Tables.** OCR reads a table row by row without its columns, and a row
  with too many garbled cells is removed as debris.
- **Some debris.** Short fragments of a drawing that happen to look like
  words survive, such as `What` or `LIE I`.

## The Audel Electric Library scans

The eight volumes are the Internet Archive items
`audels-electric-library-vol-N` for volumes 1, 2, 3, 4, 7, 8, 9 and 10 of
the 1929 edition. They were scanned at 600 ppi and read by Tesseract 5.0.

### Cleanup results

Measured over all eight volumes on 2026-09-28, using `/usr/share/dict/words`
as an evaluation aid only. The code uses no dictionary.

| Measure | Before | After |
|---|---|---|
| Lines under 30 percent dictionary words | 22.4 percent of 150,138 | 3.7 percent of 101,836 |
| Dictionary words removed as debris | | 0.85 percent |

Most of the dictionary words removed as debris are labels inside drawings,
such as `COUNTER-WEIGHT` and `FUSED CUTOUT`, which belong to the figure.

### Words cut off at the binding

The scans are cropped into the binding. A left-hand page loses the last
letters of its lines and a right-hand page the first letters. Page 304 of
Volume 1 reads "Professors Miller an" and "design a machine o" in the page
image itself, so re-running OCR would not recover them.

The table gives the share of prose lines that end, or begin, with a
fragment that is not a word. On clean Gutenberg text the same measure is 1.5
to 3.5 percent for line ends and 2.3 to 3.7 percent for line starts, from
abbreviations and technical terms.

| Volume | Line ends cut | Line starts cut |
|---|---|---|
| 1 | 8.5 percent | 7.9 percent |
| 2 | 3.9 percent | 7.4 percent |
| 3 | 4.8 percent | 8.0 percent |
| 4 | 3.7 percent | 8.6 percent |
| 7 | 5.9 percent | 7.8 percent |
| 8 | 8.7 percent | 10.6 percent |
| 9 | 4.5 percent | 7.7 percent |
| 10 | 4.6 percent | 7.1 percent |

Every volume loses line starts. Volumes 1 and 8 also lose many line ends.

### Other scans

On 2026-09-28 the Internet Archive was searched for other scans of the same
edition. Later editions, from the 1940s to the 1960s, are revised texts, and
the Better World Books scans are lending-only, so neither can replace these.

| Volume | Scan | Finding |
|---|---|---|
| 1 | `in.ernet.dli.2015.126215` (Digital Library of India, 1929) | Fewer cut line ends (3.6 against 8.5 percent) and fewer misread words, but only 68 percent of its five-word phrases match ours, so it may be a different printing. Not adopted. |
| 3 | `dli.ernet.18936`, `in.ernet.dli.2015.148528` | Worse than ours. |
| 7 | `audels-new-electric-library-vol.-7-1929` | The same text, slightly better. Not worth a swap. |
| 7 | `in.ernet.dli.2015.148530` (1931) | Worse than ours. |
| 8 | `audels-new-electric-library-vol.-8-1930` | The same text (84 percent of phrases match), with half the cut line ends (4.0 against 8.7 percent) and the same misread rate. The best candidate for a replacement. |
| 9, 10 | `audels-new-electric-library-vol.-9-1931`, `-vol.-10-1931` | Slightly better; ours are already close to clean text. |
| 2, 4 | None | No other scan of this edition. |
