"""Tests for the Gutenberg diary parsers (gutenberg_kg.diary.parser).

Covers the three date formats (pepys / evelyn / boswell), the parser registry,
and PSV serialisation.  Inputs are small synthetic snippets so the tests stay
fast and independent of the downloaded corpus.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from gutenberg_kg.diary import get_parser, parse, write_psv
from gutenberg_kg.diary.parser import BoswellParser, EvelynParser, PepysParser


def _write(tmp_path: Path, text: str) -> Path:
    md = tmp_path / "diary.md"
    md.write_text(text, encoding="utf-8")
    return md


# ---------------------------------------------------------------------------
# Pepys format
# ---------------------------------------------------------------------------


def test_pepys_section_header_and_continuation(tmp_path):
    """Dual-year header sets the later year; continuation entries inherit it.

    Pepys uses abbreviated months with an optional parenthetical
    (``Jan. 1st (Lord's day).``), then day-only continuations (``2nd.``).
    """
    md = _write(
        tmp_path,
        "Front matter that should be skipped before the first section.\n\n"
        "JANUARY 1659-1660\n\n"
        "Jan. 1st (Lord's day). This morning I rose and put on my suit with skirts.\n\n"
        "2nd. The second day continued with much business at the office today.\n",
    )
    entries = list(PepysParser().parse(md))
    assert len(entries) == 2
    assert entries[0].timestamp == datetime(1660, 1, 1)
    assert entries[1].timestamp == datetime(1660, 1, 2)
    assert entries[0].content.startswith("This morning I rose")


def test_pepys_requires_section_header():
    """Pepys parser ignores date lines before any section header."""
    assert PepysParser().requires_section_header is True


def test_pepys_strips_bracketed_footnotes(tmp_path):
    """Editorial [footnotes] are removed from entry content."""
    md = _write(
        tmp_path,
        "APRIL 1660\n\nApr. 1st. We sailed onward [this is an editorial footnote] to the sea.\n",
    )
    entries = list(PepysParser().parse(md))
    assert len(entries) == 1
    assert "editorial footnote" not in entries[0].content
    assert "to the sea" in entries[0].content


# ---------------------------------------------------------------------------
# Evelyn format
# ---------------------------------------------------------------------------


def test_evelyn_day_first_inline_year(tmp_path):
    """Evelyn entries carry their own inline year; no section headers."""
    md = _write(
        tmp_path,
        "21st October, 1632. My eldest sister was married to Edward Darcy, Esq.\n\n"
        "3d February, 1660. Another entry written with the older ordinal suffix.\n",
    )
    entries = list(EvelynParser().parse(md))
    assert len(entries) == 2
    assert entries[0].timestamp == datetime(1632, 10, 21)
    assert entries[1].timestamp == datetime(1660, 2, 3)


# ---------------------------------------------------------------------------
# Boswell format
# ---------------------------------------------------------------------------


def test_boswell_weekday_prefix_anchor_year(tmp_path):
    """Boswell weekday-prefixed dates use the construction-time anchor year."""
    md = _write(
        tmp_path,
        "Sunday, 15th August. Mr Scott came to breakfast with Dr Johnson today.\n\n"
        "Monday, 16th August. We set out early upon our tour of the Hebrides.\n",
    )
    entries = list(BoswellParser(anchor_year=1773).parse(md))
    assert len(entries) == 2
    assert entries[0].timestamp == datetime(1773, 8, 15)
    assert entries[1].timestamp == datetime(1773, 8, 16)


# ---------------------------------------------------------------------------
# Registry + module-level API
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt,cls",
    [("pepys", PepysParser), ("evelyn", EvelynParser), ("boswell", BoswellParser)],
)
def test_get_parser_registry(fmt, cls):
    assert isinstance(get_parser(fmt), cls)


def test_get_parser_unknown_defaults_to_pepys():
    assert isinstance(get_parser("nonexistent-format"), PepysParser)


def test_module_level_parse_uses_pepys(tmp_path):
    md = _write(tmp_path, "MAY 1660\n\nMay 1st. A short but sufficiently long entry here.\n")
    entries = list(parse(md))
    assert len(entries) == 1
    assert entries[0].timestamp == datetime(1660, 5, 1)


# ---------------------------------------------------------------------------
# PSV serialisation
# ---------------------------------------------------------------------------


def test_write_psv_format_and_count(tmp_path):
    """write_psv emits 'TIMESTAMP | diary | prose | CONTENT' and returns the count."""
    md = _write(
        tmp_path,
        "JUNE 1660\n\nJune 1st. Pipe | characters must be replaced in the output.\n",
    )
    out = tmp_path / "out.psv"
    n = write_psv(PepysParser().parse(md), out)
    assert n == 1
    line = out.read_text(encoding="utf-8").strip()
    assert line.startswith("1660-06-01T00:00:00 | diary | prose | ")
    # the literal pipe in content is replaced with an em-dash, so only the
    # three structural delimiters remain
    assert line.count(" | ") == 3
    assert "—" in line
