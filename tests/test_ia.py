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


# ---------------------------------------------------------------------------
# identifier-keyed idempotence and catalog write-back
# ---------------------------------------------------------------------------

from gutenberg_kg import ia as _ia  # noqa: E402
from gutenberg_kg.authors import parse_reference as _parse_reference  # noqa: E402


def _make_ia_book(root: Path, name: str, identifier: str) -> Path:
    book = root / name
    book.mkdir(parents=True)
    md = book / f"{slugify(name)}.md"
    md.write_text("Body text.", encoding="utf-8")
    (book / "reference.md").write_text(
        f"# Reference: {name}\n\n- **Internet Archive ID**: {identifier}\n",
        encoding="utf-8",
    )
    return md


def test_parse_reference_extracts_ia_id(tmp_path: Path):
    """The identifier was always written; nothing read it until now."""
    _make_ia_book(tmp_path, "Miracle Mongers", "MiracleMongersAndTheirMethods")
    meta = _parse_reference(tmp_path / "Miracle Mongers" / "reference.md")
    assert meta["ia_id"] == "MiracleMongersAndTheirMethods"
    assert meta["ebook_id"] is None


def test_find_item_by_id_matches_regardless_of_dir_name(tmp_path: Path):
    md = _make_ia_book(tmp_path, "Miracle Mongers and Their Methods", "MiracleMongers")
    assert _ia._find_item_by_id("MiracleMongers", tmp_path) == str(md)


def test_find_item_by_id_returns_none_when_absent(tmp_path: Path):
    _make_ia_book(tmp_path, "Miracle Mongers", "MiracleMongers")
    assert _ia._find_item_by_id("SomethingElse", tmp_path) is None


def test_ia_download_skips_by_identifier_despite_title_override(tmp_path, monkeypatch, capsys):
    """The duplicate bug: a differing --title must not write a second copy.

    The IA counterpart of the Gutenberg #2445 regression. IA titles are
    uncurated, so an override is the normal case, which made this reachable in
    ordinary use -- and audit could not see the result.
    """
    monkeypatch.setattr(_ia, "CORPUS_ROOT", tmp_path / "corpus")
    monkeypatch.setattr(_ia, "CATALOG_ROOT", tmp_path / "catalogs")
    _make_ia_book(tmp_path / "corpus" / "curiosities", "Miracle Mongers", "MiracleMongers")

    def _no_network(*a, **kw):
        raise AssertionError("network must not be hit when the identifier exists")

    monkeypatch.setattr(_ia, "fetch_ia_metadata", _no_network)
    result = _ia.download_book(
        "MiracleMongers", title="A Totally Different Title", genre="curiosities"
    )
    assert result is not None
    assert Path(result).parent.name == "Miracle Mongers"
    assert "already downloaded (IA MiracleMongers)" in capsys.readouterr().out


def test_ia_record_in_catalog_appends_and_is_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(_ia, "CATALOG_ROOT", tmp_path)
    assert _ia.record_in_catalog("curiosities", "MiracleMongers", "Miracle Mongers") is True
    assert _ia.record_in_catalog("curiosities", "MiracleMongers", "Miracle Mongers") is False
    assert (tmp_path / "curiosities.txt").read_text(
        encoding="utf-8"
    ) == "MiracleMongers\tMiracle Mongers\n"


def test_ia_record_in_catalog_dry_run_writes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(_ia, "CATALOG_ROOT", tmp_path / "catalogs")
    assert _ia.record_in_catalog("curiosities", "X", "Some Item", dry_run=True) is True
    assert not (tmp_path / "catalogs").exists()


def test_ia_catalog_sync_records_and_preserves(tmp_path: Path, monkeypatch):
    """Sync appends; a curated title override already present is left alone."""
    monkeypatch.setattr(_ia, "CORPUS_ROOT", tmp_path / "corpus")
    monkeypatch.setattr(_ia, "CATALOG_ROOT", tmp_path / "catalogs")
    monkeypatch.setattr(_ia, "ALL_GENRES", ["audel-electric"])
    (tmp_path / "catalogs").mkdir()
    (tmp_path / "catalogs" / "audel-electric.txt").write_text(
        "# curated\naudels-electric-library-vol-1\tAudels Electric Library Vol 1\n",
        encoding="utf-8",
    )
    _make_ia_book(
        tmp_path / "corpus" / "audel-electric",
        "Audels Electric Library Vol 1",
        "audels-electric-library-vol-1",
    )
    _make_ia_book(
        tmp_path / "corpus" / "audel-electric", "Vol VIII Long Title", "audelsnewelectri008004mbp"
    )

    assert _ia.run_catalog_sync(["audel-electric"]) == 1  # vol 1 already there
    text = (tmp_path / "catalogs" / "audel-electric.txt").read_text(encoding="utf-8")
    assert text.startswith("# curated\n")
    assert text.endswith("audelsnewelectri008004mbp\tVol VIII Long Title\n")
    assert _ia.run_catalog_sync(["audel-electric"]) == 0  # idempotent


