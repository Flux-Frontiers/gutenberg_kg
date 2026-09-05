"""Heading vocabulary shared by the Gutenberg and Internet Archive converters.

Both downloaders turn a plain-text book into Markdown, and both have to decide
which lines are headings. They used to answer that question with two separate
pattern lists, and the Archive's copy was the poorer one: it knew CHAPTER,
PART, SECTION and DIVISION and nothing else, so none of the work on title
pages, word numerals or templated story titles reached a scanned book.

The vocabulary lives here now and the callers supply what is genuinely their
own -- the Archive's OCR guards and its ``Ques.`` pattern, Gutenberg's
producer-credit skip.

:data:`HEADING_PATTERNS` is the vocabulary, ordered by specificity.
:data:`STRUCTURAL_PATTERNS` is the same list without the bare ALL-CAPS
catch-all, for telling a real heading from a line that merely looks like one.
It is derived by identity rather than by position: reaching for these by index
(``HEADING_PATTERNS[-1]``) silently rewired itself whenever a pattern was
added near the end, which cost a live IndexError once already.
"""

from __future__ import annotations

import re

# Three patterns _is_heading has to post-process rather than accept verbatim.
# They are named because it used to reach for them by position
# (HEADING_PATTERNS[-1], [-2], [-3]), which silently rewired itself the moment
# a new pattern was appended near the end.
ALL_CAPS_PATTERN = re.compile(r"^([A-Z][A-Z\s\-',:]{2,60})$")
ROMAN_STANDALONE_PATTERN = re.compile(r"^([IVXLCDM]{1,6})\.\s*$")
ROMAN_TITLED_PATTERN = re.compile(r"^([IVXLCDM]{1,6})\.\s+([A-Z][A-Z\s\-',:]{2,60})$")

