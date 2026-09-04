"""Structural profiling: find numbered sequences in a book's raw lines.

Step 1 of ``analysis/STRUCTURAL_PARSER_PLAN.md``. This module is read-only:
it reports where numbered sequences (``CHAPTER 1..135``, ``CANTO I..XXXIV``,
...) occur in a book, and separates a table of contents from the body it
lists by clustering: hits close together with nothing but more listing
between them are one contents-shaped region; a hit sitting alone, with real
prose on either side, is a real heading (:func:`cluster_hits`).

The first version of this module paired runs by density instead --
``CHAPTER 1..135`` printed at 0.496 in Moby Dick's contents versus 0.007 in
its body, for example -- which works for a single-volume book but breaks on
one where a keyword's numbering restarts partway through, such as chapter
numbers resetting at each of Emma's three volumes or each of Les
Miserables' forty-eight books: numbering restarts split what should be one
region into several small ones on both the contents and the body sides,
which a rule keyed to monotonic runs cannot tell apart. Clustering by line
position and what sits between hits doesn't care about the numbers at all,
so a multi-volume contents listing collapses into one cluster the same way
a single-volume one does, without special-casing volumes.

Nothing here changes what ``text_to_markdown`` emits; that is a later step
once this signal has been read against the whole corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gutenberg_kg.headings import _TITLE_CASE_SMALL_WORDS

#: Keywords that introduce a numbered division, matched case-insensitively.
#: Deliberately the same vocabulary HEADING_PATTERNS already knows, since the
#: question here is not "what words divide a book" but "which of their
#: numbers form a sequence."
SEQUENCE_KEYWORDS = (
    "CHAPTER",
    "BOOK",
    "PART",
    "VOLUME",
    "ACT",
    "SCENE",
    "LETTER",
    "STAVE",
    "SECTION",
    "DIVISION",
    "CANTO",
    "SURA",
)

#: The minimum number of hits, whether clustered together or scattered
#: through the book, below which a template is noise rather than structure.
#: Also the minimum cluster size read as a contents listing rather than a
#: lone real heading -- two or three lines with ascending numbers happen by
#: chance; real spines and contents lists run much longer than this in
#: every book measured.
MIN_RUN_LENGTH = 5

#: The numeral must be followed by a separator-and-subtitle or by the end of
#: the line, not just a word boundary. A bare \b after the numeral does not
#: enforce that: "one" in "Chapter one was the longest of them all." also
#: ends at a word boundary (the space before "was"), so a \b-only pattern
#: promotes ordinary sentences as readily as real headings like
#: "Chapter 93. The Castaway." This is the same discipline
#: HEADING_PATTERNS' own word-numeral rule uses, in gutenberg_kg.headings.
_KEYWORD_PATTERN = re.compile(
    r"^(" + "|".join(SEQUENCE_KEYWORDS) + r")\.?\s+([A-Za-z][A-Za-z-]*|\d+)"
    r"(?:\s*[-—:.]\s*.*)?$",
    re.IGNORECASE,
)
#: A bare numeral needs its own separator discipline, and a period is it: a
#: roman numeral alone with nothing after ("I.") is unambiguous, and so is
#: one followed by a subtitle ("I. The Shores of Purgatory."). Without the
#: period this collides with the pronoun "I" and ordinary initials. Found by
#: validating this module against Longfellow's Divine Comedy: Purgatorio and
#: Paradiso's contents entries are "I. The Shores of Purgatory...", not
#: "Canto I." like Inferno's -- the same document uses two shapes for the
#: same thing, and a period-only bare-roman template with no subtitle
#: allowed caught neither.
_BARE_ROMAN_PATTERN = re.compile(r"^([IVXLCDM]{1,6})\.(?:\s+.*)?$")

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

_ONES = {
    name: value
    for value, name in enumerate(
        [
            "ZERO",
            "ONE",
            "TWO",
            "THREE",
            "FOUR",
            "FIVE",
            "SIX",
            "SEVEN",
            "EIGHT",
            "NINE",
            "TEN",
            "ELEVEN",
            "TWELVE",
            "THIRTEEN",
            "FOURTEEN",
            "FIFTEEN",
            "SIXTEEN",
            "SEVENTEEN",
            "EIGHTEEN",
            "NINETEEN",
        ]
    )
}
_TENS = {
    "TWENTY": 20,
    "THIRTY": 30,
    "FORTY": 40,
    "FIFTY": 50,
    "SIXTY": 60,
    "SEVENTY": 70,
    "EIGHTY": 80,
    "NINETY": 90,
}


def _roman_value(token: str) -> int | None:
    """Parse a roman numeral, or None if *token* is not one.

    :param token: A candidate numeral, e.g. ``"XIV"``.
    :returns: The integer value, or None.
    """
    token = token.upper()
    if not token or any(ch not in _ROMAN_VALUES for ch in token):
        return None
    total = 0
    prev = 0
    for ch in reversed(token):
        value = _ROMAN_VALUES[ch]
        total += -value if value < prev else value
        prev = max(prev, value)
    return total if total > 0 else None


def _word_value(token: str) -> int | None:
    """Parse a spelled-out numeral like ``"Twenty-Three"``, or None.

    :param token: A candidate numeral, hyphen or space separated.
    :returns: The integer value, or None.
    """
    words = token.upper().replace("-", " ").split()
    if not words or any(w not in _ONES and w not in _TENS for w in words):
        return None
    if len(words) == 1:
        return _ONES.get(words[0], _TENS.get(words[0]))
    if len(words) == 2 and words[0] in _TENS and words[1] in _ONES:
        return _TENS[words[0]] + _ONES[words[1]]
    return None


def numeral_value(token: str) -> int | None:
    """Parse *token* as digits, a roman numeral, or a spelled-out word.

    :param token: A candidate numeral, e.g. ``"14"``, ``"XIV"``, ``"Fourteen"``.
    :returns: The integer value, or None if none of the three forms match.
    """
    token = token.strip()
    if token.isdigit():
        return int(token)
    return _roman_value(token) if _roman_value(token) is not None else _word_value(token)


@dataclass(frozen=True)
class Hit:
    """One line matching a sequence template."""

    line: int
    number: int


@dataclass(frozen=True)
class Cluster:
    """A group of same-template hits close enough together to be one
    structural region: either a contents listing, or (for most of a book)
    a single isolated real heading standing alone as its own cluster of
    one."""

    template: str
    hits: tuple[Hit, ...]

    @property
    def start(self) -> int:
        return self.hits[0].line

    @property
    def end(self) -> int:
        return self.hits[-1].line

    @property
    def span(self) -> int:
        return self.end - self.start + 1

    @property
    def density(self) -> float:
        return len(self.hits) / self.span if self.span else 0.0

    @property
    def is_contents_shaped(self) -> bool:
        """Whether this cluster has enough members packed closely enough to
        be read as a contents listing rather than a lone real heading."""
        return len(self.hits) >= MIN_RUN_LENGTH


def find_candidates(lines: list[str]) -> dict[str, list[Hit]]:
    """Collect every numbered-heading-shaped line, grouped by template.

    :param lines: A book's lines, split on ``\\n``.
    :returns: Template name (a keyword, or ``"ROMAN"`` for a bare numeral)
        to the hits found for it, in line order.
    """
    by_template: dict[str, list[Hit]] = {}
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or len(stripped) > 80:
            continue
        m = _KEYWORD_PATTERN.match(stripped)
        if m:
            number = numeral_value(m.group(2))
            if number is not None:
                by_template.setdefault(m.group(1).upper(), []).append(Hit(i, number))
            continue
        m = _BARE_ROMAN_PATTERN.match(stripped)
        if m:
            number = _roman_value(m.group(1))
            if number is not None:
                by_template.setdefault("ROMAN", []).append(Hit(i, number))
    return by_template


#: How many lines apart two hits of the same template may be and still
#: belong to one cluster. Chosen so a contents listing's occasional
#: divider ("BOOK SECOND", a blank line either side) doesn't break it, while
#: two real chapters -- which are separated by a whole scene, not a line
#: count -- essentially never end up this close.
_CLUSTER_GAP = 20

#: How close two contents-shaped regions found under *different* templates
#: may be and still be one listing. Longfellow's Divine Comedy lists
#: Inferno's contents as ``CANTO I..XXXIV`` and Purgatorio's, five lines
#: later, as a bare ``I..XXXIII`` -- two templates, one table of contents.
#: Only regions that have each independently cleared MIN_RUN_LENGTH are
#: combined this way (see contents_regions); it never absorbs a lone hit.
_CONTENTS_MERGE_GAP = 100

#: How many prose-shaped lines between two hits mean real body text rather
#: than a wrapped listing entry. A contents entry that runs onto a second
#: line can look like one line of prose -- Innocents Abroad's descriptive
#: entries ("--The Mystery of 'Ship Time'--The Denizens of the Deep--'Land
#: Hoh'") put at most one or two such lines between consecutive hits,
#: measured across every gap in its listing. A chapter, even a very short
#: one, is many. Testing for *any* prose line is what fragmented that
#: listing into five pieces; counting separates the two cases cleanly.
_PROSE_BREAK = 3


def _is_prose_line(line: str) -> bool:
    """Whether a line reads as running narrative rather than a listing entry.

    Judged by case, not punctuation. An earlier version required a
    sentence-ending mark, which is the wrong test: wrapped prose ends
    mid-sentence by construction, so Emma's opening paragraph --

        Emma Woodhouse, handsome, clever, and rich, with a comfortable home an
        happy disposition, seemed to unite some of the best blessings of

    -- counted as no prose at all, and the body's ``CHAPTER I`` two lines
    above it was deleted as the last entry of the contents.

    Nor is a plain lowercase majority enough: a descriptive contents entry
    like Twain's "Popular Talk of the Excursion--Programme of the Trip--Duly
    Ticketed for the Excursion" is half lowercase purely on its articles and
    prepositions. What actually separates the two is the *content* words.
    In Title Case every noun and verb is capitalised; in prose they are
    not. The small words are set aside using the same list
    :mod:`gutenberg_kg.headings` uses to recognise a Title Case line.

    :param line: A raw line.
    :returns: True if it is long and most of its content words start
        lowercase.
    """
    stripped = line.strip()
    if len(stripped) <= 60:
        return False
    content = [
        w
        for w in (t.strip("“”\"'(),.;:") for t in stripped.split())
        if w and w[0].isalpha() and w.lower() not in _TITLE_CASE_SMALL_WORDS
    ]
    return len(content) >= 4 and sum(1 for w in content if w[0].islower()) * 2 > len(content)


def _prose_lines_between(lines: list[str], start: int, end: int) -> int:
    """How many real-prose-shaped lines sit strictly between two positions.

    :param lines: A book's lines, split on ``\\n``.
    :param start: Line index to look after (exclusive).
    :param end: Line index to stop before (exclusive).
    :returns: The count of prose lines in that range (see :func:`_is_prose_line`).
    """
    return sum(1 for line in lines[start + 1 : end] if _is_prose_line(line))


def cluster_hits(lines: list[str], hits: list[Hit], template: str) -> list[Cluster]:
    """Group hits close enough together, with nothing but listing between
    them, into clusters.

    Ignores each hit's number entirely -- only line position and what sits
    between matters. This is what lets a multi-volume contents listing
    (chapter numbering restarting at I for each volume, as in Emma or the
    365-chapter, 5-volume Les Miserables) collapse into one cluster instead
    of shattering into one short fragment per volume the way a
    monotonic-sequence rule would.

    A cluster's trailing hit is then re-examined: if a chapter's worth of
    prose follows it, it is the body's first heading sitting a few blank
    lines after the listing's last entry, not the entry itself. Emma's
    contents end with ``CHAPTER XIX`` of Volume III; two lines later comes
    the body's ``CHAPTER I``, and two lines after that "Emma Woodhouse,
    handsome, clever, and rich". Nothing between the two headings tells
    them apart -- only what comes *after* the second does. Such a hit is
    split off as a cluster of its own, and the check repeats in case the
    new last hit is one too.

    "After" means up to the next hit of the same template, not a fixed
    distance. A listing entry whose next entry is one line away has nothing
    after it, whatever lies twenty lines further on; scanning a fixed
    window past the next hit read the body's prose back onto the last
    dozen listing entries and trimmed them all.

    Prose after a trailing hit is necessary but not sufficient: the
    listing's own last entry is followed by prose too whenever a preface or
    transcriber's note begins within reach of it, as Moby Dick's does. What
    the two have in common is nothing local. What separates them is the
    number: the body's first heading *restarts* the sequence (Emma's
    contents end at Volume III's ``CHAPTER XIX``; the body opens at
    ``CHAPTER I``), while the listing's last entry continues it (``CHAPTER
    134``, then ``135``). So a trailing hit is only split off if its number
    does not exceed the one before it.

    :param lines: A book's lines, split on ``\\n``.
    :param hits: Hits for one template, in line order.
    :param template: The template name the hits were found under.
    :returns: Clusters covering every hit, in line order.
    """
    if not hits:
        return []
    by_line = sorted(hits, key=lambda h: h.line)
    # For each hit, how far "what follows it" extends: to the next hit, or
    # one cluster gap on if there is none close enough to bound it.
    horizons = [
        min(nxt.line, cur.line + _CLUSTER_GAP + 1) for cur, nxt in zip(by_line, by_line[1:])
    ]
    horizons.append(by_line[-1].line + _CLUSTER_GAP + 1)
    followed_by_prose = [
        _prose_lines_between(lines, hit.line, horizon) >= _PROSE_BREAK
        for hit, horizon in zip(by_line, horizons)
    ]

    groups: list[list[int]] = [[0]]
    for i in range(1, len(by_line)):
        prev, cur = by_line[i - 1], by_line[i]
        close = cur.line - prev.line <= _CLUSTER_GAP
        if close and _prose_lines_between(lines, prev.line, cur.line) < _PROSE_BREAK:
            groups[-1].append(i)
        else:
            groups.append([i])

    result: list[list[int]] = []
    for group in groups:
        split_off: list[int] = []
        while (
            len(group) > 1
            and followed_by_prose[group[-1]]
            and by_line[group[-1]].number <= by_line[group[-2]].number
        ):
            split_off.append(group.pop())
        result.append(group)
        result.extend([i] for i in reversed(split_off))
    return [Cluster(template=template, hits=tuple(by_line[i] for i in g)) for g in result]


def profile(lines: list[str]) -> dict[str, list[Cluster]]:
    """Find every hit cluster in a book, by template.

    A template is only reported if it has at least :data:`MIN_RUN_LENGTH`
    hits *somewhere* in the document (clustered or not) -- a single
    coincidental match, like "Volume" catching the leading letter of an
    unrelated word, is exactly the noise this threshold exists to drop.

    :param lines: A book's lines, split on ``\\n``.
    :returns: Template name to its clusters, in line order.
    """
    result: dict[str, list[Cluster]] = {}
    for template, hits in find_candidates(lines).items():
        if len(hits) < MIN_RUN_LENGTH:
            continue
        result[template] = cluster_hits(lines, hits, template)
    return result


def contents_regions(lines: list[str]) -> list[tuple[int, int]]:
    """Every contents-shaped region found, across all templates.

    Regions from *different* templates within :data:`_CONTENTS_MERGE_GAP`
    of each other are combined -- Longfellow's Divine Comedy lists
    Inferno's contents as ``CANTO I..XXXIV`` and Purgatorio's a few lines
    later as a bare ``I..XXXIII``, five lines apart and each its own
    template, but unmistakably one contents listing. Only regions that are
    already contents-shaped on their own take part, so this can never pull
    a lone real heading into the deleted range.

    :param lines: A book's lines, split on ``\\n``.
    :returns: ``(start, end)`` line ranges (inclusive), merged where they
        are close, sorted by position.
    """
    spans = sorted(
        (c.start, c.end)
        for clusters in profile(lines).values()
        for c in clusters
        if c.is_contents_shaped
    )
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start - merged[-1][1] <= _CONTENTS_MERGE_GAP:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def spine_hits(lines: list[str]) -> dict[str, list[Hit]]:
    """The hits that are real body headings: every hit belonging to a
    cluster too small to be a contents listing.

    :param lines: A book's lines, split on ``\\n``.
    :returns: Template name to its non-contents hits, in line order.
    """
    result: dict[str, list[Hit]] = {}
    for template, clusters in profile(lines).items():
        hits = [h for c in clusters if not c.is_contents_shaped for h in c.hits]
        if hits:
            result[template] = sorted(hits, key=lambda h: h.line)
    return result
