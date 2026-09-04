# A structural parser: reading the book before deciding what a heading is

Written 2026-09-04, after the monolithic-sections work (PRs #98-#103).
Design only; nothing below is implemented.

## Why the current converter keeps being wrong

`_is_heading` takes one line and answers yes or no. It has no idea what else
is in the book. Every defect fixed in the last round came from that, and each
fix was document-level knowledge bolted onto a line-level function:

| defect | what it actually needed to know |
|---|---|
| Franklin's publisher page became a section | that it was still in the front matter |
| 1001 Nights collapsed into one section | that `The Story of ...` recurs nineteen times |
| Hobbes gained 552 marginal notes as headings | that they recur but share no template |
| `Volume containing several works` became a heading | that no `Volume <n>` sequence exists |
| `Section locking, 3,954.` became a heading | the same |
| Jekyll lost its first page | where the contents list actually ends |

The last one is the important one, because it could not be fixed at all. The
contents-end rule counts blank lines; books that separate paragraphs with one
blank never satisfy it, so the scan ran to its bound and deleted whatever it
had crossed -- the chapter heading and the opening of the story. Sixteen books
were silently short about 13,000 words. The shipped fix (#103) makes the
scan decline rather than guess, which stops the deletion but leaves the
contents list leaking in as duplicate headings: Moby Dick browses 288
headings for 135 chapters.

Contents entries wrap in *The Innocents Abroad* and do not in *Moby Dick*, so
line length does not separate them. Neither does paragraph shape, blank
runs, indentation, or capitalisation. Nothing local to a line distinguishes
"CHAPTER 93. The Castaway." in a contents list from the same string above
chapter 93. **The difference is not in the line. It is in how many other
lines look like it, and how they are spread.**

## The signal

A book's chapter spine is a *dense, monotonic numeric sequence*. A contents
list is that same sequence at much higher density, because it prints in a few
hundred lines what the body spreads over tens of thousands.

Measured on the real corpus:

```
Moby Dick          CHAPTER 1..135   lines     14-285    span    272   density 0.496
                   CHAPTER 1..135   lines   812-21446   span  20635   density 0.007
Middlemarch        CHAPTER 1..86    lines     16-115    span    100   density 0.860
                   CHAPTER 1..86    lines   182-32799   span  32618   density 0.003
Innocents Abroad   CHAPTER 1..60    lines     12-413    span    402   density 0.147
                   CHAPTER 1..61    lines   452-18368   span  17917   density 0.003
```

Two to three orders of magnitude apart, on every book tried. The dense run is
the contents; the sparse run is the book. Both are bounded *exactly* -- Moby
Dick's contents are lines 14-285, where the blank-line heuristics variously
guessed 200 and 290 and took chapter one with them.

This one measurement replaces several separate rules:

- **Where the contents are.** The dense run, bounded by its own first and last
  member. No blank counting.
- **Which candidates are real.** Only members of a confirmed sequence. A
  lone `Volume C...` or `Section l...` belongs to no sequence and is rejected
  without needing the `(?![A-Za-z])` guard bolted on in #101.
- **Where the front matter ends.** Before the first body-spine member.
- **What this book's vocabulary is.** Whatever keyword its sequence uses --
  `CHAPTER`, `CANTO`, `Ques.`, `SURA` -- learned per book rather than
  guessed from a fixed list.

## Shape

Two passes over the lines, replacing nothing about how Markdown is emitted.

**Pass 1 -- profile.** Walk every line. For each line matching any candidate
template (keyword + numeral, bare numeral, Title-Case template, ALL-CAPS
standalone), record `(template, number, line_index)`. Promote nothing.

Then, per template, split the hits into monotonic runs and score each run by
length, density and coverage. A run is a **spine** if it is long enough
(>= 5), dense in numbering (few gaps), and monotonic. Where a template yields
two spines over the same number range, the denser one is a **contents list**
and the sparser one is the **body**.

**Pass 2 -- emit.** Convert as today, except that a line is a heading only if
it is a member of a body spine, or matches a non-sequential rule that
survived Pass 1's evidence (a lone `Preface`, a templated story title
recurring five times with distinct members). Lines inside a contents run are
dropped, bounded exactly.

## What this does not solve

- **Books with no sequence at all.** Franklin has four editorial hinges in
  6,595 lines; Boswell has none. They stay unstructured, and Phase 3's
  export-time windowing keeps them browsable. The parser should say "no spine
  found" plainly, so windowing is a considered fallback rather than an
  accident.
- **The Audels manuals**, whose structure is 800 `Ques.` lines and no
  numbering. Recurrence carries them, not sequence; Pass 1 must score both.
- **OCR damage.** A scan with `CHAPTER lll` for `III` breaks monotonicity.
  Tolerating one bad member in a long run is worth it; tolerating many is how
  false spines get in.

## Verification

The harness that caught every regression in the last round applies unchanged
and is the reason this is tractable:

- 243 Gutenberg raw texts and 9 Archive scans are cached locally, so a full
  old-vs-new comparison costs seconds and no network.
- Compare against a **pristine worktree**, not an in-place baseline --
  `headings.py` is imported by both sides, and an in-place comparison
  silently reported Moby Dick's baseline as 288 instead of 195.
- Read every difference. Three of the last round's misfires (a Nietzsche
  title-page label, 260 `Full Size` plate captions, Les Miserables'
  frontispieces) would have passed any test suite and were caught only by
  reading the diff.
- Corpus writes keep the directional rule that has worked: only-deletions,
  only-markup, or only-insertions, whichever the change should produce, and
  refuse anything else. It refused the one book that would have imported 500
  words of Google Books boilerplate, on the book most tempting to wave
  through.

**The gate for this work is Moby Dick at 135 chapter headings, no duplicates,
with "Call me Ishmael." intact** -- the two failures of the last round, which
no rule available today can satisfy at once.

## Sequencing

1. Pass 1 as a *reporting* script only: profile all 252 books, print the
   spines and contents runs it finds. No behaviour change. Read the output
   for books whose structure is already known and check it agrees.
2. Contents detection from the dense run, replacing `detect_toc`. Gate: the
   16 books that recovered text in #103 keep it, and Moby Dick loses its
   duplicates.
3. Spine-membership as the heading test, retiring the numeral lookaheads and
   the repeat-count guards those patches added.
4. Retire whatever of `HEADING_PATTERNS` the evidence says is dead.
