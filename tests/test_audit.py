"""Tests for the corpus audit (gutenberg_kg.audit).

Builds a synthetic ``corpus/`` tree under ``tmp_path`` (so the real corpus is
never touched) and verifies each error class the audit is meant to catch.  The
KGRAG registry is pointed at a non-existent path so registration checks are
skipped — keeping these tests dependency-light.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gutenberg_kg import audit as au

NO_REGISTRY = "/nonexistent/registry.sqlite"  # forces registry_found=False


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Point the audit module at an empty synthetic corpus root (and an empty
    synthetic catalog dir, so the real scripts/catalogs/ never leaks in)."""
    root = tmp_path / "corpus"
    root.mkdir()
    catalogs = tmp_path / "catalogs"
    catalogs.mkdir()
    monkeypatch.setattr(au, "CORPUS_ROOT", root)
    monkeypatch.setattr(au, "CATALOG_ROOT", catalogs)
    return root


def _make_book(
    corpus_root: Path,
    genre: str,
    name: str,
    *,
    ebook_id=42,
    md=True,
    ref=True,
    summary_title=None,
) -> Path:
    book = corpus_root / genre / name
    book.mkdir(parents=True)
    if md:
        (book / f"{name.lower().replace(' ', '_')}.md").write_text("Body text.", encoding="utf-8")
    if ref:
        text = f"# Reference: {name}\n\n- **Project Gutenberg ID**: {ebook_id}\n"
        if summary_title is not None:
            text += f'\n## Summary\n\n"{summary_title}" by Some Author is a book.\n'
        (book / "reference.md").write_text(text, encoding="utf-8")
    return book


def _errors(report, book_name):
    return next(b.errors for b in report.books if b.book == book_name)


def test_clean_prose_book_has_no_errors(corpus):
    _make_book(corpus, "philosophy", "Apology")
    report = au.audit_corpus(["philosophy"], registry=NO_REGISTRY)
    assert report.n_errors == 0


def test_missing_md_is_error(corpus):
    _make_book(corpus, "philosophy", "NoText", md=False)
    report = au.audit_corpus(["philosophy"], registry=NO_REGISTRY)
    assert any("missing full-text .md" in e for e in _errors(report, "NoText"))


def test_missing_reference_is_error(corpus):
    _make_book(corpus, "philosophy", "NoRef", ref=False)
    report = au.audit_corpus(["philosophy"], registry=NO_REGISTRY)
    assert any("missing reference.md" in e for e in _errors(report, "NoRef"))


def test_duplicate_gutenberg_id_flags_both_books(corpus):
    _make_book(corpus, "philosophy", "BookA", ebook_id=1497)
    _make_book(corpus, "ancient-classical", "BookB", ebook_id=1497)
    report = au.audit_corpus(["philosophy", "ancient-classical"], registry=NO_REGISTRY)
    assert any("duplicate Gutenberg ID 1497" in e for e in _errors(report, "BookA"))
    assert any("duplicate Gutenberg ID 1497" in e for e in _errors(report, "BookB"))


def test_diary_stray_dockg_is_error(corpus):
    book = _make_book(corpus, "diaries", "Pepys")
    (book / ".diary_format").write_text("pepys", encoding="utf-8")
    # parseable diary content so the only error is the stray .dockg
    (book / "pepys.md").write_text(
        "JANUARY 1659-1660\n\nJan. 1st (Lord's day). This morning I rose early today.\n",
        encoding="utf-8",
    )
    (book / ".dockg").mkdir()
    report = au.audit_corpus(["diaries"], registry=NO_REGISTRY)
    assert any("stray .dockg/" in e for e in _errors(report, "Pepys"))


def test_diary_unparseable_with_format_is_error(corpus):
    book = _make_book(corpus, "diaries", "BadFormat")
    (book / ".diary_format").write_text("pepys", encoding="utf-8")
    # Prose with no Pepys-style date headers → 0 entries under the pepys format.
    (book / "badformat.md").write_text(
        "There are no dated diary entries anywhere in this plain text.\n",
        encoding="utf-8",
    )
    report = au.audit_corpus(["diaries"], registry=NO_REGISTRY)
    assert any("0 entries" in e for e in _errors(report, "BadFormat"))