# Common heading patterns found in Gutenberg texts, ordered by specificity.
# Each tuple: (compiled regex, markdown heading level, group index for title)
HEADING_PATTERNS = [
    # "THE FIRST BOOK" / "THE SECOND BOOK" (ordinal, e.g. Meditations)
    (
        re.compile(
            r"^THE\s+(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|"
            r"NINTH|TENTH|ELEVENTH|TWELFTH|THIRTEENTH)\s+BOOK$",
            re.IGNORECASE,
        ),
        2,
    ),
    # VOLUME / BOOK / PART + numeral (h2).
    #
    # The optional ``THE`` and the spelled-out ordinals mean this also covers
    # Dickens' "Book the First--Recalled to Life", which used to have a rule
    # of its own. That rule never fired: this one is earlier in the list and
    # matches the same lines to the same level, so first-match-wins gave it
    # every hit. A Tale of Two Cities' three book divisions are the corpus
    # evidence -- see the shadowing tests in tests/test_headings.py.
    (
        re.compile(
            r"^(?:VOLUME|BOOK|PART)\s+"
            r"(?:THE\s+)?"
            r"(?:[IVXLCDM]+|FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|"
            r"NINTH|TENTH|ELEVENTH|TWELFTH|\d+)(?![A-Za-z])"
            r"(?:\.?\s*[-—:.]?\s*(.+))?$",
            re.IGNORECASE,
        ),
        2,
    ),
    # ACT (for plays, h2)
    (
        re.compile(
            r"^ACT\s+(?:[IVXLCDM]+|\d+)(?![A-Za-z])"
            r"(?:\.?\s*[-—:.]?\s*(.+))?$",
            re.IGNORECASE,
        ),
        2,
    ),
    # CHAPTER level (h2) — "CHAPTER I.", "CHAPTER XIV", "CHAPTER 3".
    # IGNORECASE, so Title Case "Chapter 1" comes here too; the separate
    # Title Case rule that used to follow was identical apart from the flag
    # and never saw a line.
    (
        re.compile(
            r"^CHAPTER\s+(?:[IVXLCDM]+|\d+)(?![A-Za-z])\.?"
            r"(?:\s*[-—:.]?\s*(.+))?$",
            re.IGNORECASE,
        ),
        2,
    ),
    # Word numerals: "Chapter One", "CHAPTER TWENTY-THREE", "PART TWO".
    # Kafka's Trial carries all ten of its chapter lines this way and the
    # converter walked past every one.  Unlike the numeral forms above, a
    # separator or the end of the line is required after the numeral: "Chapter
    # One" is a heading, "Chapter One was the longest" is a sentence, and only
    # the punctuation tells them apart.
    #
    # VOLUME is deliberately absent.  Spelled out it is nearly always a
    # publisher's series label on the title page -- "Volume Seventeen" sits
    # between the editor and the printer in Nietzsche's collected works -- and
    # matching it there stops _skip_title_page, which treats a recognised
    # heading as the end of the front matter.  Roman "VOLUME I" is already
    # covered above.
    (
        re.compile(
            r"^(?:CHAPTER|BOOK|PART)\s+"
            r"(?:TWENTY|THIRTY|FORTY)?[-\s]?"
            r"(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE|"
            r"THIRTEEN|FOURTEEN|FIFTEEN|SIXTEEN|SEVENTEEN|EIGHTEEN|NINETEEN|"
            r"TWENTY|THIRTY|FORTY|FIFTY)"
            r"(?:\s*[-—:.]\s*(.+)|\.?)$",
            re.IGNORECASE,
        ),
        2,
    ),
    # SCENE (for plays, h3)
    (
        re.compile(
            r"^SCENE\s+(?:[IVXLCDM]+|\d+)(?![A-Za-z])"
            r"(?:\.?\s*[-—:.]?\s*(.+))?$",
            re.IGNORECASE,
        ),
        3,
    ),
    # LETTER I / LETTER 1 / "Letter 1" (epistolary novels)
    (
        re.compile(
            r"^Letter\s+(?:[IVXLCDM]+|\d+)(?![A-Za-z])"
            r"(?:\.?\s*[-—:.]?\s*(.+))?$",
            re.IGNORECASE,
        ),
        2,
    ),
    # Bible book headings: "The First Book of Moses: Called Genesis",
    # "The Book of Joshua", "The Gospel According to Saint Matthew", etc.
    (
        re.compile(
            r"^The\s+(?:First|Second|Third|Fourth|Fifth)\s+Book\s+of\s+.+$",
        ),
        2,
    ),
    (
        re.compile(
            r"^The\s+(?:Book\s+of|Gospel\s+According|Epistle|General\s+Epistle|"
            r"Revelation|Acts|Song|Lamentations)\s+.+$",
        ),
        2,
    ),
    # Testament dividers (Bible)
    (
        re.compile(
            r"^The\s+(?:Old|New)\s+Testament.*$",
        ),
        2,
    ),
    # SURA headings (Quran).  Rodwell prints a footnote digit straight after
    # the word or the numeral and an edition-order marker in brackets at the
    # end: "SURA1 XCVI.-THICK BLOOD, OR CLOTS OF BLOOD [I.]".  A separator
    # after the numeral is required so prose like "SURA I saw ..." is not
    # mistaken for a heading.
    (
        re.compile(
            r"^SURA\d*\s+([IVXLCDM]+)\d*\s*[.\-—]+\s*(.*?)\s*(?:\[[IVXLCDM]+\.?\])?$",
            re.IGNORECASE,
        ),
        2,
    ),
    # STAVE I / STAVE 1 (A Christmas Carol).
    #
    # No book in the corpus uses this, so unlike the rules removed above it
    # earns its place on expectation rather than evidence. It is kept anyway:
    # nothing else claims "STAVE I" (the ALL-CAPS catch-all would, but later
    # and at the wrong level), so deleting it saves two lines and silently
    # costs A Christmas Carol its divisions the day it is downloaded.
    (
        re.compile(
            r"^STAVE\s+(?:[IVXLCDM]+|\d+)(?![A-Za-z])"
            r"(?:\.?\s*[-—:.]?\s*(.+))?$",
            re.IGNORECASE,
        ),
        2,
    ),
    # "I. A SCANDAL IN BOHEMIA" — Roman numeral + period + ALL CAPS TITLE
    (ROMAN_TITLED_PATTERN, 2),
    # Roman numeral standalone: "I.", "II.", "XIV." (section breaks within stories)
    # Must have a period to distinguish "I." from "I think..."
    (ROMAN_STANDALONE_PATTERN, 3),
    # Title-Case front and back matter: "Preface", "Introduction.",
    # "Epilogue".  A closed vocabulary standing alone on its line, so it
    # cannot fire inside prose the way a general Title-Case rule would.  The
    # ALL-CAPS spellings are already caught by the catch-all below.
    (
        re.compile(
            r"^(?:Preface|Foreword|Prologue|Introduction|Epilogue|Afterword|"
            r"Postscript|Conclusion|Dedication|Envoi)\.?$",
        ),
        3,
    ),
    # Standalone ALL-CAPS heading (at least 3 chars, max ~60, not a sentence)
    (
        ALL_CAPS_PATTERN,
        3,
    ),
]


