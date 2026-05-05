"""Unit tests for gutenberg_kg.gutenberg — pure-function coverage."""

from __future__ import annotations

import os
from pathlib import Path

from gutenberg_kg.gutenberg import (
    _check_mark,
    _detect_toc,
    _is_heading,
    _skip_front_matter,
    _survey_book_dir,
    parse_catalog,
    slugify,
    strip_boilerplate,
    text_to_markdown,
    write_reference,
)

# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


def test_slugify_basic():
    assert slugify("Moby Dick") == "moby_dick"


def test_slugify_lowercases():
    assert slugify("HAMLET") == "hamlet"


def test_slugify_strips_punctuation():
    assert slugify("War, and Peace") == "war_and_peace"


def test_slugify_collapses_spaces_and_hyphens():
    assert slugify("A Tale  of Two  Cities") == "a_tale_of_two_cities"


def test_slugify_hyphens_become_underscores():
    # gutenberg slugify converts both spaces and hyphens to underscores
    assert slugify("Don Quixote-1605") == "don_quixote_1605"


def test_slugify_empty():
    assert slugify("") == ""


# ---------------------------------------------------------------------------
# strip_boilerplate
# ---------------------------------------------------------------------------

_PG_START = "*** START OF THE PROJECT GUTENBERG EBOOK HAMLET ***"
_PG_END = "*** END OF THE PROJECT GUTENBERG EBOOK HAMLET ***"


def test_strip_boilerplate_removes_header_and_footer():
    text = f"Header junk\n{_PG_START}\n\nActual content\n\n{_PG_END}\nFooter junk"
    result = strip_boilerplate(text)
    assert "Header junk" not in result
    assert "Footer junk" not in result
    assert "Actual content" in result


def test_strip_boilerplate_no_markers_returns_text():
    text = "Plain text with no markers."
    result = strip_boilerplate(text)
    assert "Plain text" in result


def test_strip_boilerplate_only_start():
    text = f"Header\n{_PG_START}\n\nContent here"
    result = strip_boilerplate(text)
    assert "Header" not in result
    assert "Content here" in result


def test_strip_boilerplate_only_end():
    text = f"Content here\n{_PG_END}\nFooter junk"
    result = strip_boilerplate(text)
    assert "Footer junk" not in result
    assert "Content here" in result


def test_strip_boilerplate_ends_with_newline():
    result = strip_boilerplate("some text")
    assert result.endswith("\n")


# ---------------------------------------------------------------------------
# _is_heading
# ---------------------------------------------------------------------------


def test_is_heading_chapter_roman():
    result = _is_heading("CHAPTER I.")
    assert result is not None
    level, text = result
    assert level == 2
    assert "CHAPTER" in text


def test_is_heading_chapter_arabic():
    result = _is_heading("CHAPTER 3")
    assert result is not None
    assert result[0] == 2


def test_is_heading_volume():
    result = _is_heading("VOLUME II")
    assert result is not None
    assert result[0] == 2


def test_is_heading_act():
    result = _is_heading("ACT I")
    assert result is not None
    assert result[0] == 2


def test_is_heading_scene():
    result = _is_heading("SCENE III")
    assert result is not None
    assert result[0] == 3


def test_is_heading_all_caps():
    result = _is_heading("INTRODUCTION")
    assert result is not None
    assert result[0] == 3


def test_is_heading_roman_standalone():
    result = _is_heading("IV.")
    assert result is not None
    assert result[0] == 3
    assert result[1] == "IV."


def test_is_heading_roman_titled():
    result = _is_heading("I. A SCANDAL IN BOHEMIA")
    assert result is not None
    assert result[0] == 2
    assert "SCANDAL" in result[1]


def test_is_heading_stave():
    result = _is_heading("STAVE I")
    assert result is not None
    assert result[0] == 2


def test_is_heading_letter():
    result = _is_heading("Letter I")
    assert result is not None
    assert result[0] == 2


def test_is_heading_ordinal_book():
    result = _is_heading("THE FIRST BOOK")
    assert result is not None
    assert result[0] == 2


def test_is_heading_returns_none_for_normal_text():
    assert _is_heading("This is a normal paragraph.") is None


def test_is_heading_returns_none_for_empty():
    assert _is_heading("") is None