def test_title_content_mismatch_is_error(corpus):
    # Reference titled one book, but the summary (from the real text) names a
    # completely different one → wrong Gutenberg ID contamination.
    _make_book(
        corpus,
        "english-literature",
        "Howards End",
        ebook_id=5765,
        summary_title="Insectivorous Plants",
    )
    report = au.audit_corpus(["english-literature"], registry=NO_REGISTRY)
    assert any("title/content mismatch" in e for e in _errors(report, "Howards End"))


def test_title_variant_is_not_flagged(corpus):
    # A fuller canonical title for the same work must not be flagged.
    _make_book(
        corpus,
        "philosophy",
        "Politics",
        ebook_id=99,
        summary_title="Politics: A Treatise on Government",
    )
    report = au.audit_corpus(["philosophy"], registry=NO_REGISTRY)
    assert report.n_errors == 0


def test_allowlisted_id_suppresses_mismatch(corpus):
    # An allowlisted ebook_id (known alternate-title work) is never flagged,
    # even when the titles diverge completely.
    allowed = next(iter(au.KNOWN_TITLE_VARIANTS))
    _make_book(
        corpus,
        "sacred-texts",
        "The Quran",
        ebook_id=allowed,
        summary_title="Something Entirely Different",
    )
    report = au.audit_corpus(["sacred-texts"], registry=NO_REGISTRY)
    assert report.n_errors == 0


def test_catalog_title_drift_is_error(corpus, tmp_path):
    _make_book(corpus, "drama", "The sea-gull", ebook_id=1754)
    (tmp_path / "catalogs" / "drama.txt").write_text(
        "1754\tThe Seagull — Anton Chekhov\n", encoding="utf-8"
    )
    report = au.audit_corpus(["drama"], registry=NO_REGISTRY)
    assert any("catalog title" in e for e in _errors(report, "The sea-gull"))


def test_catalog_title_match_is_clean(corpus, tmp_path):
    _make_book(corpus, "drama", "The sea-gull", ebook_id=1754)
    (tmp_path / "catalogs" / "drama.txt").write_text("1754\tThe sea-gull\n", encoding="utf-8")
    report = au.audit_corpus(["drama"], registry=NO_REGISTRY)
    assert report.n_errors == 0


def test_catalog_entry_not_yet_downloaded_is_ignored(corpus, tmp_path):
    """A catalog line whose book has no directory yet is a wishlist entry,
    not drift."""
    _make_book(corpus, "drama", "The sea-gull", ebook_id=1754)
    (tmp_path / "catalogs" / "drama.txt").write_text(
        "1754\tThe sea-gull\n9999\tNot Downloaded Yet\n", encoding="utf-8"
    )
    report = au.audit_corpus(["drama"], registry=NO_REGISTRY)
    assert report.n_errors == 0


def test_catalog_id_only_line_is_ignored(corpus, tmp_path):
    """A line without a title override has nothing to drift from."""
    _make_book(corpus, "drama", "The sea-gull", ebook_id=1754)
    (tmp_path / "catalogs" / "drama.txt").write_text("1754\n", encoding="utf-8")
    report = au.audit_corpus(["drama"], registry=NO_REGISTRY)
    assert report.n_errors == 0


def test_catalog_title_unicode_normalization(corpus, tmp_path):
    """NFC/NFD variants of the same name (macOS filesystems return NFD) must
    not be flagged as drift."""
    import unicodedata

    name = "Faust: Der Tragödie zweiter Teil"
    _make_book(corpus, "german-literature", unicodedata.normalize("NFD", name), ebook_id=2230)
    (tmp_path / "catalogs" / "german-literature.txt").write_text(
        f"2230\t{unicodedata.normalize('NFC', name)}\n", encoding="utf-8"
    )
    report = au.audit_corpus(["german-literature"], registry=NO_REGISTRY)
    assert report.n_errors == 0


def test_run_audit_exit_code(corpus):
    _make_book(corpus, "philosophy", "NoText", md=False)  # one error
    assert au.run_audit(["philosophy"], registry=NO_REGISTRY) == 1
    # a clean corpus exits 0
    for p in (corpus / "philosophy" / "NoText").glob("*"):
        p.unlink()
    (corpus / "philosophy" / "NoText").rmdir()
    _make_book(corpus, "philosophy", "Clean")
    assert au.run_audit(["philosophy"], registry=NO_REGISTRY) == 0
