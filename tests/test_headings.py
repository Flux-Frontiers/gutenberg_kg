"""Unit tests for the heading vocabulary shared by both converters."""

from __future__ import annotations

from gutenberg_kg.headings import (
    ALL_CAPS_PATTERN,
    HEADING_PATTERNS,
    ROMAN_STANDALONE_PATTERN,
    STRUCTURAL_PATTERNS,
    is_heading,
    is_structural_heading,
)


class TestStructuralPatterns:
    def test_derived_by_identity_not_position(self):
        """The bare ALL-CAPS catch-all is the one pattern excluded.

        It used to be excluded by slicing (HEADING_PATTERNS[:-1]), which
        silently changed meaning whenever a pattern was appended.
        """
        assert all(p is not ALL_CAPS_PATTERN for p, _ in STRUCTURAL_PATTERNS)
        assert len(STRUCTURAL_PATTERNS) == len(HEADING_PATTERNS) - 1

    def test_all_caps_line_is_not_structural(self):
        assert is_heading("INTRODUCTORY NOTE") is not None
        assert not is_structural_heading("INTRODUCTORY NOTE")

    def test_keyword_line_is_structural(self):
        assert is_structural_heading("CHAPTER I")


class TestRomanNumeralsAreWholeTokens:
    """Under IGNORECASE the roman class matches ordinary letters.

    'Volume containing several works' parsed as VOLUME + roman 'C' + a
    title, turning sentences into headings in both corpora.
    """

    def test_a_word_starting_with_a_roman_letter_is_not_a_numeral(self):
        assert is_heading("Volume containing several works; and among them") is None
        assert is_heading("Chapter Circuits and their uses") is None

    def test_real_numerals_still_match(self):
        for line in ("VOLUME II", "CHAPTER XIV", "BOOK 3", "PART ONE"):
            assert is_heading(line) is not None, line


class TestPatternSelection:
    def test_caller_may_supply_its_own_vocabulary(self):
        without_roman = [
            (p, lvl) for p, lvl in HEADING_PATTERNS if p is not ROMAN_STANDALONE_PATTERN
        ]
        assert is_heading("IV.") is not None
        assert is_heading("IV.", without_roman) is None

    def test_all_caps_guard_is_consulted(self):
        assert is_heading("THE END") is not None
        assert is_heading("THE END", all_caps_guard=lambda _line: False) is None
