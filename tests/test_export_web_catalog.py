"""Unit tests for scripts/export_web_catalog.py.

The script must count ``kind='chunk'`` nodes the same way ForestLayout does,
and it must keep BookMeta slugs so Hamlet stays ``hamlet``. Tests build a
tiny corpus tree in tmp_path — they do not touch the real ``corpus/``.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_web_catalog.py"
_spec = importlib.util.spec_from_file_location("export_web_catalog", _SCRIPT)
assert _spec is not None and _spec.loader is not None
export_web_catalog = importlib.util.module_from_spec(_spec)
sys.modules["export_web_catalog"] = export_web_catalog
_spec.loader.exec_module(export_web_catalog)


def _write_book(
    root: Path, genre: str, folder: str, *, title: str, author: str, chunks: list[str]
) -> Path:
    book_dir = root / genre / folder
    kg = book_dir / ".dockg"
    kg.mkdir(parents=True)
    (book_dir / "reference.md").write_text(
        f"# Reference: {title}\n\n## Author\n- **Name**: {author}\n",
        encoding="utf-8",
    )
    db = kg / "graph.sqlite"
    with sqlite3.connect(str(db)) as con:
        con.execute(
            "CREATE TABLE nodes (id TEXT, kind TEXT, name TEXT, title TEXT, file_path TEXT, text TEXT)"
        )
        con.execute(
            "INSERT INTO nodes VALUES ('doc','document',?,?,?,?)",
            (title, title, f"{folder}.md", None),
        )
        for i, text in enumerate(chunks):
            con.execute(
                "INSERT INTO nodes VALUES (?,?,?,?,?,?)",
                (f"c{i}", "chunk", f"chunk {i}", f"chunk {i}", f"{folder}.md", text),
            )
        con.commit()
    return book_dir


class TestSlug:
    def test_hamlet_matches_bookmeta(self):
        assert export_web_catalog.slug_from_title("Hamlet") == "hamlet"

    def test_strips_punctuation_and_caps_length(self):
        assert (
            export_web_catalog.slug_from_title("A Selection from the Discourses of Epictetus!")[:20]
            == "a_selection_from_the"
        )


class TestScan:
    def test_counts_chunk_nodes(self, tmp_path: Path):
        _write_book(
            tmp_path,
            "shakespeare",
            "Hamlet",
            title="Hamlet",
            author="William Shakespeare",
            chunks=["To be, or not to be, that is the question."] * 420,
        )
        books = export_web_catalog.scan_corpus(tmp_path)
        assert len(books) == 1
        assert books[0].slug == "hamlet"
        assert books[0].chunks == 420
        assert books[0].author == "William Shakespeare"
        assert books[0].genre == "shakespeare"

    def test_skips_books_without_a_graph(self, tmp_path: Path):
        (tmp_path / "philosophy" / "Notes").mkdir(parents=True)
        assert export_web_catalog.scan_corpus(tmp_path) == []

    def test_writes_split_catalog(self, tmp_path: Path):
        _write_book(
            tmp_path,
            "philosophy",
            "Meditations",
            title="Meditations",
            author="Marcus Aurelius",
            chunks=["You have power over your mind — not outside events."] * 12,
        )
        books = export_web_catalog.scan_corpus(tmp_path)
        out = tmp_path / "game"
        n = export_web_catalog.write_catalog(books, out)
        assert n == 1
        text = (out / "catalogPart1.ts").read_text(encoding="utf-8")
        assert "chunks: 12" in text
        assert "meditations" in text
        barrel = (out / "catalog.ts").read_text(encoding="utf-8")
        assert "BOOKS_PART1" in barrel


class TestCli:
    def test_dry_run_does_not_write(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        _write_book(
            tmp_path,
            "philosophy",
            "The Republic",
            title="The Republic",
            author="Plato",
            chunks=["What is justice?"] * 5,
        )
        out = tmp_path / "game"
        rc = export_web_catalog.main(["--corpus", str(tmp_path), "--out", str(out), "--dry-run"])
        assert rc == 0
        assert not out.exists()
        assert "1 books" in capsys.readouterr().out

    def test_missing_corpus_is_an_error(self, tmp_path: Path):
        rc = export_web_catalog.main(["--corpus", str(tmp_path / "nope"), "--dry-run"])
        assert rc == 1