#: The vocabulary minus the bare ALL-CAPS catch-all, derived by identity
#: so that adding a pattern cannot quietly change what counts as
#: structural.
STRUCTURAL_PATTERNS = [(p, lvl) for p, lvl in HEADING_PATTERNS if p is not ALL_CAPS_PATTERN]

# Literal lines that open a table-of-contents-shaped block. "Navigation" is
# Gutenberg's own auto-generated nav list (an HTML-to-text artefact seen in
# some editions, e.g. #148 Franklin); it is handled separately from
# CONTENTS because its entries are indented list items rather than
# dot-leader chapter listings, and blank-line-count heuristics that work for
# CONTENTS badly over-consume a Navigation block (see _detect_toc).
_TOC_CONTENTS_LINES = {"CONTENTS", "CONTENTS.", "TABLE OF CONTENTS", "TABLE OF CONTENTS."}
_TOC_NAVIGATION_LINES = {"NAVIGATION", "NAVIGATION."}

#: How far past a CONTENTS marker a profiled contents region may begin and
#: still be the listing that marker announces. Kant's Critique opens its
#: numbered listing 185 lines after the word "CONTENTS", Symzonia 116; the
#: numbered lists in Ruskin's and Diogenes Laertius' prefaces -- which are
#: not contents and must never be deleted -- sit 660 and 1,900 lines from
#: theirs. Measured across all 243 cached texts.
_CONTENTS_ANCHOR_WINDOW = 250

#: When the region begins within this many lines of the marker, everything
#: between is listing preamble -- "VOLUME I." in Emma, "LES MISÉRABLES /
#: PREFACE / VOLUME I—FANTINE / BOOK FIRST" in Les Miserables -- and is
#: skipped with it. Further away, the intervening lines are kept: they are
#: as likely a preface as a preamble, and deleting a preface is the worse
#: mistake by far. The cost of keeping them is the marker line leaking in as
#: text.
_CONTENTS_PREAMBLE = 60


# Safety bounds on _skip_title_page: real title pages are a handful of
# fields within the first couple dozen lines. These just stop a pathological
# run of short lines (e.g. a page of verse) from being consumed wholesale.
_TITLE_PAGE_MAX_LINES = 60
_TITLE_PAGE_MAX_FIELDS = 20

# A title page must have at least this many standalone fields before the
# region is treated as front matter rather than a real (single-line) body
# heading -- so "CHAPTER I" or a lone "INTRODUCTION" immediately followed by
# prose is left alone, per test_skip_front_matter_no_front_matter and
# friends.
_TITLE_PAGE_MIN_FIELDS = 2


#: Words allowed to stay lowercase inside a Title-Case line.
_TITLE_CASE_SMALL_WORDS = frozenset(
    "a an and as at but by for from in into nor of on onto or over the to up "
    "upon with within without".split()
)

#: How many standalone Title-Case lines must open with the *same* phrase
#: before they are read as titles rather than one-line paragraphs.  A bare
#: count of Title-Case lines is far too loose a guard -- it promotes 552 of
#: Hobbes's marginal notes in Leviathan and 292 lines of Leaves of Grass.
#: What marks a collection's titles is that they are built to a template:
#: Lane's Nights prints nineteen lines opening "The Story of", while
#: Hobbes's notes and Whitman's poem titles share no opening at all.
_REPEATED_TITLE_THRESHOLD = 5

#: Words of a title line taken as its template key.
_TITLE_PREFIX_WORDS = 2

