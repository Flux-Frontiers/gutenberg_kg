"""Structural profiling: find numbered sequences in a book's raw lines.

Step 1 of ``analysis/STRUCTURAL_PARSER_PLAN.md``. This module is read-only:
it reports where numbered sequences (``CHAPTER 1..135``, ``CANTO I..XXXIV``,
...) occur in a book and at what density, so a table of contents -- the same
sequence printed at far higher density than the body -- can be told apart
from the body itself without counting blank lines.

Measured on the real corpus, a contents list and its body are the same
sequence two to three orders of magnitude apart in density::

    Moby Dick   CHAPTER 1..135   lines     14-285    density 0.496   (contents)
                CHAPTER 1..135   lines   812-21446   density 0.007   (body)

Nothing here changes what ``text_to_markdown`` emits; that is a later step
once this signal has been read against the whole corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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

#: A minimum run length below which a sequence is noise, not structure. Two
#: or three lines with ascending numbers happen by chance; real spines and
#: contents lists run much longer than this in every book measured.
MIN_RUN_LENGTH = 5

#: How many times denser a run must be than its sibling covering the same
#: number range before the denser one is read as a contents list rather than
#: a second, coincidentally-numbered spine. The measured corpus separations
#: were 70x-250x; this is set an order of magnitude below the weakest of
#: those, not against the strongest, so it doesn't need retuning per book.
CONTENTS_DENSITY_RATIO = 8.0

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
class Run:
    """A maximal non-decreasing run of hits for one template."""

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
    def first_number(self) -> int:
        return self.hits[0].number

    @property
    def last_number(self) -> int:
        return self.hits[-1].number


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


def split_runs(template: str, hits: list[Hit]) -> list[Run]:
    """Split *hits* into maximal runs whose numbers never decrease.

    A single sequence read twice (once as a contents list, once as the body)
    is two separate runs even though they share numbering, because a large
    gap in line position always intervenes; this only ever breaks a run on
    an actual decrease, which is what tells a restart (a new contents entry
    run, or a second `CHAPTER I` opening a new volume) from a continuation.

    :param template: The template name the hits were found under.
    :param hits: Hits for that template, in line order.
    :returns: Runs of at least one hit each.
    """
    if not hits:
        return []
    runs: list[list[Hit]] = [[hits[0]]]
    for prev, cur in zip(hits, hits[1:]):
        if cur.number < prev.number:
            runs.append([])
        runs[-1].append(cur)
    return [Run(template=template, hits=tuple(r)) for r in runs]


def profile(lines: list[str]) -> dict[str, list[Run]]:
    """Find every sequence run in a book, by template.

    :param lines: A book's lines, split on ``\\n``.
    :returns: Template name to its runs, longest first, restricted to runs
        meeting :data:`MIN_RUN_LENGTH`.
    """
    result: dict[str, list[Run]] = {}
    for template, hits in find_candidates(lines).items():
        runs = [r for r in split_runs(template, hits) if len(r.hits) >= MIN_RUN_LENGTH]
        if runs:
            result[template] = sorted(runs, key=lambda r: len(r.hits), reverse=True)
    return result


@dataclass(frozen=True)
class Classification:
    """A template's best guess at which of its runs is which."""

    template: str
    spine: Run | None
    contents: Run | None


def classify(runs: list[Run]) -> Classification | None:
    """Pick the body spine and the contents list out of one template's runs.

    Two runs are a spine/contents pair when their number ranges overlap and
    one is much denser than the other -- the signal this module exists to
    use. A template with only one qualifying run is a spine with no
    contents list found (or vice versa); either is reported as such rather
    than guessed at.

    :param runs: Runs for one template, as returned by :func:`profile`.
    :returns: None if *runs* is empty.
    """
    if not runs:
        return None
    template = runs[0].template
    by_density = sorted(runs, key=lambda r: r.density, reverse=True)
    densest, sparsest = by_density[0], by_density[-1]
    if (
        len(runs) >= 2
        and densest is not sparsest
        and densest.density >= sparsest.density * CONTENTS_DENSITY_RATIO
        and densest.first_number <= sparsest.last_number
        and sparsest.first_number <= densest.last_number
    ):
        return Classification(template=template, spine=sparsest, contents=densest)
    # No density split found: the longest run is the best guess at the
    # spine, and there is no contents list among the qualifying runs.
    longest = max(runs, key=lambda r: len(r.hits))
    return Classification(template=template, spine=longest, contents=None)