def test_is_heading_returns_none_for_very_long_line():
    long_line = "A" * 130
    assert _is_heading(long_line) is None


def test_is_heading_all_caps_too_many_words():
    # 9 words → rejected
    assert _is_heading("ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE") is None


def test_is_heading_all_caps_ends_with_semicolon():
    assert _is_heading("INTRODUCTION;") is None


# ---------------------------------------------------------------------------
# _skip_front_matter
# ---------------------------------------------------------------------------


def test_skip_front_matter_skips_produced_by():
    lines = [
        "Produced by Some Name",
        "and Another Name",
        "",
        "CHAPTER I",
    ]
    idx = _skip_front_matter(lines, 0)
    assert lines[idx].strip() == "CHAPTER I"


def test_skip_front_matter_skips_leading_blanks():
    lines = ["", "", "CHAPTER I"]
    idx = _skip_front_matter(lines, 0)
    assert lines[idx].strip() == "CHAPTER I"


def test_skip_front_matter_no_front_matter():
    lines = ["CHAPTER I", "Some text"]
    idx = _skip_front_matter(lines, 0)
    assert idx == 0


def test_skip_front_matter_respects_start_idx():
    lines = ["", "CHAPTER I", "Some text"]
    idx = _skip_front_matter(lines, 1)
    assert idx == 1


# ---------------------------------------------------------------------------
# _detect_toc
# ---------------------------------------------------------------------------


def test_detect_toc_finds_contents_heading():
    lines = ["CONTENTS", "Chapter I . . . . 1", "Chapter II . . . . 5", "", "", "", "CHAPTER I"]
    result = _detect_toc(lines, 0, len(lines))
    assert result is not None
    assert result[0] == 0


def test_detect_toc_returns_none_when_absent():
    lines = ["CHAPTER I", "Some text", "CHAPTER II", "More text"]
    result = _detect_toc(lines, 0, len(lines))
    assert result is None


def test_detect_toc_ends_at_triple_blank():
    lines = [
        "CONTENTS",
        "Chapter I",
        "Chapter II",
        "",
        "",
        "",
        "CHAPTER I",
    ]
    result = _detect_toc(lines, 0, len(lines))
    assert result is not None
    toc_start, toc_end = result
    assert toc_start == 0
    assert toc_end < len(lines)


# ---------------------------------------------------------------------------
# text_to_markdown
# ---------------------------------------------------------------------------


def test_text_to_markdown_includes_title():
    meta = {"title": "My Book", "author": "My Author"}
    result = text_to_markdown("Some text.", meta)
    assert "# My Book" in result


def test_text_to_markdown_includes_author():
    meta = {"title": "My Book", "author": "My Author"}
    result = text_to_markdown("Some text.", meta)
    assert "My Author" in result


def test_text_to_markdown_chapter_becomes_h2():
    text = "CHAPTER I.\n\nSome content."
    meta = {"title": "T", "author": "A"}
    result = text_to_markdown(text, meta)
    assert "## CHAPTER I." in result


def test_text_to_markdown_ends_with_newline():
    meta = {"title": "T", "author": "A"}
    result = text_to_markdown("Hello.", meta)
    assert result.endswith("\n")


def test_text_to_markdown_untitled_fallback():
    result = text_to_markdown("Text.", {})
    assert "# Untitled" in result


# ---------------------------------------------------------------------------
# write_reference
# ---------------------------------------------------------------------------


def test_write_reference_creates_file(tmp_path: Path):
    meta = {
        "title": "Hamlet",
        "ebook_id": 1787,
        "gutenberg_url": "https://www.gutenberg.org/ebooks/1787",
        "rights": "Public domain",
    }
    ref_path = write_reference(str(tmp_path), meta)
    assert os.path.exists(ref_path)