#: Opening words of a plate caption.  Illustration captions are Title-Case,
#: stand alone between blanks and come in templated runs -- "Frontispiece
#: Volume One", "Titlepage Volume Two" through Les Miserables -- so they clear
#: every other test here and have to be named.
_CAPTION_FIRST_WORDS = frozenset(
    "frontispiece titlepage illustration illustrations plate plates facsimile "
    "portrait map maps figure diagram engraving".split()
)


def breaks_before_heading(prev_line: str) -> bool:
    """
    Whether *prev_line* separates a heading from body text as a blank line would.

    A heading is normally only honoured after a blank line, which keeps
    mid-paragraph phrases from being promoted.  Bilingual editions break that
    assumption: Legge's Analects prints the Chinese heading immediately above
    the English one with nothing between, so every ``BOOK I.`` in the volume
    was silently swallowed into the body and the whole work collapsed into one
    section.  A line carrying no Latin letters is not prose in these texts, so
    it can stand in for the blank.

    :param prev_line: The preceding source line.
    :return: ``True`` if a heading may follow it.
    """
    stripped = prev_line.strip()
    if not stripped:
        return True
    return not any(ch.isalpha() and ch.isascii() for ch in stripped)


def is_heading(line: str, patterns=HEADING_PATTERNS, all_caps_guard=None) -> tuple[int, str] | None:
    """Check if a line is a structural heading.

    Returns (level, heading_text) or None.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return None

    all_caps_pattern = ALL_CAPS_PATTERN
    roman_standalone_pattern = ROMAN_STANDALONE_PATTERN
    roman_titled_pattern = ROMAN_TITLED_PATTERN

    for pattern, level in patterns:
        m = pattern.match(stripped)
        if not m:
            continue

        # ALL-CAPS standalone: reject sentence-like lines
        if pattern is all_caps_pattern:
            if len(stripped) > 60 or stripped.endswith(",") or stripped.endswith(";"):
                continue
            words = stripped.split()
            if len(words) > 8:
                continue
            # Scanned text needs stricter rejection than typed text; the
            # caller supplies it rather than this module guessing which
            # corpus it is looking at.
            if all_caps_guard is not None and not all_caps_guard(stripped):
                continue

        # Bare roman numeral "IV." — sub-section divider
        if pattern is roman_standalone_pattern:
            roman = m.group(1)
            if not re.match(r"^[IVXLCDM]+$", roman):
                continue
            return (level, f"{roman}.")

        # "I. A SCANDAL IN BOHEMIA" — roman + titled
        if pattern is roman_titled_pattern:
            roman = m.group(1)
            if not re.match(r"^[IVXLCDM]+$", roman):
                continue
            title_part = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
            heading = f"{roman}. {title_part}".strip()
            return (level, heading)

        return (level, stripped)
    return None


def is_structural_heading(line: str, structural=None) -> bool:
    """Whether *line* matches a keyword-anchored heading pattern (CHAPTER,
    BOOK, PART, ACT, ...), as opposed to the generic standalone ALL-CAPS
    catch-all. Used to recognise a real body heading even when it is short
    enough to otherwise look like a title-page field."""
    for pattern, _level in STRUCTURAL_PATTERNS if structural is None else structural:
        if pattern.match(line):
            return True
    return False


def looks_like_title_field(line: str, structural=None) -> bool:
    """Whether *line* has the shape of a title-page field: a short
    standalone label (ALL-CAPS, a Title-Case phrase, or a bare
    number/date), not a real heading and not a line of prose."""
    if not line or len(line) > 60:
        return False
    if is_structural_heading(line, structural):
        return False
    if line.isupper():
        return True
    if re.match(r"^[\d\W]+$", line):
        return True
    words = line.split()
    if 0 < len(words) <= 8 and line[-1] not in ".!?;,":
        return all(not w[0].isalpha() or w[0].isupper() for w in words)
    return False


def looks_like_story_title(line: str) -> bool:
    """Whether *line* has the shape of a Title-Case work title.

    Deliberately shape-only: the decision to honour it is
    :func:`_repeated_title_lines`'s, and rests on how often the shape recurs.

    :param line: A stripped source line.
    :return: ``True`` if the line reads as a title rather than prose.
    """
    if not 4 <= len(line) <= 70 or line[-1] in ".!?;:":
        return False
    if line.isupper() or not line[0].isupper():
        return False
    words = line.split()
    if len(words) < 2:
        return False
    if words[0].strip("“”\"'(),").lower() in _CAPTION_FIRST_WORDS:
        return False
    capitalised = 0
    for word in words:
        bare = word.strip("“”\"'(),")
        if not bare:
            continue
        if bare[0].isupper():
            capitalised += 1
        elif bare.lower() not in _TITLE_CASE_SMALL_WORDS:
            return False
    return capitalised >= 2


def repeated_title_lines(
    lines: list[str], start: int, skip: range, patterns=HEADING_PATTERNS
) -> set[int]:
    """Find Title-Case lines frequent enough to be a collection's titles.

    A Title-Case line standing alone between blank lines is also what a
    one-line paragraph looks like, so shape alone cannot decide it, and
    neither can how many such lines a file holds. What marks a collection's
    titles is a shared template: Lane's *One Thousand and One Nights* prints
    nineteen lines opening ``The Story of`` and the converter walked past
    every one, collapsing the book into a single section. Grouping by that
    opening is what separates them from Hobbes's marginal notes and Whitman's
    poem titles, which are equally Title-Case and equally standalone but
    share no phrasing.

    :param lines: All source lines.
    :param start: First line of the body.
    :param skip: Line range already claimed by a table of contents.
    :returns: Indices to treat as headings, empty when no template recurs.
    """
    by_prefix: dict[str, dict[str, set[int]]] = {}
    for i in range(start, len(lines)):
        if i in skip:
            continue
        stripped = lines[i].strip()
        if not stripped:
            continue
        if i and lines[i - 1].strip():
            continue
        if i + 1 < len(lines) and lines[i + 1].strip():
            continue
        if is_heading(stripped, patterns):
            continue
        if not looks_like_story_title(stripped):
            continue
        prefix = " ".join(stripped.lower().split()[:_TITLE_PREFIX_WORDS])
        by_prefix.setdefault(prefix, {}).setdefault(stripped.lower(), set()).add(i)

    found: set[int] = set()
    for variants in by_prefix.values():
        # Distinct titles, not repetitions of one line: a table of contents
        # names each story once, while Don Quixote's 260 "Full Size" plate
        # captions and the Quran's bismillah before every sura are the same
        # line over and over, and are not titles at all.
        if len(variants) >= _REPEATED_TITLE_THRESHOLD:
            for group in variants.values():
                found |= group
    return found


def skip_title_page(lines: list[str], start_idx: int, structural=None) -> int:
    """Skip a title page (title, subtitle, editor, publisher, year) that
    precedes the real body -- e.g. the Harvard Classics front page ahead of
    Franklin's Autobiography (#148), which the standalone ALL-CAPS heading
    rule would otherwise turn into its own section.

    Stops at the first line that is not title-field-shaped, at a
    table-of-contents marker, or at a run of 2+ blank lines -- Gutenberg
    editions commonly widen the gap to mark a structural boundary (e.g. the
    four blank lines between Franklin's title page and its Navigation
    block), which distinguishes it from the single blank line that
    separates ordinary paragraphs. Only commits the skip if at least
    _TITLE_PAGE_MIN_FIELDS fields were found, so a single ALL-CAPS heading
    immediately followed by prose -- a real chapter opener -- is never
    eaten.
    """
    i = start_idx
    fields = 0
    blank_run = 0
    while (
        i < len(lines)
        and (i - start_idx) < _TITLE_PAGE_MAX_LINES
        and fields < _TITLE_PAGE_MAX_FIELDS
    ):
        stripped = lines[i].strip()
        if not stripped:
            blank_run += 1
            if blank_run >= 2:
                break
            i += 1
            continue
        blank_run = 0
        upper = stripped.upper()
        if upper in _TOC_CONTENTS_LINES or upper in _TOC_NAVIGATION_LINES:
            break
        if not looks_like_title_field(stripped, structural):
            break
        i += 1
        fields += 1

    if fields < _TITLE_PAGE_MIN_FIELDS:
        return start_idx
    return i


def detect_toc(
    lines: list[str],
    start: int,
    end: int,
    regions: list[tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    """Locate a table of contents and return the line range to skip.

    The marker line -- ``CONTENTS``, ``TABLE OF CONTENTS`` or Gutenberg's
    generated ``Navigation`` -- is found the same way it always was. Where
    a ``CONTENTS`` listing *ends* is answered two ways, in order:

    1. From the structural profile. The caller passes the contents-shaped
       regions :func:`gutenberg_kg.spine.contents_regions` found, and the
       listing is the first of them beginning within
       :data:`_CONTENTS_ANCHOR_WINDOW` lines of the marker. This bounds a
       numbered listing exactly, whatever its blank lines do: Moby Dick's
       135 chapters, Les Miserables' 365 across 48 books, Emma's three
       restarts. It also stops the blank-line rule short of text it used
       to take -- the editor's preface of The Education of Henry Adams sat
       between the listing's last entry and the first triple blank.
    2. Failing that, by counting blank lines: the listing ends at a triple
       blank, or at a long line after a double one. The profile sees only
       numbered sequences, and the listings it cannot see -- named
       chapters, stories, poems, dialogues, about a fifth of the corpus --
       are exactly the ones this rule has always bounded. Its one way of
       deleting text, running to its bound when no blank pattern ever
       fired, was closed in #103: it declines instead.

    The marker is a hard requirement for the first, not a convenience. The
    profile also reports dense numbered regions deep inside books --
    Marcus Aurelius's numbered paragraphs, Ruskin's lettered sections --
    that are the book, not its contents. Anchoring to the marker is what
    keeps them out of reach.

    With no marker, or neither rule finding an end, this returns None:
    nothing is skipped and the listing leaks in as text, which costs a
    duplicate heading or two rather than a chapter.

    :param lines: The book's lines.
    :param start: Line to begin searching for the marker.
    :param end: Line to stop searching (exclusive).
    :param regions: Contents-shaped regions from the structural profile, as
        ``(first, last)`` line indices inclusive. None or empty means none
        were found.
    :returns: ``(start, end)`` line indices to skip, end exclusive, or None.
    """
    toc_start = None
    is_navigation = False
    for i in range(start, min(start + 200, end)):
        line = lines[i].strip().upper()
        if line in _TOC_CONTENTS_LINES:
            toc_start = i
            break
        if line in _TOC_NAVIGATION_LINES:
            toc_start = i
            is_navigation = True
            break

    if toc_start is None:
        return None

    if is_navigation:
        # Gutenberg's auto-generated "Navigation" block: a short list of
        # indented entries. Blank-line-count heuristics badly over-consume
        # here since these editions use plain single blank lines between
        # paragraphs throughout, so end at the first flush-left
        # (non-indented) line instead -- a real list item is always
        # indented in the raw text.
        i = toc_start + 1
        while i < min(toc_start + 100, end) and not lines[i].strip():
            i += 1
        while i < min(toc_start + 100, end) and lines[i].strip() and lines[i][:1].isspace():
            i += 1
        return (toc_start, i)

    for region_start, region_end in regions or ():
        if toc_start < region_start <= toc_start + _CONTENTS_ANCHOR_WINDOW:
            skip_from = (
                toc_start if region_start - toc_start <= _CONTENTS_PREAMBLE else region_start
            )
            return (skip_from, region_end + 1)

    # No numbered listing to anchor. The listings the profile cannot see --
    # named chapters, stories, poems -- end at a triple blank, or at a long
    # line after a double one.
    i = toc_start + 1
    blank_count = 0
    while i < min(toc_start + 300, end):
        line = lines[i].strip()
        if not line:
            blank_count += 1
            if blank_count >= 3:
                return (toc_start, i)
        else:
            if blank_count >= 2 and len(line) > 60:
                return (toc_start, i)
            blank_count = 0
        i += 1

    # No end found. Everything this function returns gets deleted from the
    # document, so guessing here is not a neutral act: Jekyll and Hyde's
    # contents are separated by single blank lines, neither rule above ever
    # fired, and the run to the bound swallowed the chapter heading and the
    # opening of the story -- the committed text begins mid-scene, on
    # Enfield already talking. Declining costs a duplicate heading or two
    # where the contents leak in as text; guessing costs the reader a
    # chapter.
    return None
