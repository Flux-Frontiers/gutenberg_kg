"""parser.py — Parse Project Gutenberg diary markdown into dated PSV entries.

Handles the formatting used in Pepys' complete diary (Gutenberg #4200) and
similar diary texts:

- ALL-CAPS ``MONTH YEAR`` or ``MONTH YEAR-YEAR`` section headers anchor year context.
  Dual-year headers (e.g. ``JANUARY 1659-1660``) use the *later* year.
- Full-month dated entries: ``January 1st.``, ``January 1st,``, ``April 1st, 1661.``
- Abbreviated-month entries: ``Jan. 1st (Lord's day).``
- Continuation entries: ``2nd.``, ``3rd (Lord's day).`` — same month as context.
- Editorial footnotes in ``[square brackets]`` are stripped from entry text.

Output: pipe-delimited lines compatible with ``DiaryTransformer``::

    TIMESTAMP | diary | prose | CONTENT
"""

from __future__ import annotations

import re
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

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# ALL-CAPS section header: "JANUARY 1659-1660" or "APRIL 1660"
_SECTION_RE = re.compile(r"^([A-Z]+)\s+(\d{4})(?:-(\d{4}))?$")

# Full-month dated entry: "January 1st." / "January 1st," / "April 1st, 1661."
# After the ordinal we REQUIRE either [.,] (period/comma) or \s+(?=\() (space
# before an open paren, e.g. "January 1st (Lord's day).").  This prevents
# false-positive matches on editorial prose like "March 25th to the following…"
# Groups: (1) month-name  (2) day  (3) rest
_FULL_DATE_RE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\.?\s+(\d{1,2})(?:st|nd|rd|th)"
    r"(?:[.,]\s*|\s+(?=\())"  # punctuation OR space-before-paren
    r"(?:\d{4}[.,]?\s*)?"  # swallow optional embedded year (no capture)
    r"(?:\([^)]*\))?[.,]?\s*(.*)",  # optional parenthetical, then rest
    re.DOTALL | re.IGNORECASE,
)

# Abbreviated-month entry: "Jan. 1st (Lord's day)."
# Same strict punctuation requirement as _FULL_DATE_RE.
# Groups: (1) abbr-month  (2) day  (3) rest
_ABBR_DATE_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept?|Oct|Nov|Dec)\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)"
    r"(?:[.,]\s*|\s+(?=\())"  # punctuation OR space-before-paren
    r"(?:\([^)]*\))?[.,]?\s*(.*)",
    re.DOTALL | re.IGNORECASE,
)

# Continuation entry: "2nd." or "11th (Lord's day)." at line start, 1-2 digits only
# Require a literal period immediately after the ordinal suffix to avoid false positives.
_CONT_DATE_RE = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)\.\s*(?:\([^)]*\))?\.?\s*(.*)",
    re.DOTALL,
)

# Footnote paragraph: entire paragraph is an editorial note in [brackets]
# We strip these from accumulated text after collection.
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
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_footnotes(text: str) -> str:
    """Remove editorial footnotes in [square brackets] from text."""
    return _FOOTNOTE_INLINE_RE.sub(" ", text)


def _clean(text: str) -> str:
    """Strip footnotes and normalize whitespace."""
    text = _strip_footnotes(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    return text.strip()


def _month_num(name: str) -> int | None:
    """Return integer month number for a month name/abbreviation, or None."""
    return _MONTH_MAP.get(name.lower().rstrip("."))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse(md_path: Path) -> Iterator[ParsedEntry]:
    """Parse a Gutenberg diary markdown file, yielding dated entries.

    Skips the preface automatically — diary content begins at the first
    ALL-CAPS ``MONTH YEAR`` section header.

    :param md_path: Path to the downloaded Gutenberg markdown file.
    :yields: :class:`ParsedEntry` objects in chronological order.
    """
    lines = md_path.read_text(encoding="utf-8").splitlines()

    # ── state ──────────────────────────────────────────────────────────────
    in_diary = False  # True after first MONTH YEAR header
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

    bracket_depth = 0  # tracks open [..] across lines to skip footnote content

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()

        # Track [..] nesting so we don't parse dates inside editorial footnotes.
        # Blank lines reset depth: Pepys uses blank lines to separate entry prose
        # from editorial footnote paragraphs, so after any blank line we know we're
        # back at paragraph-start context (depth 0).
        if not line:
            bracket_depth = 0
        depth_at_start = bracket_depth
        bracket_depth = max(0, bracket_depth + line.count("[") - line.count("]"))

        # ── ALL-CAPS section header → update year/month context ────────────
        # Only recognised when not inside a footnote block.
        m = _SECTION_RE.match(line) if depth_at_start == 0 else None
        if m:
            month_num = _month_num(m.group(1))
            if month_num:
                if in_diary and current_day:
                    entry = _flush()
                    if entry:
                        yield entry
                    current_lines = []
                    current_day = 0

                in_diary = True
                current_month = month_num
                # Dual-year header (e.g. JANUARY 1659-1660) → take later year
                current_year = int(m.group(3)) if m.group(3) else int(m.group(2))
            continue

        if not in_diary:
            continue

        # ── Date matching: only when we're not inside a footnote block ──────
        # ── Full-month date: "January 1st." ────────────────────────────────
        m = _FULL_DATE_RE.match(line) if depth_at_start == 0 else None
        if m:
            entry = _flush()
            if entry:
                yield entry

            num = _month_num(m.group(1))
            if num:
                current_month = num
            current_day = int(m.group(2))
            rest = m.group(3) or ""
            current_lines = [rest] if rest.strip() else []
            current_start = lineno
            continue

        # ── Abbreviated-month date: "Jan. 1st (Lord's day)." ───────────────
        m = _ABBR_DATE_RE.match(line) if depth_at_start == 0 else None
        if m:
            entry = _flush()
            if entry:
                yield entry

            num = _month_num(m.group(1))
            if num:
                current_month = num
            current_day = int(m.group(2))
            rest = m.group(3) or ""
            current_lines = [rest] if rest.strip() else []
            current_start = lineno
            continue

        # ── Continuation date: "2nd." ───────────────────────────────────────
        if current_month and current_year and depth_at_start == 0:
            m = _CONT_DATE_RE.match(line)
            if m:
                day = int(m.group(1))
                if 1 <= day <= 31:
                    entry = _flush()
                    if entry:
                        yield entry

                    current_day = day
                    rest = m.group(2) or ""
                    current_lines = [rest] if rest.strip() else []
                    current_start = lineno
                    continue

        # ── Accumulate into current entry ───────────────────────────────────
        if current_day > 0:
            current_lines.append(raw_line)

    # Flush the final entry
    if in_diary and current_day:
        entry = _flush()
        if entry:
            yield entry


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
            content = entry.content.replace("|", "—")  # em-dash for pipe
            fh.write(f"{ts} | diary | prose | {content}\n")
            count += 1
    return count
