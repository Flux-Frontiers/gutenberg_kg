"""Unit tests for gutenberg_kg.ia — pure-function coverage."""

from __future__ import annotations

from pathlib import Path

from gutenberg_kg.ia import (
    _coerce_list,
    _coerce_str,
    _detect_running_headers,
    _find_toc_range,
    _is_heading,
    clean_ocr,
    find_text_file,
    slugify,
    text_to_markdown,
    write_reference,
)

# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


def test_slugify_basic():
    assert slugify("Audel Electric Manual") == "audel_electric_manual"


def test_slugify_lowercases():
    assert slugify("WIRING HANDBOOK") == "wiring_handbook"


def test_slugify_strips_punctuation():
    assert slugify("Vol. 3: Power Systems") == "vol_3_power_systems"


def test_slugify_strips_leading_trailing_underscores():
    result = slugify("My Title")
    assert not result.startswith("_")
    assert not result.endswith("_")


def test_slugify_empty():
    assert slugify("") == ""


# ---------------------------------------------------------------------------
# _coerce_str
# ---------------------------------------------------------------------------


def test_coerce_str_from_string():
    assert _coerce_str("hello") == "hello"


def test_coerce_str_strips_whitespace():
    assert _coerce_str("  hello  ") == "hello"


def test_coerce_str_from_list():
    assert _coerce_str(["first", "second"]) == "first"


def test_coerce_str_from_empty_list():
    assert _coerce_str([]) == ""


def test_coerce_str_from_falsy():
    assert _coerce_str(None) == ""
    assert _coerce_str("") == ""


def test_coerce_str_from_int():
    assert _coerce_str(42) == "42"


# ---------------------------------------------------------------------------
# _coerce_list
# ---------------------------------------------------------------------------


def test_coerce_list_from_list():
    assert _coerce_list(["a", "b"]) == ["a", "b"]


def test_coerce_list_filters_empty_strings():
    assert _coerce_list(["a", "", "b"]) == ["a", "b"]


def test_coerce_list_from_string():
    assert _coerce_list("single") == ["single"]


def test_coerce_list_from_empty_string():
    assert _coerce_list("") == []


def test_coerce_list_strips_whitespace():
    assert _coerce_list(["  a  "]) == ["a"]


# ---------------------------------------------------------------------------
# _detect_running_headers
# ---------------------------------------------------------------------------


def test_detect_running_headers_finds_repeating():
    # A header appearing 4+ times should be detected
    lines = ["Audel Electric Manual"] * 5 + ["Some real content"]
    result = _detect_running_headers(lines)
    assert "Audel Electric Manual" in result


def test_detect_running_headers_ignores_rare():
    lines = ["Common line", "Common line", "Common line", "Unique line"]
    result = _detect_running_headers(lines)
    assert "Common line" not in result  # only 3 times, not 4


def test_detect_running_headers_excludes_index():
    # Lines matching INDEX heading re should be excluded even if frequent
    lines = ["INDEX"] * 5
    result = _detect_running_headers(lines)
    assert "INDEX" not in result


def test_detect_running_headers_ignores_short_lines():
    # Lines with len <= 3 are excluded by the filter `3 < len < 80`
    lines = ["hi"] * 6
    result = _detect_running_headers(lines)
    assert "hi" not in result


def test_detect_running_headers_returns_frozenset():
    result = _detect_running_headers(["x y z a b c"] * 4)
    assert isinstance(result, frozenset)


# ---------------------------------------------------------------------------
# clean_ocr
# ---------------------------------------------------------------------------


def test_clean_ocr_normalizes_ligatures():
    result = clean_ocr("ﬁeld ﬂow eﬀect")
    assert "field" in result
    assert "flow" in result
    assert "effect" in result


def test_clean_ocr_joins_hyphenated_linebreaks():
    result = clean_ocr("mag-\nnetism")
    assert "magnetism" in result


def test_clean_ocr_strips_page_numbers():
    text = "Some text\n   42  \nMore text"
    result = clean_ocr(text)
    lines = [ln for ln in result.split("\n") if ln.strip()]
    assert "42" not in lines


def test_clean_ocr_collapses_excessive_blanks():
    text = "Para one\n\n\n\n\nPara two"
    result = clean_ocr(text)
    # Should have at most 2 consecutive blank lines (3 newlines in a row)
    assert "\n\n\n\n" not in result


def test_clean_ocr_removes_figure_markers():
    text = "Some text [Illustration: a diagram] more text"
    result = clean_ocr(text)
    assert "[Illustration" not in result


