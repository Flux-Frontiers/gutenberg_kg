"""Unit tests for gutenberg_kg.authors — pure-function coverage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import gutenberg_kg.authors as authors_mod
from gutenberg_kg.authors import (
    _field,
    _slugify,
    parse_reference,
    patch_reference,
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
# patch_reference
# ---------------------------------------------------------------------------


def test_patch_reference_inserts_missing_fields(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(MINIMAL_REFERENCE, encoding="utf-8")

    extra = {"author_birth": "1819", "author_death": "1891"}
    changed = patch_reference(p, extra, dry_run=False)

    assert changed is True
    content = p.read_text(encoding="utf-8")
    assert "**Born**: 1819" in content
    assert "**Died**: 1891" in content


def test_patch_reference_no_change_when_already_present(full_ref: Path):
    extra = {"author_birth": "1819", "author_death": "1891"}
    changed = patch_reference(full_ref, extra, dry_run=False)
    assert changed is False


def test_patch_reference_dry_run_does_not_write(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text(MINIMAL_REFERENCE, encoding="utf-8")
    original = p.read_text(encoding="utf-8")

    extra = {"author_birth": "1819"}
    patch_reference(p, extra, dry_run=True)

    assert p.read_text(encoding="utf-8") == original


def test_patch_reference_returns_false_when_no_name_line(tmp_path: Path):
    p = tmp_path / "reference.md"
    p.write_text("# Reference: No Author Section\n\nSome text.\n", encoding="utf-8")
    extra = {"author_birth": "1819"}
    changed = patch_reference(p, extra, dry_run=False)
    assert changed is False


def test_patch_reference_returns_false_with_empty_extra(minimal_ref: Path):
    changed = patch_reference(minimal_ref, {}, dry_run=False)
    assert changed is False


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
