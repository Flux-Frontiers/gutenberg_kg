"""Unit tests for gutenberg_kg.export_web and `gutenkg export-web-catalog`.

The export must count ``kind='chunk'`` nodes the same way ForestLayout does,
and it must keep BookMeta slugs so Hamlet stays ``hamlet``. Tests build a
tiny corpus tree in tmp_path — they do not touch the real ``corpus/``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from gutenberg_kg import export_web as export_web_catalog
from gutenberg_kg.cli.main import cli


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

    def test_book_key_is_the_folder_name(self, tmp_path: Path):
        # The worker keys books by folder; the reference title can differ.
        _write_book(
            tmp_path,
            "american-literature",
            "The Sea-Wolf (London)",
            title="The Sea-Wolf",
            author="Jack London",
            chunks=["The sea was calm."],
        )
        (row,) = export_web_catalog.scan_corpus(tmp_path)
        assert row.title == "The Sea-Wolf"
        assert row.book == "The Sea-Wolf (London)"

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
    def test_dry_run_does_not_write(self, tmp_path: Path):
        _write_book(
            tmp_path,
            "philosophy",
            "The Republic",
            title="The Republic",
            author="Plato",
            chunks=["What is justice?"] * 5,
        )
        out = tmp_path / "game"
        result = CliRunner().invoke(
            cli, ["export-web-catalog", "--corpus", str(tmp_path), "--out", str(out), "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert not out.exists()
        assert "1 books" in result.output

    def test_missing_corpus_is_an_error(self, tmp_path: Path):
        result = CliRunner().invoke(
            cli, ["export-web-catalog", "--corpus", str(tmp_path / "nope"), "--dry-run"]
        )
        assert result.exit_code == 1
        assert "no corpus" in result.output


class TestWrite:
    def test_cli_writes_the_catalog(self, tmp_path: Path):
        _write_book(
            tmp_path,
            "philosophy",
            "Meditations",
            title="Meditations",
            author="Marcus Aurelius",
            chunks=["Waste no more time arguing what a good man should be."] * 3,
        )
        out = tmp_path / "game"
        result = CliRunner().invoke(
            cli, ["export-web-catalog", "--corpus", str(tmp_path), "--out", str(out)]
        )
        assert result.exit_code == 0, result.output
        assert f"wrote {out / 'catalog.ts'} and 1 part(s)" in result.output
        assert "chunks: 3" in (out / "catalogPart1.ts").read_text(encoding="utf-8")
        assert "gutenkg export-web-catalog" in (out / "catalog.ts").read_text(encoding="utf-8")
        assert (out / "catalogTypes.ts").exists()

    def test_corpus_without_graphs_is_an_error(self, tmp_path: Path):
        (tmp_path / "philosophy" / "Notes").mkdir(parents=True)
        result = CliRunner().invoke(
            cli, ["export-web-catalog", "--corpus", str(tmp_path), "--dry-run"]
        )
        assert result.exit_code == 1
        assert "no books with graph.sqlite" in result.output

    def test_fewer_books_removes_leftover_parts(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(export_web_catalog, "PART_SIZE", 1)
        rows = [
            export_web_catalog.BookRow(
                slug=s,
                title=s,
                book=s,
                author="A",
                genre="drama",
                genre_label="Drama",
                chunks=1,
                excerpt="",
            )
            for s in ("a", "b")
        ]
        out = tmp_path / "game"
        assert export_web_catalog.write_catalog(rows, out) == 2
        assert (out / "catalogPart2.ts").exists()
        assert export_web_catalog.write_catalog(rows[:1], out) == 1
        assert not (out / "catalogPart2.ts").exists()
        assert "BOOKS_PART2" not in (out / "catalog.ts").read_text(encoding="utf-8")

    def test_diary_periods_are_written(self):
        row = export_web_catalog.BookRow(
            slug="pepys",
            title="Pepys",
            book="Pepys",
            author="Samuel Pepys",
            genre="diaries",
            genre_label="Diaries",
            chunks=2,
            excerpt="",
            periods=[{"label": "1660", "entries": 2, "bins": [1, 0, 1]}],
        )
        text = export_web_catalog.emit_part([row], 1)
        assert '{ label: "1660", entries: 2, bins: [1,0,1] },' in text