def test_clean_ocr_removes_running_headers():
    # A line appearing 4+ times is a running header
    lines = ["Audel Electric\n"] * 5 + ["Chapter text\n"]
    text = "".join(lines)
    result = clean_ocr(text)
    # Running header should be stripped
    remaining = [ln for ln in result.split("\n") if ln.strip() == "Audel Electric"]
    assert len(remaining) == 0


def test_clean_ocr_strips_index_at_end():
    body = "Main content\n" * 10
    index = "\nINDEX\n\nAlpha 1\nBeta 2\n"
    text = body + index
    result = clean_ocr(text)
    assert "Alpha 1" not in result


def test_clean_ocr_normalizes_smart_quotes():
    text = "‘hello’ and “world”"
    result = clean_ocr(text)
    assert "'" in result
    assert '"' in result
    assert "‘" not in result


# ---------------------------------------------------------------------------
# _is_heading (ia module)
# ---------------------------------------------------------------------------


def test_ia_is_heading_chapter():
    result = _is_heading("CHAPTER I")
    assert result is not None
    assert result[0] == 2


def test_ia_is_heading_chapter_with_subtitle():
    result = _is_heading("CHAPTER I. Direct Currents")
    assert result is not None
    assert result[0] == 2


def test_ia_is_heading_part():
    result = _is_heading("PART ONE")
    assert result is not None
    assert result[0] == 2


def test_ia_is_heading_section():
    result = _is_heading("SECTION 3")
    assert result is not None
    assert result[0] == 2


def test_ia_is_heading_all_caps():
    result = _is_heading("DIRECT CURRENTS")
    assert result is not None
    assert result[0] == 3


def test_ia_is_heading_question():
    result = _is_heading("Ques. What is a circuit?")
    assert result is not None
    assert result[0] == 4


def test_ia_is_heading_returns_none_normal_text():
    assert _is_heading("This is a paragraph of text.") is None


def test_ia_is_heading_returns_none_empty():
    assert _is_heading("") is None


def test_ia_is_heading_all_caps_rejects_sentence_end():
    # ends with '.' → rejected
    assert _is_heading("DIRECT CURRENTS.") is None


def test_ia_is_heading_all_caps_rejects_single_short_word():
    # single word < 5 chars → rejected
    assert _is_heading("HI") is None


def test_ia_is_heading_all_caps_rejects_too_many_words():
    # > 8 words → rejected
    assert _is_heading("ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE") is None


def test_ia_is_heading_returns_none_for_very_long():
    long_line = "A" * 130
    assert _is_heading(long_line) is None


# ---------------------------------------------------------------------------
# _find_toc_range
# ---------------------------------------------------------------------------


def test_find_toc_range_finds_contents():
    lines = ["CONTENTS", "Chapter I . 1", "Chapter II . 5", "", "", "CHAPTER I"]
    result = _find_toc_range(lines)
    assert len(result) > 0  # non-empty range
    assert 0 in result  # starts at line 0


def test_find_toc_range_finds_table_of_contents():
    lines = ["TABLE OF CONTENTS", "Ch. I . 1", "", "", "CHAPTER I"]
    result = _find_toc_range(lines)
    assert len(result) > 0


def test_find_toc_range_returns_empty_when_absent():
    lines = ["CHAPTER I", "Some text", "CHAPTER II", "More text"]
    result = _find_toc_range(lines)
    assert len(result) == 0


def test_find_toc_range_ends_at_structural_heading():
    lines = [
        "CONTENTS",
        "Chapter I . . . . . 1",
        "Chapter II . . . . . 5",
        "CHAPTER I",  # structural heading (no page number dots)
        "Real content",
    ]
    result = _find_toc_range(lines)
    assert len(result) > 0
    assert 3 not in result  # CHAPTER I line should not be in TOC


# ---------------------------------------------------------------------------
# text_to_markdown (ia module)
# ---------------------------------------------------------------------------


def test_ia_text_to_markdown_includes_title():
    meta = {"title": "Audel Guide", "author": "T. Author"}
    result = text_to_markdown("Some content.", meta)
    assert "# Audel Guide" in result


def test_ia_text_to_markdown_includes_author():
    meta = {"title": "Audel Guide", "author": "T. Author"}
    result = text_to_markdown("Some content.", meta)
    assert "T. Author" in result


def test_ia_text_to_markdown_chapter_becomes_h2():
    text = "CHAPTER I\n\nContent here."
    meta = {"title": "Book", "author": "Author"}
    result = text_to_markdown(text, meta)
    assert "## CHAPTER I" in result


def test_ia_text_to_markdown_question_becomes_h4():
    text = "\nQues. What is resistance?\n\nAns. It opposes current."
    meta = {"title": "Book", "author": "Author"}
    result = text_to_markdown(text, meta)
    assert "#### Ques. What is resistance?" in result