def test_ia_parse_catalog_reads_identifier_and_title(tmp_path: Path):
    cat = tmp_path / "curiosities.txt"
    cat.write_text("# comment\n\nMiracleMongers\tMiracle Mongers\nBareIdentifier\n", "utf-8")
    assert _ia.parse_catalog(cat) == [
        ("MiracleMongers", "Miracle Mongers"),
        ("BareIdentifier", None),
    ]


# ---------------------------------------------------------------------------
# ported from ia_kg: draft-catalog export and genre inference
# ---------------------------------------------------------------------------


def test_export_draft_catalog_comments_every_entry(tmp_path: Path):
    """Nothing must download from an un-reviewed draft. IA search returns
    modern reprints beside period scans, so the human pass is the point."""
    results = [
        {"identifier": "audels-electric-library-vol-1", "title": "Audels Vol 1", "date": "1929"},
        {"identifier": "audelsnewelectri0004unse", "title": "Audels New Vol IV", "date": "1963"},
    ]
    out = tmp_path / "catalogs" / "audel-electric.txt"
    assert _ia.export_draft_catalog("audels electric library", results, out) == 2

    text = out.read_text(encoding="utf-8")
    assert _ia.parse_catalog(out) == []  # every line commented -> parses to nothing
    assert "audels-electric-library-vol-1" in text
    assert "1963" in text  # the year is carried so rights can be judged
    assert "audels electric library" in text  # query recorded for provenance


def test_export_draft_catalog_creates_parent_dirs(tmp_path: Path):
    out = tmp_path / "a" / "b" / "draft.txt"
    _ia.export_draft_catalog("q", [{"identifier": "x", "title": "X", "date": "1900"}], out)
    assert out.exists()


def test_export_draft_catalog_round_trips_after_uncommenting(tmp_path: Path):
    """The documented workflow: export, uncomment, feed straight to catalog."""
    results = [{"identifier": "vol-1", "title": "Vol 1", "date": "1929"}]
    out = tmp_path / "d.txt"
    _ia.export_draft_catalog("q", results, out)
    # a human uncommenting one line, keeping the title, dropping the year note
    out.write_text("vol-1\tVol 1\n", encoding="utf-8")
    assert _ia.parse_catalog(out) == [("vol-1", "Vol 1")]


def test_run_catalog_infers_genre_from_filename(tmp_path: Path, monkeypatch, capsys):
    """Without inference an omitted --genre writes books to the corpus root,
    where no catalog covers them."""
    monkeypatch.setattr(_ia, "ALL_GENRES", ["audel-electric"])
    cat = tmp_path / "audel-electric.txt"
    cat.write_text("some-identifier\tSome Title\n", encoding="utf-8")

    seen = {}

    def _fake_download(identifier, title=None, genre=None, force=False, dry_run=False):
        seen["genre"] = genre
        return "/fake/path.md"

    monkeypatch.setattr(_ia, "download_book", _fake_download)
    _ia.run_catalog(str(cat), genre=None)
    assert seen["genre"] == "audel-electric"
    assert "inferred from filename" in capsys.readouterr().out


def test_run_catalog_explicit_genre_wins_over_filename(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(_ia, "ALL_GENRES", ["audel-electric", "curiosities"])
    cat = tmp_path / "audel-electric.txt"
    cat.write_text("some-identifier\tSome Title\n", encoding="utf-8")

    seen = {}

    def _fake_download(identifier, title=None, genre=None, force=False, dry_run=False):
        seen["genre"] = genre
        return "/fake/path.md"

    monkeypatch.setattr(_ia, "download_book", _fake_download)
    _ia.run_catalog(str(cat), genre="curiosities")
    assert seen["genre"] == "curiosities"


def test_run_catalog_does_not_invent_a_genre(tmp_path: Path, monkeypatch):
    """A filename that is not a known genre must not become one."""
    monkeypatch.setattr(_ia, "ALL_GENRES", ["audel-electric"])
    cat = tmp_path / "random-notes.txt"
    cat.write_text("some-identifier\tSome Title\n", encoding="utf-8")

    seen = {}

    def _fake_download(identifier, title=None, genre=None, force=False, dry_run=False):
        seen["genre"] = genre
        return "/fake/path.md"

    monkeypatch.setattr(_ia, "download_book", _fake_download)
    _ia.run_catalog(str(cat), genre=None)
    assert seen["genre"] is None
