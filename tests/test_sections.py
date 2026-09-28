"""Tests for gutenberg_kg.sections: books with most text in one section.

Each book is a tmp_path DocKG store holding only the section and chunk rows
the measurement reads.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gutenberg_kg import sections as sec


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