def test_write_reference_contains_title(tmp_path: Path):
    meta = {"title": "Hamlet", "ebook_id": 1787, "gutenberg_url": "", "rights": ""}
    write_reference(str(tmp_path), meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "Hamlet" in content


def test_write_reference_contains_ebook_id(tmp_path: Path):
    meta = {"title": "Hamlet", "ebook_id": 1787, "gutenberg_url": "", "rights": ""}
    write_reference(str(tmp_path), meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "1787" in content


def test_write_reference_includes_author_section(tmp_path: Path):
    meta = {
        "title": "Hamlet",
        "ebook_id": 1787,
        "gutenberg_url": "",
        "rights": "",
        "author": "William Shakespeare",
        "author_birth": "1564",
        "author_death": "1616",
    }
    write_reference(str(tmp_path), meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "William Shakespeare" in content
    assert "1564" in content
    assert "1616" in content


def test_write_reference_includes_subjects(tmp_path: Path):
    meta = {
        "title": "Hamlet",
        "ebook_id": 1787,
        "gutenberg_url": "",
        "rights": "",
        "subjects": ["Tragedy", "Revenge"],
    }
    write_reference(str(tmp_path), meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "Tragedy" in content
    assert "Revenge" in content


def test_write_reference_includes_summary(tmp_path: Path):
    meta = {
        "title": "Hamlet",
        "ebook_id": 1787,
        "gutenberg_url": "",
        "rights": "",
        "summary": "A prince seeks revenge.",
    }
    write_reference(str(tmp_path), meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "A prince seeks revenge." in content


# ---------------------------------------------------------------------------
# parse_catalog
# ---------------------------------------------------------------------------


def test_parse_catalog_basic(tmp_path: Path):
    catalog = tmp_path / "catalog.txt"
    catalog.write_text("1342\tPride and Prejudice\n2701\tMoby Dick\n", encoding="utf-8")
    entries = parse_catalog(str(catalog))
    assert entries == [(1342, "Pride and Prejudice"), (2701, "Moby Dick")]


def test_parse_catalog_no_title(tmp_path: Path):
    catalog = tmp_path / "catalog.txt"
    catalog.write_text("1342\n", encoding="utf-8")
    entries = parse_catalog(str(catalog))
    assert entries == [(1342, None)]


def test_parse_catalog_skips_comments(tmp_path: Path):
    catalog = tmp_path / "catalog.txt"
    catalog.write_text("# comment\n1342\tPride and Prejudice\n", encoding="utf-8")
    entries = parse_catalog(str(catalog))
    assert len(entries) == 1
    assert entries[0][0] == 1342


def test_parse_catalog_skips_blank_lines(tmp_path: Path):
    catalog = tmp_path / "catalog.txt"
    catalog.write_text("\n1342\n\n2701\n", encoding="utf-8")
    entries = parse_catalog(str(catalog))
    assert len(entries) == 2


def test_parse_catalog_skips_non_numeric_id(tmp_path: Path, capsys):
    catalog = tmp_path / "catalog.txt"
    catalog.write_text("abc\tBad Entry\n1342\tGood Entry\n", encoding="utf-8")
    entries = parse_catalog(str(catalog))
    assert len(entries) == 1
    assert entries[0][0] == 1342


# ---------------------------------------------------------------------------
# _survey_book_dir
# ---------------------------------------------------------------------------


def test_survey_book_dir_empty_dir(tmp_path: Path):
    book_dir = tmp_path / "My Book"
    book_dir.mkdir()
    result = _survey_book_dir(str(book_dir), "My Book")
    assert result["title"] == "My Book"
    assert result["md"] is False
    assert result["ref"] is False
    assert result["kg"] is False


def test_survey_book_dir_with_md_file(tmp_path: Path):
    book_dir = tmp_path / "My Book"
    book_dir.mkdir()
    (book_dir / "my_book.md").write_text("content", encoding="utf-8")
    result = _survey_book_dir(str(book_dir), "My Book")
    assert result["md"] is True


def test_survey_book_dir_with_reference(tmp_path: Path):
    book_dir = tmp_path / "My Book"
    book_dir.mkdir()
    (book_dir / "reference.md").write_text("ref content", encoding="utf-8")
    result = _survey_book_dir(str(book_dir), "My Book")
    assert result["ref"] is True


def test_survey_book_dir_with_kg(tmp_path: Path):
    book_dir = tmp_path / "My Book"
    dockg_dir = book_dir / ".dockg"
    dockg_dir.mkdir(parents=True)
    (dockg_dir / "graph.sqlite").write_bytes(b"")
    result = _survey_book_dir(str(book_dir), "My Book")
    assert result["kg"] is True


# ---------------------------------------------------------------------------
# _check_mark
# ---------------------------------------------------------------------------


def test_check_mark_true():
    assert _check_mark(True) == "✓"


def test_check_mark_false():
    assert _check_mark(False) == "✗"
