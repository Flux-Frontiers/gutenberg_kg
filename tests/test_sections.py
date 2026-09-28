"""Tests for gutenberg_kg.sections: books with most text in one section.

Each book is a tmp_path DocKG store holding only the section and chunk rows
the measurement reads.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from gutenberg_kg import sections as sec
from gutenberg_kg.cli import cmd_audit
from gutenberg_kg.cli.main import cli


def _book(corpus: Path, genre: str, name: str, spans: list[tuple[str, int, int]]) -> None:
    book = corpus / genre / name
    (book / ".dockg").mkdir(parents=True)
    (book / f"{name.lower()}.md").write_text("x", encoding="utf-8")
    (book / "reference.md").write_text("x", encoding="utf-8")
    with sqlite3.connect(book / ".dockg" / "graph.sqlite") as con:
        con.execute(
            "CREATE TABLE nodes (kind TEXT, title TEXT, file_path TEXT, char_start INT, char_end INT)"
        )
        for title, start, end in spans:
            con.execute(
                "INSERT INTO nodes VALUES ('section', ?, ?, ?, ?)",
                (title, f"{name.lower()}.md", start, end),
            )
            con.execute(
                "INSERT INTO nodes VALUES ('chunk', NULL, ?, ?, NULL)",
                (f"{name.lower()}.md", start),
            )


def test_one_giant_section_is_flagged(tmp_path: Path) -> None:
    _book(tmp_path, "horror", "Dunwich", [("Title", 0, 500), ("All of it", 500, 200_500)])
    _book(
        tmp_path,
        "philosophy",
        "Balanced",
        [(f"Ch {i}", i * 50_000, (i + 1) * 50_000) for i in range(4)],
    )
    results = sec.scan_corpus(tmp_path)
    assert [r.book for r in results] == ["Dunwich", "Balanced"]
    (flag,) = sec.flagged(results)
    assert flag.book == "Dunwich"
    assert flag.largest_section_title == "All of it"
    assert flag.sections == 2


def test_short_book_is_not_flagged_even_in_one_section(tmp_path: Path) -> None:
    _book(tmp_path, "drama", "Short", [("Only", 0, 50_000)])
    assert sec.flagged(sec.scan_corpus(tmp_path)) == []


def test_genre_filter(tmp_path: Path) -> None:
    _book(tmp_path, "horror", "Dunwich", [("All", 0, 200_000)])
    _book(tmp_path, "drama", "Short", [("Only", 0, 50_000)])
    assert [r.book for r in sec.scan_corpus(tmp_path, ["drama"])] == ["Short"]


def test_baseline_round_trip_and_changes(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _book(corpus, "horror", "Dunwich", [("A", 0, 1000), ("B", 1000, 2000)])
    csv_path = tmp_path / "baseline.csv"
    sec.write_csv(sec.scan_corpus(corpus), csv_path)
    baseline = sec.load_baseline(csv_path)
    assert baseline == {"Dunwich": 2}
    assert sec.baseline_changes(sec.scan_corpus(corpus), baseline) == []
    assert sec.baseline_changes([], baseline) == [("Dunwich", 2, None)]


class TestAuditCli:
    """`gutenkg audit --sections`: the report rides on the audit's exit code."""

    @pytest.fixture
    def corpus(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        root = tmp_path / "corpus"
        _book(root, "horror", "Dunwich", [("All of it", 0, 200_000)])
        _book(root, "drama", "Short", [("Only", 0, 50_000)])
        monkeypatch.setattr(cmd_audit, "CORPUS_ROOT", root)
        self.audit_genres: list[list[str]] = []
        self.audit_rc = 0

        def fake_run_audit(genres, registry=None, as_json=False):
            self.audit_genres.append(genres)
            return self.audit_rc

        monkeypatch.setattr(cmd_audit.au, "run_audit", fake_run_audit)
        return root

    def test_sections_lists_the_flagged_book(self, corpus: Path) -> None:
        result = CliRunner().invoke(cli, ["audit", "--sections"])
        assert result.exit_code == 0, result.output
        assert "1 books have >90% of their text in a single section" in result.output
        assert "[horror]  Dunwich  -- All of it" in result.output

    def test_without_sections_there_is_no_report(self, corpus: Path) -> None:
        result = CliRunner().invoke(cli, ["audit"])
        assert result.exit_code == 0
        assert "single section" not in result.output

    def test_flagged_books_do_not_fail_a_clean_audit(self, corpus: Path) -> None:
        self.audit_rc = 0
        assert CliRunner().invoke(cli, ["audit", "--sections"]).exit_code == 0

    def test_a_failing_audit_still_fails_with_sections(self, corpus: Path) -> None:
        self.audit_rc = 1
        result = CliRunner().invoke(cli, ["audit", "--sections"])
        assert result.exit_code == 1
        assert "Dunwich" in result.output

    def test_genre_reaches_both_checks(self, corpus: Path) -> None:
        result = CliRunner().invoke(cli, ["audit", "--genre", "drama", "--sections"])
        assert self.audit_genres == [["drama"]]
        assert "0 books have" in result.output
        assert "Dunwich" not in result.output

    def test_csv_out_and_baseline(self, corpus: Path, tmp_path: Path) -> None:
        csv_path = tmp_path / "sections.csv"
        result = CliRunner().invoke(cli, ["audit", "--sections", "--csv-out", str(csv_path)])
        assert "Wrote 2 rows" in result.output
        assert sec.load_baseline(csv_path) == {"Dunwich": 1, "Short": 1}

        result = CliRunner().invoke(cli, ["audit", "--sections", "--baseline", str(csv_path)])
        assert "No section-count changes vs baseline." in result.output

        csv_path.write_text(csv_path.read_text().replace(",1,", ",3,", 1), encoding="utf-8")
        result = CliRunner().invoke(cli, ["audit", "--sections", "--baseline", str(csv_path)])
        assert "1 book(s) changed section count vs baseline:" in result.output
        assert ": 3 -> 1" in result.output

    @pytest.mark.parametrize("flag", ["--baseline", "--csv-out"])
    def test_report_options_need_sections(self, corpus: Path, tmp_path: Path, flag: str) -> None:
        path = tmp_path / "x.csv"
        path.write_text("book,sections\n", encoding="utf-8")
        result = CliRunner().invoke(cli, ["audit", flag, str(path)])
        assert result.exit_code == 2
        assert "need --sections" in result.output