def test_ia_text_to_markdown_includes_publisher():
    meta = {"title": "Book", "author": "A", "publisher": "Audel & Co", "date": "1920"}
    result = text_to_markdown("content.", meta)
    assert "Audel & Co" in result


def test_ia_text_to_markdown_ends_with_newline():
    meta = {"title": "Book", "author": "A"}
    result = text_to_markdown("content.", meta)
    assert result.endswith("\n")


def test_ia_text_to_markdown_chapter_absorbs_subtitle():
    # ALL-CAPS next line that already matches the heading pattern stays as its
    # own heading — only non-heading ALL-CAPS lines get absorbed.
    # "DIRECT CURRENTS" matches the all-caps heading pattern, so it becomes
    # its own ### heading rather than being merged into the chapter heading.
    text = "CHAPTER I\n\nDIRECT CURRENTS\n\nContent here."
    meta = {"title": "Book", "author": "A"}
    result = text_to_markdown(text, meta)
    assert "## CHAPTER I" in result
    assert "### DIRECT CURRENTS" in result


# ---------------------------------------------------------------------------
# write_reference (ia module)
# ---------------------------------------------------------------------------


def test_ia_write_reference_creates_file(tmp_path: Path):
    meta = {"identifier": "mybook01", "title": "My Book", "rights": "Public domain"}
    ref_path = write_reference(tmp_path, meta)
    assert ref_path.exists()


def test_ia_write_reference_contains_identifier(tmp_path: Path):
    meta = {"identifier": "mybook01", "title": "My Book", "rights": "Public domain"}
    write_reference(tmp_path, meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "mybook01" in content


def test_ia_write_reference_contains_title(tmp_path: Path):
    meta = {"identifier": "mybook01", "title": "My Book", "rights": "Public domain"}
    write_reference(tmp_path, meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "My Book" in content


def test_ia_write_reference_includes_publication_section(tmp_path: Path):
    meta = {
        "identifier": "mybook01",
        "title": "My Book",
        "rights": "Public domain",
        "author": "J. Smith",
        "publisher": "Audel",
        "date": "1920",
    }
    write_reference(tmp_path, meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "J. Smith" in content
    assert "Audel" in content
    assert "1920" in content


def test_ia_write_reference_includes_series(tmp_path: Path):
    meta = {
        "identifier": "mybook01",
        "title": "My Book",
        "rights": "Public domain",
        "series": "Audel Technical Series",
        "volume": "3",
    }
    write_reference(tmp_path, meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "Audel Technical Series" in content
    assert "3" in content


def test_ia_write_reference_includes_subjects(tmp_path: Path):
    meta = {
        "identifier": "mybook01",
        "title": "My Book",
        "rights": "Public domain",
        "subjects": ["Electricity", "Wiring"],
    }
    write_reference(tmp_path, meta)
    content = (tmp_path / "reference.md").read_text(encoding="utf-8")
    assert "Electricity" in content
    assert "Wiring" in content


# ---------------------------------------------------------------------------
# find_text_file
# ---------------------------------------------------------------------------


def test_find_text_file_prefers_djvu():
    files = [
        {"name": "book.txt"},
        {"name": "book_djvu.txt"},
    ]
    result = find_text_file("book", files)
    assert result is not None
    filename, fmt = result
    assert filename == "book_djvu.txt"
    assert fmt == "DjVu Text"


def test_find_text_file_falls_back_to_txt():
    files = [{"name": "book.txt"}]
    result = find_text_file("book", files)
    assert result is not None
    filename, fmt = result
    assert filename == "book.txt"
    assert fmt == "Plain Text"


def test_find_text_file_returns_none_when_no_text():
    files = [{"name": "book.pdf"}, {"name": "book.djvu"}]
    result = find_text_file("book", files)
    assert result is None


def test_find_text_file_excludes_readme(tmp_path: Path):
    files = [{"name": "readme.txt"}, {"name": "book.txt"}]
    result = find_text_file("book", files)
    assert result is not None
    assert result[0] == "book.txt"


def test_find_text_file_excludes_meta_files():
    files = [{"name": "book_meta.txt"}, {"name": "book.txt"}]
    result = find_text_file("book", files)
    assert result is not None
    assert result[0] == "book.txt"


def test_find_text_file_shortest_djvu_wins():
    files = [
        {"name": "longer_name_book_djvu.txt"},
        {"name": "book_djvu.txt"},
    ]
    result = find_text_file("book", files)
    assert result is not None
    assert result[0] == "book_djvu.txt"


def test_find_text_file_empty_files():
    result = find_text_file("book", [])
    assert result is None
