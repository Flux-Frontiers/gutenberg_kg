"""Tests for gutenberg_kg.stale: books whose index is older than their text.

Built on a tmp_path corpus with explicit modification times, so the real
corpus is never read.
"""

from __future__ import annotations

import os
from pathlib import Path

from gutenberg_kg.stale import bundle_is_stale, stale_books

OLD, NEW = 1_000_000.0, 2_000_000.0


def _touch(path: Path, mtime: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _book(corpus: Path, genre: str, name: str, *, text: float, index: float | None) -> Path:
    book = corpus / genre / name
    _touch(book / f"{name.lower()}.md", text)
    _touch(book / "reference.md", text)
    if index is not None:
        _touch(book / ".dockg" / "graph.sqlite", index)
    return book


def test_book_newer_than_its_index_is_stale(tmp_path: Path) -> None:
    book = _book(tmp_path, "philosophy", "Meditations", text=NEW, index=OLD)
    assert stale_books(tmp_path) == [(book, "text newer than index: meditations.md, reference.md")]


def test_current_book_is_not_stale(tmp_path: Path) -> None:
    _book(tmp_path, "philosophy", "Meditations", text=OLD, index=NEW)
    assert stale_books(tmp_path) == []


def test_book_without_an_index_is_stale(tmp_path: Path) -> None:
    book = _book(tmp_path, "horror", "Dracula", text=OLD, index=None)
    assert stale_books(tmp_path) == [(book, "no index")]


def test_diaries_and_authors_are_skipped(tmp_path: Path) -> None:
    _book(tmp_path, "diaries", "Pepys", text=NEW, index=None)
    _touch(tmp_path / "authors" / "plato" / "author.md", NEW)
    assert stale_books(tmp_path) == []


def test_bundle_older_than_a_book_index_is_stale(tmp_path: Path) -> None:
    corpus, bundle = tmp_path / "corpus", tmp_path / "bundle"
    _book(corpus, "philosophy", "Meditations", text=OLD, index=NEW)
    _touch(bundle / ".dockg" / "graph.sqlite", OLD)
    assert bundle_is_stale(corpus, bundle)
    os.utime(bundle / ".dockg" / "graph.sqlite", (NEW + 1, NEW + 1))
    assert not bundle_is_stale(corpus, bundle)


def test_missing_bundle_is_stale(tmp_path: Path) -> None:
    assert bundle_is_stale(tmp_path, tmp_path / "no-bundle")
