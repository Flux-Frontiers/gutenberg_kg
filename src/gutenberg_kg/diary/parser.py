"""parser.py — Parse Project Gutenberg diary markdown into dated PSV entries.

Supports multiple diary date formats via pluggable parser subclasses:

- ``pepys``   — ALL-CAPS MONTH YEAR section headers + ``Month Nth.`` entries
                (Pepys, any standard Gutenberg diary)
- ``evelyn``  — Day-first inline year: ``29th December, 1659.``
- ``boswell`` — Weekday prefix, no inline year: ``Sunday, 15th August``
                (year anchored at construction time, default 1773)

Use :func:`get_parser` to select a parser by format name, or instantiate
directly.  The module-level :func:`parse` and :func:`write_psv` use the
Pepys format for backward compatibility.

Output: pipe-delimited lines compatible with ``DiaryTransformer``::

    TIMESTAMP | diary | prose | CONTENT
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Month name → integer
# ---------------------------------------------------------------------------

_MONTH_MAP: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Pepys: ALL-CAPS section header "JANUARY 1659-1660" or "APRIL 1660"
_SECTION_RE = re.compile(r"^([A-Z]+)\s+(\d{4})(?:-(\d{4}))?$")

# Pepys: full-month entry "January 1st." / "April 1st, 1661."
_FULL_DATE_RE = re.compile(
    rf"^({_MONTH_NAMES})"
    r"\.?\s+(\d{{1,2}})(?:st|nd|rd|th)"
    r"(?:[.,]\s*|\s+(?=\())"
    r"(?:\d{{4}}[.,]?\s*)?"
    r"(?:\([^)]*\))?[.,]?\s*(.*)",
    re.DOTALL | re.IGNORECASE,
)

# Pepys: abbreviated-month entry "Jan. 1st (Lord's day)."
_ABBR_DATE_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept?|Oct|Nov|Dec)\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)"
    r"(?:[.,]\s*|\s+(?=\())"
    r"(?:\([^)]*\))?[.,]?\s*(.*)",
    re.DOTALL | re.IGNORECASE,
)

# Pepys: continuation entry "2nd." or "11th (Lord's day)."
_CONT_DATE_RE = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)\.\s*(?:\([^)]*\))?\.?\s*(.*)",
    re.DOTALL,
)

# Evelyn: day-first with inline year "29th December, 1659." / "3d February, 1660."
# Note: Evelyn uses "3d" / "22d" for rd — included in suffix alternation.
_DAY_FIRST_RE = re.compile(
    rf"^(\d{{1,2}})(?:st|nd|rd|th|d)\.?\s+({_MONTH_NAMES})"
    r"[,.]?\s+(\d{4})(?:-\d{2,4})?[.,]?\s*(.*)",
    re.DOTALL | re.IGNORECASE,
)

# Boswell: weekday-prefixed, no year "Sunday, 15th August"
_WEEKDAY_RE = re.compile(
    rf"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[.,]?\s+"
    rf"(\d{{1,2}})(?:st|nd|rd|th|d)\.?\s+({_MONTH_NAMES})"
    r"[.,]?\s*(.*)",
    re.DOTALL | re.IGNORECASE,
)

# Shared: strip editorial footnotes in [brackets]
_FOOTNOTE_INLINE_RE = re.compile(r"\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]", re.DOTALL)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ParsedEntry:
    """One dated diary entry extracted from a Gutenberg diary markdown."""

    timestamp: datetime
    content: str
    source_line: int


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _strip_footnotes(text: str) -> str:
    return _FOOTNOTE_INLINE_RE.sub(" ", text)


def _clean(text: str) -> str:
    text = _strip_footnotes(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    return text.strip()


def _month_num(name: str) -> int | None:
    return _MONTH_MAP.get(name.lower().rstrip("."))


# ---------------------------------------------------------------------------
# Base parser
# ---------------------------------------------------------------------------


class BaseDiaryParser(ABC):
    """State-machine base for Gutenberg diary parsing.

    Subclasses implement :meth:`_match_section` and :meth:`_match_date`.
    Set ``requires_section_header = True`` (Pepys) to skip date matching
    before the first section header fires; leave ``False`` (Evelyn, Boswell)
    to start accumulating from the first matched date line.
    """

    requires_section_header: bool = False

    def parse(self, md_path: Path) -> Iterator[ParsedEntry]:
        """Yield dated entries from a Gutenberg diary markdown file.

        :param md_path: Path to the downloaded markdown.
        :yields: :class:`ParsedEntry` in chronological order.
        """
        lines = md_path.read_text(encoding="utf-8").splitlines()

        in_diary = False
        current_year = 0
        current_month = 0
        current_day = 0
        current_lines: list[str] = []
        current_start = 0

        def _flush() -> ParsedEntry | None:
            if not current_lines or current_day == 0:
                return None
            content = _clean("\n".join(current_lines))
            if len(content) < 10:
                return None
            try:
                ts = datetime(current_year, current_month, current_day)
            except ValueError:
                return None
            return ParsedEntry(timestamp=ts, content=content, source_line=current_start)

        bracket_depth = 0

        for lineno, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()

            if not line:
                bracket_depth = 0
            depth_at_start = bracket_depth
            bracket_depth = max(0, bracket_depth + line.count("[") - line.count("]"))

            # Section header (e.g. JANUARY 1660)
            if depth_at_start == 0:
                section = self._match_section(line)
                if section is not None:
                    month, year = section
                    if in_diary and current_day:
                        entry = _flush()
                        if entry:
                            yield entry
                        current_lines = []
                        current_day = 0
                    in_diary = True
                    current_month = month
                    current_year = year
                    continue

            # For Pepys-style parsers: skip preamble before first section header
            if not in_diary and self.requires_section_header:
                continue

            # Date matching
            if depth_at_start == 0:
                result = self._match_date(line, current_month, current_year)
                if result is not None:
                    day, month, year, rest = result
                    entry = _flush()
                    if entry:
                        yield entry
                    in_diary = True
                    current_day = day
                    current_month = month
                    current_year = year
                    current_lines = [rest] if rest.strip() else []
                    current_start = lineno
                    continue

            if in_diary and current_day > 0:
                current_lines.append(raw_line)

        if in_diary and current_day:
            entry = _flush()
            if entry:
                yield entry

    @abstractmethod
    def _match_section(self, line: str) -> tuple[int, int] | None:
        """Return ``(month, year)`` if *line* is a section header, else ``None``."""

    @abstractmethod
    def _match_date(
        self, line: str, current_month: int, current_year: int
    ) -> tuple[int, int, int, str] | None:
        """Return ``(day, month, year, rest)`` if *line* opens a dated entry."""


# ---------------------------------------------------------------------------
# Format-specific parsers
# ---------------------------------------------------------------------------


class PepysParser(BaseDiaryParser):
    """Pepys format: ALL-CAPS MONTH YEAR headers + ``Month Nth.`` entries."""

    requires_section_header = True

    def _match_section(self, line: str) -> tuple[int, int] | None:
        m = _SECTION_RE.match(line)
        if not m:
            return None
        month = _month_num(m.group(1))
        if not month:
            return None
        year = int(m.group(3)) if m.group(3) else int(m.group(2))
        return month, year

    def _match_date(
        self, line: str, current_month: int, current_year: int
    ) -> tuple[int, int, int, str] | None:
        m = _FULL_DATE_RE.match(line)
        if m:
            month = _month_num(m.group(1)) or current_month
            return int(m.group(2)), month, current_year, m.group(3) or ""

        m = _ABBR_DATE_RE.match(line)
        if m:
            month = _month_num(m.group(1)) or current_month
            return int(m.group(2)), month, current_year, m.group(3) or ""

        if current_month and current_year:
            m = _CONT_DATE_RE.match(line)
            if m:
                day = int(m.group(1))
                if 1 <= day <= 31:
                    return day, current_month, current_year, m.group(2) or ""

        return None


class EvelynParser(BaseDiaryParser):
    """Evelyn format: day-first with inline year — ``29th December, 1659.``

    Each entry carries its own year; no section headers.  Handles the older
    ordinal ``d`` suffix used by Evelyn (``3d``, ``22d``).
    """

    def _match_section(self, line: str) -> tuple[int, int] | None:
        return None

    def _match_date(
        self, line: str, current_month: int, current_year: int
    ) -> tuple[int, int, int, str] | None:
        m = _DAY_FIRST_RE.match(line)
        if not m:
            return None
        month = _month_num(m.group(2))
        if not month:
            return None
        return int(m.group(1)), month, int(m.group(3)), m.group(4) or ""


class BoswellParser(BaseDiaryParser):
    """Boswell format: ``Sunday, 15th August`` — weekday prefix, no inline year.

    The tour (1773) spans a single year, supplied via ``anchor_year``.
    """

    def __init__(self, anchor_year: int = 1773) -> None:
        self.anchor_year = anchor_year

    def _match_section(self, line: str) -> tuple[int, int] | None:
        return None

    def _match_date(
        self, line: str, current_month: int, current_year: int
    ) -> tuple[int, int, int, str] | None:
        m = _WEEKDAY_RE.match(line)
        if not m:
            return None
        month = _month_num(m.group(2))
        if not month:
            return None
        year = current_year if current_year else self.anchor_year
        return int(m.group(1)), month, year, m.group(3) or ""


# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

_PARSERS: dict[str, BaseDiaryParser] = {
    "pepys": PepysParser(),
    "evelyn": EvelynParser(),
    "boswell": BoswellParser(anchor_year=1773),
}


def get_parser(fmt: str) -> BaseDiaryParser:
    """Return the parser for *fmt* (default: ``pepys`` if unknown).

    :param fmt: Format name — one of ``"pepys"``, ``"evelyn"``, ``"boswell"``.
    :return: Shared :class:`BaseDiaryParser` instance.
    """
    return _PARSERS.get(fmt.lower().strip(), _PARSERS["pepys"])


# ---------------------------------------------------------------------------
# Backward-compatible module-level API
# ---------------------------------------------------------------------------


def parse(md_path: Path) -> Iterator[ParsedEntry]:
    """Parse using the Pepys format (default).  See :func:`get_parser` for others."""
    return PepysParser().parse(md_path)


def write_psv(entries: Iterator[ParsedEntry], out_path: Path) -> int:
    """Write parsed entries as a pipe-delimited file for DiaryTransformer.

    Format per line::

        TIMESTAMP | diary | prose | CONTENT

    Pipe characters within content are replaced with em-dashes.

    :param entries: Iterator of :class:`ParsedEntry` objects.
    :param out_path: Destination ``.psv`` file path.
    :return: Number of lines written.
    """
    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            ts = entry.timestamp.strftime("%Y-%m-%dT%H:%M:%S")
            content = entry.content.replace("|", "—")
            fh.write(f"{ts} | diary | prose | {content}\n")
            count += 1
    return count
