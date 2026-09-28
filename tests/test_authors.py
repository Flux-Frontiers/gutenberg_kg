"""Unit tests for gutenberg_kg.authors — pure-function coverage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import gutenberg_kg.authors as authors_mod
from gutenberg_kg.authors import (
    _field,
    _slugify,
    author_lines,
    build,
    credit,
    display_name,
    parse_reference,
    rewrite_author_section,
    write_author_page,
    write_index,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_REFERENCE = """\
# Reference: Moby Dick

## Book

- **Project Gutenberg ID**: 2701

## Author

- **Name**: Herman Melville
"""

FULL_REFERENCE = """\
# Reference: Moby Dick

## Book

- **Project Gutenberg ID**: 2701

## Author

- **Name**: Herman Melville
- **Born**: 1819
- **Died**: 1891
- **Wikipedia**: https://en.wikipedia.org/wiki/Herman_Melville
- **Gutenberg Agent ID**: 9
"""


@pytest.fixture
def minimal_ref(tmp_path: Path) -> Path:
    p = tmp_path / "reference.md"
    p.write_text(MINIMAL_REFERENCE, encoding="utf-8")
    return p


@pytest.fixture
def full_ref(tmp_path: Path) -> Path:
    p = tmp_path / "reference.md"
    p.write_text(FULL_REFERENCE, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


def test_slugify_simple_name():
    assert _slugify("Herman Melville") == "herman_melville"


def test_slugify_lowercase():
    assert _slugify("HOMER") == "homer"


def test_slugify_strips_punctuation():
    assert _slugify("Tolstoy, Leo") == "tolstoy_leo"


def test_slugify_collapses_spaces():
    assert _slugify("Victor  Hugo") == "victor_hugo"


def test_slugify_handles_hyphen():
    # _slugify collapses hyphens and spaces to underscores
    assert _slugify("Jean-Paul Sartre") == "jean_paul_sartre"


def test_slugify_strips_leading_trailing_underscores():
    assert not _slugify("Homer").startswith("_")
    assert not _slugify("Homer").endswith("_")


# ---------------------------------------------------------------------------
# _field
# ---------------------------------------------------------------------------


def test_field_finds_match():
    text = "- **Name**: Herman Melville\n"
    assert _field(r"\*\*Name\*\*:\s*(.+)$", text) == "Herman Melville"


def test_field_returns_none_on_no_match():
    assert _field(r"\*\*Born\*\*:\s*(.+)$", "no dates here") is None


def test_field_strips_whitespace():
    text = "- **Name**:   Herman Melville   \n"
    result = _field(r"\*\*Name\*\*:\s*(.+)$", text)
    assert result == "Herman Melville"


# ---------------------------------------------------------------------------
# parse_reference
# ---------------------------------------------------------------------------


def test_parse_reference_extracts_title(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(FULL_REFERENCE, encoding="utf-8")
    meta = parse_reference(p)
    assert meta["title"] == "Moby Dick"


def test_parse_reference_extracts_ebook_id(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(FULL_REFERENCE, encoding="utf-8")
    meta = parse_reference(p)
    assert meta["ebook_id"] == 2701


def test_parse_reference_extracts_author(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(FULL_REFERENCE, encoding="utf-8")
    meta = parse_reference(p)
    assert meta["author"] == "Herman Melville"


def test_parse_reference_extracts_birth_death(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(FULL_REFERENCE, encoding="utf-8")
    meta = parse_reference(p)
    assert meta["author_birth"] == "1819"
    assert meta["author_death"] == "1891"


def test_parse_reference_extracts_wikipedia(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(FULL_REFERENCE, encoding="utf-8")
    meta = parse_reference(p)
    assert "Herman_Melville" in meta["author_url"]


def test_parse_reference_extracts_agent_id(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(FULL_REFERENCE, encoding="utf-8")
    meta = parse_reference(p)
    assert meta["author_agent_id"] == 9


def test_parse_reference_genre_from_grandparent(tmp_path: Path):
    genre_dir = tmp_path / "english-literature"
    book_dir = genre_dir / "moby-dick"
    book_dir.mkdir(parents=True)
    p = book_dir / "reference.md"
    p.write_text(FULL_REFERENCE, encoding="utf-8")
    meta = parse_reference(p)
    assert meta["genre"] == "english-literature"


def test_parse_reference_minimal_no_author(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text("# Reference: Unknown\n", encoding="utf-8")
    meta = parse_reference(p)
    assert meta["author"] is None
    assert meta["ebook_id"] is None


# ---------------------------------------------------------------------------
# display_name / credit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        # Every shape below is a real Gutenberg heading from the corpus.
        ("Dumas, Alexandre", "Alexandre Dumas"),
        ("Goethe, Johann Wolfgang von", "Johann Wolfgang von Goethe"),
        ("Cervantes Saavedra, Miguel de", "Miguel de Cervantes Saavedra"),
        ("Wells, H. G. (Herbert George)", "H. G. Wells"),
        ("Du Bois, W. E. B. (William Edward Burghardt)", "W. E. B. Du Bois"),
        ("Tolstoy, Leo, graf", "Leo Tolstoy"),
        ("Seaborn, Adam, Captain", "Adam Seaborn"),
        ("Marcus Aurelius, Emperor of Rome", "Marcus Aurelius"),
        ("Sunzi, active 6th century B.C.", "Sunzi"),
        ("Pliny, the Younger", "Pliny the Younger"),
        ("Rusticiano, da Pisa", "Rusticiano da Pisa"),
        ("Augustine, of Hippo, Saint", "Augustine of Hippo"),
        ("Byron, George Gordon Byron, Baron", "George Gordon Byron, Baron Byron"),
        ("Lytton, Edward Bulwer Lytton, Baron", "Edward Bulwer Lytton, Baron Lytton"),
        (
            "Chesterfield, Philip Dormer Stanhope, Earl of",
            "Philip Dormer Stanhope, Earl of Chesterfield",
        ),
        ("Homer", "Homer"),
        ("Dante Alighieri", "Dante Alighieri"),
        ("Dumas, Alexandre, 1802-1870", "Alexandre Dumas"),
    ],
)
def test_display_name(heading: str, expected: str):
    assert display_name(heading) == expected


def test_display_name_keeps_a_heading_nothing_survives():
    assert display_name("1802-1870") == "1802-1870"


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ([], ""),
        (["Jane Austen"], "Jane Austen"),
        (["Alexandre Dumas", "Auguste Maquet"], "Alexandre Dumas and Auguste Maquet"),
        (
            ["Alexander Hamilton", "John Jay", "James Madison"],
            "Alexander Hamilton, John Jay, and James Madison",
        ),
    ],
)
def test_credit(names: list[str], expected: str):
    assert credit(names) == expected


# ---------------------------------------------------------------------------
# author_lines / co-authors
# ---------------------------------------------------------------------------

DUMAS = {
    "authors": ["Alexandre Dumas", "Auguste Maquet"],
    "author_birth": "1802",
    "author_death": "1870",
    "author_url": "https://en.wikipedia.org/wiki/Alexandre_Dumas",
    "author_agent_id": 492,
}


def test_author_lines_give_provenance_to_the_first_author_only():
    assert author_lines(DUMAS) == [
        "- **Name**: Alexandre Dumas",
        "- **Born**: 1802",
        "- **Died**: 1870",
        "- **Wikipedia**: https://en.wikipedia.org/wiki/Alexandre_Dumas",
        "- **Gutenberg Agent ID**: 492",
        "- **Co-author**: Auguste Maquet",
    ]


def test_author_lines_fall_back_to_a_single_author():
    assert author_lines({"author": "Herman Melville"}) == ["- **Name**: Herman Melville"]


def test_author_lines_empty_without_an_author():
    assert author_lines({"title": "The Bible"}) == []


def test_parse_reference_reads_co_authors_into_the_byline(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(
        "# Reference: The Count of Monte Cristo\n\n## Author\n\n"
        + "\n".join(author_lines(DUMAS))
        + "\n",
        encoding="utf-8",
    )
    meta = parse_reference(p)
    assert meta["authors"] == ["Alexandre Dumas", "Auguste Maquet"]
    assert meta["author"] == "Alexandre Dumas and Auguste Maquet"
    assert meta["author_birth"] == "1802"


def test_parse_reference_single_author_is_unchanged(full_ref: Path):
    meta = parse_reference(full_ref)
    assert meta["authors"] == ["Herman Melville"]
    assert meta["author"] == "Herman Melville"


# ---------------------------------------------------------------------------
# rewrite_author_section
# ---------------------------------------------------------------------------

MONTE_CRISTO = """\
# Reference: The Count of Monte Cristo

