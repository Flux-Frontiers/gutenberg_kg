"""Unit tests for gutenberg_kg.gutenberg — pure-function coverage."""

from __future__ import annotations

import os
from pathlib import Path

from gutenberg_kg import gutenberg as dg
from gutenberg_kg.gutenberg import (
    _check_mark,
    _detect_toc,
    _find_book_by_id,
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


# ---------------------------------------------------------------------------
# _find_book_by_id / ID-based download idempotence
# ---------------------------------------------------------------------------


def _make_downloaded_book(root: Path, name: str, ebook_id: int) -> Path:
    book_dir = root / name
    book_dir.mkdir(parents=True)
    md = book_dir / f"{slugify(name)}.md"
    md.write_text("Body text.", encoding="utf-8")
    (book_dir / "reference.md").write_text(
        f"# Reference: {name}\n\n- **Project Gutenberg ID**: {ebook_id}\n",
        encoding="utf-8",
    )
    return md


def test_find_book_by_id_matches_regardless_of_dir_name(tmp_path: Path):
    md = _make_downloaded_book(tmp_path, "Letters on England", 2445)
    assert _find_book_by_id(2445, str(tmp_path)) == str(md)


def test_find_book_by_id_returns_none_when_absent(tmp_path: Path):
    _make_downloaded_book(tmp_path, "Letters on England", 2445)
    assert _find_book_by_id(9999, str(tmp_path)) is None


def test_find_book_by_id_returns_none_for_missing_root(tmp_path: Path):
    assert _find_book_by_id(2445, str(tmp_path / "nope")) is None


def test_find_book_by_id_ignores_book_without_main_md(tmp_path: Path):
    book_dir = tmp_path / "Broken Book"
    book_dir.mkdir()
    (book_dir / "reference.md").write_text(
        "# Reference: Broken Book\n\n- **Project Gutenberg ID**: 2445\n",
        encoding="utf-8",
    )
    assert _find_book_by_id(2445, str(tmp_path)) is None


def test_download_book_skips_by_id_despite_title_override(tmp_path: Path, monkeypatch, capsys):
    """A catalog title override that differs from the existing directory name
    must not re-download the book (the regression that duplicated #2445)."""
    monkeypatch.setattr(dg, "CORPUS_ROOT", str(tmp_path))
    md = _make_downloaded_book(tmp_path / "letters", "Letters on England", 2445)

    def _no_network(*a, **kw):
        raise AssertionError("network must not be hit when the ID already exists")

    monkeypatch.setattr(dg, "fetch_metadata", _no_network)
    result = dg.download_book(2445, title="Philosophical Letters — Voltaire", genre="letters")
    assert result == str(md)
    assert "already downloaded (Gutenberg #2445)" in capsys.readouterr().out


def test_download_book_force_bypasses_id_check(tmp_path: Path, monkeypatch):
    """--force must still reach the metadata fetch even when the ID exists."""
    monkeypatch.setattr(dg, "CORPUS_ROOT", str(tmp_path))
    _make_downloaded_book(tmp_path / "letters", "Letters on England", 2445)

    class _Sentinel(Exception):
        pass

    def _boom(*a, **kw):
        raise _Sentinel

    monkeypatch.setattr(dg, "fetch_metadata", _boom)
    try:
        dg.download_book(2445, genre="letters", force=True)
    except _Sentinel:
        pass  # reached the fetch — the ID check was bypassed
    else:
        raise AssertionError("expected the download path to be taken")


# ---------------------------------------------------------------------------
# SURA headings (Quran) and the bilingual heading gate
# ---------------------------------------------------------------------------


def test_is_heading_sura_with_title_and_edition_marker():
    # Rodwell: footnote digit on the word, edition order in brackets.
    result = _is_heading("SURA1 XCVI.-THICK BLOOD, OR CLOTS OF BLOOD [I.]")
    assert result is not None
    assert result[0] == 2
    assert "XCVI" in result[1]


def test_is_heading_sura_space_separated():
    result = _is_heading("SURA CXI. ABU LAHAB [XI.]")
    assert result is not None
    assert result[0] == 2


def test_is_heading_sura_numeral_only():
    result = _is_heading("SURA I.1 [VIII.]")
    assert result is not None
    assert result[0] == 2


def test_is_heading_sura_requires_a_separator_after_the_numeral():
    # Prose must not be promoted: "SURA I saw ..." is a sentence, not a heading.
    assert _is_heading("SURA I saw the light in the east") is None


def test_is_heading_ignores_sura_in_prose():
    assert _is_heading("the sura was revealed at Mecca") is None


def test_breaks_before_heading_on_blank():
    assert dg._breaks_before_heading("") is True
    assert dg._breaks_before_heading("   ") is True


def test_breaks_before_heading_on_non_latin_line():
    # Legge's Analects prints the Chinese heading directly above the English.
    assert dg._breaks_before_heading("學而第一") is True


def test_breaks_before_heading_false_for_prose():
    assert dg._breaks_before_heading("with a constant perseverance") is False
    assert dg._breaks_before_heading("1. The Master said") is False


def test_bilingual_heading_is_promoted():
    # Regression: every "BOOK I." in the Analects was swallowed because the
    # Chinese line above it meant the blank-line gate never opened, collapsing
    # the whole work into a single section.
    text = "\n".join(
        [
            "*** START OF THE PROJECT GUTENBERG EBOOK TEST ***",
            "",
            "CONFUCIAN ANALECTS.",
            "",
            "學而第一",
            "BOOK I.  HSIO R.",
            "",
            "The Master said, is it not pleasant to learn.",
            "",
            "為政第二",
            "BOOK II. WEI CHANG.",
            "",
            "He who exercises government by means of his virtue.",
            "",
            "*** END OF THE PROJECT GUTENBERG EBOOK TEST ***",
        ]
    )
    md = text_to_markdown(text, {"title": "Analects", "author": "Legge"})
    assert "## BOOK I.  HSIO R." in md
    assert "## BOOK II. WEI CHANG." in md


def test_sura_headings_become_sections():
    text = "\n".join(
        [
            "*** START OF THE PROJECT GUTENBERG EBOOK TEST ***",
            "",
            "SURA XCVI.-THICK BLOOD [I.]",
            "",
            "Recite thou, in the name of thy Lord who created.",
            "",
            "SURA LXXIV.-THE ENWRAPPED [II.]",
            "",
            "O thou, enwrapped in thy mantle.",
            "",
            "*** END OF THE PROJECT GUTENBERG EBOOK TEST ***",
        ]
    )
    md = text_to_markdown(text, {"title": "Quran", "author": "Rodwell"})
    assert md.count("\n## SURA") == 2


# ---------------------------------------------------------------------------
# record_in_catalog — catalog write-back
# ---------------------------------------------------------------------------


def test_record_in_catalog_appends_new_entry(tmp_path: Path, monkeypatch):
    """A new download is written to its genre catalog as <id>\\t<title>."""
    monkeypatch.setattr(dg, "CATALOG_ROOT", str(tmp_path))
    catalog = tmp_path / "letters.txt"
    catalog.write_text("2811\tLetters of Pliny the Younger\n", encoding="utf-8")

    assert dg.record_in_catalog("letters", 2445, "Letters on England") is True
    assert catalog.read_text(encoding="utf-8").endswith("2445\tLetters on England\n")
    assert parse_catalog(str(catalog)) == [
        (2811, "Letters of Pliny the Younger"),
        (2445, "Letters on England"),
    ]


def test_record_in_catalog_is_idempotent_on_id(tmp_path: Path, monkeypatch):
    """Re-recording an ID already present must not duplicate the line."""
    monkeypatch.setattr(dg, "CATALOG_ROOT", str(tmp_path))
    catalog = tmp_path / "letters.txt"
    catalog.write_text("2445\tLetters on England\n", encoding="utf-8")

    assert dg.record_in_catalog("letters", 2445, "Letters on England") is False
    assert catalog.read_text(encoding="utf-8").count("2445") == 1


def test_record_in_catalog_repairs_missing_trailing_newline(tmp_path: Path, monkeypatch):
    """A catalog whose last line lacks \\n must not get two entries joined."""
    monkeypatch.setattr(dg, "CATALOG_ROOT", str(tmp_path))
    catalog = tmp_path / "letters.txt"
    catalog.write_text("2811\tLetters of Pliny the Younger", encoding="utf-8")  # no \n

    dg.record_in_catalog("letters", 2445, "Letters on England")
    assert parse_catalog(str(catalog)) == [
        (2811, "Letters of Pliny the Younger"),
        (2445, "Letters on England"),
    ]


def test_record_in_catalog_creates_missing_catalog(tmp_path: Path, monkeypatch):
    """A genre with no catalog yet gets one rather than silently dropping the book."""
    monkeypatch.setattr(dg, "CATALOG_ROOT", str(tmp_path / "catalogs"))
    assert dg.record_in_catalog("curiosities", 123, "Some Book") is True
    assert (tmp_path / "catalogs" / "curiosities.txt").read_text(
        encoding="utf-8"
    ) == "123\tSome Book\n"


def test_record_in_catalog_skips_dry_run_and_genreless(tmp_path: Path, monkeypatch):
    """--dry-run writes nothing but still reports the entry as needed, so a
    caller (catalog-sync) can count pending repairs. A genre-less download has
    no catalog to write to and reports nothing."""
    monkeypatch.setattr(dg, "CATALOG_ROOT", str(tmp_path))
    assert dg.record_in_catalog("letters", 2445, "Letters on England", dry_run=True) is True
    assert dg.record_in_catalog(None, 2445, "Letters on England") is False
    assert list(tmp_path.iterdir()) == []  # nothing written either way


def test_record_in_catalog_dry_run_stays_silent_when_already_present(tmp_path, monkeypatch):
    """A dry run must not report an entry that already exists."""
    monkeypatch.setattr(dg, "CATALOG_ROOT", str(tmp_path))
    (tmp_path / "letters.txt").write_text("2445\tLetters on England\n", encoding="utf-8")
    assert dg.record_in_catalog("letters", 2445, "Letters on England", dry_run=True) is False


def test_download_book_catalogues_the_already_present_book(tmp_path: Path, monkeypatch):
    """The skip path repairs drift: on disk but uncatalogued becomes catalogued.

    This is the pre-existing breakage -- books added by `download book` before
    write-back existed are invisible to their catalog, and re-running the
    download is the natural repair.
    """
    monkeypatch.setattr(dg, "CORPUS_ROOT", str(tmp_path / "corpus"))
    monkeypatch.setattr(dg, "CATALOG_ROOT", str(tmp_path / "catalogs"))
    _make_downloaded_book(tmp_path / "corpus" / "letters", "Letters on England", 2445)

    def _no_network(*a, **kw):
        raise AssertionError("network must not be hit when the ID already exists")

    monkeypatch.setattr(dg, "fetch_metadata", _no_network)
    dg.download_book(2445, genre="letters")

    assert parse_catalog(str(tmp_path / "catalogs" / "letters.txt")) == [
        (2445, "Letters on England")
    ]


def test_download_book_dry_run_writes_no_catalog(tmp_path: Path, monkeypatch):
    """--dry-run must leave the catalog untouched on every path."""
    monkeypatch.setattr(dg, "CORPUS_ROOT", str(tmp_path / "corpus"))
    monkeypatch.setattr(dg, "CATALOG_ROOT", str(tmp_path / "catalogs"))
    monkeypatch.setattr(dg, "fetch_metadata", lambda *a, **kw: {"title": "Letters on England"})

    dg.download_book(2445, genre="letters", dry_run=True)
    assert not (tmp_path / "catalogs").exists()


# ---------------------------------------------------------------------------
# run_catalog_sync — repairing drift from downloads that predate write-back
# ---------------------------------------------------------------------------


def _sync_corpus(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    corpus, catalogs = tmp_path / "corpus", tmp_path / "catalogs"
    monkeypatch.setattr(dg, "CORPUS_ROOT", str(corpus))
    monkeypatch.setattr(dg, "CATALOG_ROOT", str(catalogs))
    return corpus, catalogs


def test_catalog_sync_records_uncatalogued_books(tmp_path: Path, monkeypatch):
    """The repair case: books on disk, catalog empty."""
    corpus, catalogs = _sync_corpus(tmp_path, monkeypatch)
    _make_downloaded_book(corpus / "letters", "Letters on England", 2445)
    _make_downloaded_book(corpus / "letters", "Letters of Pliny the Younger", 2811)

    assert dg.run_catalog_sync(["letters"]) == 2
    assert sorted(parse_catalog(str(catalogs / "letters.txt"))) == [
        (2445, "Letters on England"),
        (2811, "Letters of Pliny the Younger"),
    ]


def test_catalog_sync_is_idempotent(tmp_path: Path, monkeypatch):
    """Re-running must add nothing and must not duplicate lines."""
    corpus, catalogs = _sync_corpus(tmp_path, monkeypatch)
    _make_downloaded_book(corpus / "letters", "Letters on England", 2445)

    assert dg.run_catalog_sync(["letters"]) == 1
    assert dg.run_catalog_sync(["letters"]) == 0
    assert parse_catalog(str(catalogs / "letters.txt")) == [(2445, "Letters on England")]


def test_catalog_sync_dry_run_counts_but_writes_nothing(tmp_path: Path, monkeypatch):
    corpus, catalogs = _sync_corpus(tmp_path, monkeypatch)
    _make_downloaded_book(corpus / "letters", "Letters on England", 2445)

    assert dg.run_catalog_sync(["letters"], dry_run=True) == 1
    assert not catalogs.exists()


def test_catalog_sync_preserves_existing_entries(tmp_path: Path, monkeypatch):
    """Sync appends; it must never rewrite or reorder a curated catalog."""
    corpus, catalogs = _sync_corpus(tmp_path, monkeypatch)
    catalogs.mkdir()
    (catalogs / "letters.txt").write_text(
        "# curated header\n2811\tLetters of Pliny the Younger\n", encoding="utf-8"
    )
    _make_downloaded_book(corpus / "letters", "Letters on England", 2445)

    dg.run_catalog_sync(["letters"])
    text = (catalogs / "letters.txt").read_text(encoding="utf-8")
    assert text.startswith("# curated header\n2811\t")
    assert text.endswith("2445\tLetters on England\n")


def test_catalog_sync_skips_ia_genres(tmp_path: Path, monkeypatch):
    """IA genres have no catalogs by design and must not get one."""
    corpus, catalogs = _sync_corpus(tmp_path, monkeypatch)
    monkeypatch.setattr("gutenberg_kg.genres.IA_GENRES", ["curiosities"])
    _make_downloaded_book(corpus / "curiosities", "Miracle Mongers", 999)

    assert dg.run_catalog_sync(["curiosities"]) == 0
    assert not catalogs.exists()


def test_catalog_sync_ignores_books_without_an_id(tmp_path: Path, monkeypatch):
    """A reference.md with no Gutenberg ID cannot be catalogued by ID."""
    corpus, catalogs = _sync_corpus(tmp_path, monkeypatch)
    book = corpus / "letters" / "Mystery Book"
    book.mkdir(parents=True)
    (book / "mystery_book.md").write_text("Body.", encoding="utf-8")
    (book / "reference.md").write_text("# Reference: Mystery Book\n", encoding="utf-8")

    assert dg.run_catalog_sync(["letters"]) == 0


def test_catalog_sync_title_matches_directory_so_audit_stays_clean(tmp_path, monkeypatch):
    """The written title must be the directory name, since audit errors when a
    catalog title differs from the directory it names."""
    corpus, catalogs = _sync_corpus(tmp_path, monkeypatch)
    _make_downloaded_book(corpus / "drama", "The sea-gull", 1754)

    dg.run_catalog_sync(["drama"])
    assert parse_catalog(str(catalogs / "drama.txt")) == [(1754, "The sea-gull")]
