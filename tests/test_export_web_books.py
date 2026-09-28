"""Unit tests for gutenberg_kg.export_web_books and `gutenkg export-web-books`.

Chapters must come out the way the worker's ``get_chapter`` builds them, keyed
by the catalog's slug. Tests build a tiny corpus and tiny packs in tmp_path.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from gutenberg_kg.cli.main import cli

PASSAGES = (
    "CREATE TABLE passages (id TEXT, kg_name TEXT, kind TEXT, name TEXT, node_title TEXT, "
    "file_path TEXT, char_start INTEGER, chapter INTEGER, timestamp TEXT, content TEXT)"
)


def _book_dir(corpus: Path, genre: str, book: str, title: str, kg: str = ".dockg") -> None:
    d = corpus / genre / book
    (d / kg).mkdir(parents=True)
    (d / kg / "graph.sqlite").write_bytes(b"x" * 200)
    (d / "reference.md").write_text(f"# Reference: {title}\n", encoding="utf-8")


def _packs(tmp_path: Path) -> tuple[Path, Path]:
    corpus, packs = tmp_path / "corpus", tmp_path / "packs"
    packs.mkdir()
    _book_dir(corpus, "shakespeare", "Hamlet", "Hamlet")
    _book_dir(corpus, "sacred-texts", "Tao", "Tao Te Ching")
    _book_dir(corpus, "diaries", "The Diary of Samuel Pepys — Complete", "Pepys", ".diarykg")
    _book_dir(corpus, "drama", "Unpacked", "Unpacked")

    with sqlite3.connect(packs / "core.pack") as con:
        con.execute("CREATE TABLE books (key TEXT, genre TEXT, book TEXT, file_path TEXT)")
        con.executemany(
            "INSERT INTO books VALUES (?,?,?,?)",
            [
                ("shakespeare/Hamlet", "shakespeare", "Hamlet", "hamlet.md"),
                ("sacred-texts/Tao", "sacred-texts", "Tao", "tao.md"),
                ("diaries/Pepys", "diaries", "The Diary of Samuel Pepys — Complete", None),
            ],
        )
    row = "INSERT INTO passages VALUES (?,?,?,?,?,?,?,?,?,?)"
    with sqlite3.connect(packs / "gutenberg.pack") as con:
        con.execute(PASSAGES)
        con.executemany(
            row,
            [
                ("g:s2", "gutenberg", "section", "s2", "Act II", "hamlet.md", 100, None, None, ""),
                ("g:s1", "gutenberg", "section", "s1", "Act I", "hamlet.md", 10, None, None, ""),
                ("g:c0", "gutenberg", "chunk", "c0", None, "hamlet.md", 0, None, None, "front"),
                ("g:c2", "gutenberg", "chunk", "c2", None, "hamlet.md", 50, None, None, "ghost"),
                ("g:c1", "gutenberg", "chunk", "c1", None, "hamlet.md", 10, None, None, "who"),
                ("g:c3", "gutenberg", "chunk", "c3", None, "hamlet.md", 100, None, None, "words"),
                ("g:t1", "gutenberg", "chunk", "t1", None, "tao.md", 0, 1, None, "way"),
                ("g:t2", "gutenberg", "chunk", "t2", None, "tao.md", 5, 2, None, "name"),
                ("g:t3", "gutenberg", "chunk", "t3", None, "tao.md", 9, 2, None, "named"),
            ],
        )
    with sqlite3.connect(packs / "diaries.pack") as con:
        con.execute(PASSAGES)
        con.executemany(
            row,
            [
                (
                    "p:b",
                    "pepys-complete",
                    "chunk",
                    "b",
                    None,
                    "e1.md",
                    0,
                    None,
                    "1660-01-02T00:00",
                    "two",
                ),
                (
                    "p:a2",
                    "pepys-complete",
                    "chunk",
                    "a2",
                    None,
                    "e0.md",
                    9,
                    None,
                    "1660-01-01T00:00",
                    "one b",
                ),
                (
                    "p:a1",
                    "pepys-complete",
                    "chunk",
                    "a1",
                    None,
                    "e0.md",
                    0,
                    None,
                    "1660-01-01T00:00",
                    "one a",
                ),
            ],
        )
    return corpus, packs


def _export(tmp_path: Path) -> tuple[Path, object]:
    corpus, packs = _packs(tmp_path)
    out = tmp_path / "books"
    result = CliRunner().invoke(
        cli, ["export-web-books", "--corpus", str(corpus), "--packs", str(packs), "--out", str(out)]
    )
    return out, result


def _chapters(out: Path, slug: str) -> list[dict]:
    return json.loads((out / f"{slug}.json").read_text(encoding="utf-8"))["chapters"]


class TestExportWebBooks:
    def test_sections_split_chunks_like_the_worker(self, tmp_path: Path):
        out, result = _export(tmp_path)
        assert result.exit_code == 0, result.output
        # Chunks before the first section stay out, as in _get_chapter.
        assert _chapters(out, "hamlet") == [
            {"title": "Act I", "text": "who\n\nghost"},
            {"title": "Act II", "text": "words"},
        ]

    def test_verse_book_groups_by_chapter(self, tmp_path: Path):
        out, _ = _export(tmp_path)
        assert _chapters(out, "tao_te_ching") == [
            {"title": "Chapter 1", "text": "way"},
            {"title": "Chapter 2", "text": "name\n\nnamed"},
        ]

    def test_diary_chapters_are_dated_entries(self, tmp_path: Path):
        out, _ = _export(tmp_path)
        assert _chapters(out, "pepys") == [
            {"title": "January 1, 1660", "text": "one a\n\none b"},
            {"title": "January 2, 1660", "text": "two"},
        ]

    def test_reports_books_without_text_and_removes_stale_files(self, tmp_path: Path):
        out = tmp_path / "books"
        out.mkdir()
        (out / "gone.json").write_text("{}", encoding="utf-8")
        out, result = _export(tmp_path)
        assert "no text in the packs: drama/Unpacked" in result.output
        assert sorted(p.name for p in out.iterdir()) == [
            "hamlet.json",
            "pepys.json",
            "tao_te_ching.json",
        ]

    def test_missing_packs_is_an_error(self, tmp_path: Path):
        (tmp_path / "corpus").mkdir()
        result = CliRunner().invoke(
            cli,
            ["export-web-books", "--corpus", str(tmp_path / "corpus"), "--packs", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "export-swift" in result.output