## Source

- **Project Gutenberg ID**: 1184

## Author

- **Name**: Auguste Maquet
- **Born**: 1802
- **Died**: 1870
- **Gutenberg Agent ID**: 492

- **Gutenberg Published**: 1998-01-01

## Language

- en
"""


def test_rewrite_replaces_only_the_author_lines(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(MONTE_CRISTO, encoding="utf-8")

    assert rewrite_author_section(p, DUMAS) is True

    expected = MONTE_CRISTO.replace(
        "- **Name**: Auguste Maquet\n- **Born**: 1802\n- **Died**: 1870\n"
        "- **Gutenberg Agent ID**: 492\n",
        "\n".join(author_lines(DUMAS)) + "\n",
    )
    assert p.read_text(encoding="utf-8") == expected


def test_rewrite_is_idempotent(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(MONTE_CRISTO, encoding="utf-8")
    rewrite_author_section(p, DUMAS)
    once = p.read_text(encoding="utf-8")

    assert rewrite_author_section(p, DUMAS) is False
    assert p.read_text(encoding="utf-8") == once


def test_rewrite_dry_run_does_not_write(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(MONTE_CRISTO, encoding="utf-8")

    assert rewrite_author_section(p, DUMAS, dry_run=True) is True
    assert p.read_text(encoding="utf-8") == MONTE_CRISTO


def test_rewrite_never_erases_an_author_when_the_fetch_found_none(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(MONTE_CRISTO, encoding="utf-8")

    assert rewrite_author_section(p, {}) is False
    assert p.read_text(encoding="utf-8") == MONTE_CRISTO


def test_rewrite_leaves_a_file_without_a_name_line(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text("# Reference: The Bible\n\n## Source\n", encoding="utf-8")

    assert rewrite_author_section(p, DUMAS) is False


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def _corpus_with_monte_cristo(tmp_path: Path) -> Path:
    book = tmp_path / "corpus" / "french-literature" / "The Count of Monte Cristo"
    book.mkdir(parents=True)
    (book / "reference.md").write_text(MONTE_CRISTO, encoding="utf-8")
    return book / "reference.md"


RDF_FIXTURES = Path(__file__).parent / "fixtures" / "rdf"


def _run_build(tmp_path: Path, monkeypatch, **kwargs) -> None:
    """Run ``build`` over a corpus in *tmp_path*, offline.

    The corpus paths point into *tmp_path* so the real corpus is never
    written. The only stand-in is the HTTP fetch, which serves Gutenberg's
    real RDF record for the book, so parsing and rewriting run as they do
    against the live catalog.
    """
    import gutenberg_kg.gutenberg as gutenberg_mod

    monkeypatch.setattr(authors_mod, "CORPUS_ROOT", tmp_path / "corpus")
    monkeypatch.setattr(authors_mod, "AUTHORS_DIR", tmp_path / "corpus" / "authors")
    monkeypatch.setattr(authors_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        gutenberg_mod,
        "fetch_url",
        lambda url: (RDF_FIXTURES / url.rsplit("/", 1)[1]).read_text(encoding="utf-8"),
    )
    assert build(**kwargs) == 0


def test_build_refresh_rewrites_the_reference_and_indexes_each_author(tmp_path, monkeypatch):
    ref = _corpus_with_monte_cristo(tmp_path)
    _run_build(tmp_path, monkeypatch, refresh=True)

    assert parse_reference(ref)["author"] == "Alexandre Dumas and Auguste Maquet"
    authors_dir = tmp_path / "corpus" / "authors"
    dumas = (authors_dir / "alexandre_dumas" / "author.md").read_text(encoding="utf-8")
    maquet = (authors_dir / "auguste_maquet" / "author.md").read_text(encoding="utf-8")
    assert "The Count of Monte Cristo" in dumas and "The Count of Monte Cristo" in maquet
    # The dates are Dumas's; Maquet's page must not borrow them.
    assert "1802" in dumas
    assert "1802" not in maquet


def test_build_refresh_dry_run_writes_nothing(tmp_path, monkeypatch):
    ref = _corpus_with_monte_cristo(tmp_path)
    _run_build(tmp_path, monkeypatch, refresh=True, dry_run=True)

    assert ref.read_text(encoding="utf-8") == MONTE_CRISTO
    assert not (tmp_path / "corpus" / "authors").exists()


# ---------------------------------------------------------------------------
# write_author_page
# ---------------------------------------------------------------------------


def test_write_author_page_dry_run_returns_path(tmp_path: Path):
    books = [{"title": "Moby Dick", "genre": "english-literature"}]
    with patch.object(authors_mod, "AUTHORS_DIR", tmp_path):
        out = write_author_page("Herman Melville", books, dry_run=True)
    assert out.name == "author.md"
    assert not out.exists()


def test_write_author_page_writes_file(tmp_path: Path):
    books = [
        {
            "title": "Moby Dick",
            "genre": "english-literature",
            "author_birth": "1819",
            "author_death": "1891",
            "author_url": "https://en.wikipedia.org/wiki/Herman_Melville",
            "author_agent_id": 9,
        }
    ]
    with patch.object(authors_mod, "AUTHORS_DIR", tmp_path):
        out = write_author_page("Herman Melville", books, dry_run=False)

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "# Herman Melville" in content
    assert "Moby Dick" in content
    assert "1819" in content
    assert "1891" in content


def test_write_author_page_table_contains_all_books(tmp_path: Path):
    books = [
        {"title": "Moby Dick", "genre": "english-literature"},
        {"title": "Bartleby", "genre": "english-literature"},
    ]
    with patch.object(authors_mod, "AUTHORS_DIR", tmp_path):
        out = write_author_page("Herman Melville", books, dry_run=False)

    content = out.read_text(encoding="utf-8")
    assert "Moby Dick" in content
    assert "Bartleby" in content


def test_write_author_page_books_sorted_by_title(tmp_path: Path):
    books = [
        {"title": "Moby Dick", "genre": "english-literature"},
        {"title": "Bartleby", "genre": "english-literature"},
    ]
    with patch.object(authors_mod, "AUTHORS_DIR", tmp_path):
        out = write_author_page("Herman Melville", books, dry_run=False)

    content = out.read_text(encoding="utf-8")
    assert content.index("Bartleby") < content.index("Moby Dick")


# ---------------------------------------------------------------------------
# write_index
# ---------------------------------------------------------------------------


def test_write_index_dry_run_returns_path(tmp_path: Path):
    authors_books = {"Herman Melville": [{"title": "Moby Dick", "genre": "eng"}]}
    with patch.object(authors_mod, "AUTHORS_DIR", tmp_path):
        out = write_index(authors_books, dry_run=True)
    assert out.name == "index.md"
    assert not out.exists()


def test_write_index_writes_file(tmp_path: Path):
    authors_books = {
        "Herman Melville": [
            {
                "title": "Moby Dick",
                "genre": "english-literature",
                "author_birth": "1819",
                "author_death": "1891",
            }
        ],
        "Homer": [
            {
                "title": "The Iliad",
                "genre": "ancient-classical",
                "author_birth": None,
                "author_death": None,
            }
        ],
    }
    with patch.object(authors_mod, "AUTHORS_DIR", tmp_path):
        out = write_index(authors_books, dry_run=False)

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Herman Melville" in content
    assert "Homer" in content


def test_write_index_sorted_alphabetically(tmp_path: Path):
    authors_books = {
        "Zola, Émile": [
            {
                "title": "Nana",
                "genre": "french-literature",
                "author_birth": None,
                "author_death": None,
            }
        ],
        "Austen, Jane": [
            {
                "title": "Emma",
                "genre": "english-literature",
                "author_birth": None,
                "author_death": None,
            }
        ],
    }
    with patch.object(authors_mod, "AUTHORS_DIR", tmp_path):
        out = write_index(authors_books, dry_run=False)

    content = out.read_text(encoding="utf-8")
    assert content.index("Austen") < content.index("Zola")


def test_write_index_work_count_column(tmp_path: Path):
    authors_books = {
        "Herman Melville": [
            {"title": "Moby Dick", "genre": "eng", "author_birth": None, "author_death": None},
            {"title": "Bartleby", "genre": "eng", "author_birth": None, "author_death": None},
        ]
    }
    with patch.object(authors_mod, "AUTHORS_DIR", tmp_path):
        out = write_index(authors_books, dry_run=False)

    content = out.read_text(encoding="utf-8")
    assert "| 2 |" in content


def test_build_removes_stale_generated_pages_only(tmp_path, monkeypatch):
    _corpus_with_monte_cristo(tmp_path)
    authors_dir = tmp_path / "corpus" / "authors"
    stale = authors_dir / "leo_graf_tolstoy"
    stale.mkdir(parents=True)
    (stale / "author.md").write_text("# Leo, graf Tolstoy\n", encoding="utf-8")
    kept = authors_dir / "hand_written"
    kept.mkdir()
    (kept / "author.md").write_text("# Kept\n", encoding="utf-8")
    (kept / "notes.md").write_text("Not generated.\n", encoding="utf-8")

    _run_build(tmp_path, monkeypatch, refresh=True)

    assert not stale.exists()
    assert (kept / "notes.md").exists()
    assert (authors_dir / "alexandre_dumas" / "author.md").exists()


def test_build_dry_run_keeps_stale_pages(tmp_path, monkeypatch):
    _corpus_with_monte_cristo(tmp_path)
    stale = tmp_path / "corpus" / "authors" / "leo_graf_tolstoy"
    stale.mkdir(parents=True)
    (stale / "author.md").write_text("# Leo, graf Tolstoy\n", encoding="utf-8")

    _run_build(tmp_path, monkeypatch, dry_run=True)

    assert stale.exists()
