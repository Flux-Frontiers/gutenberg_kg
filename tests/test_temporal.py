"""GutenbergKG's adoption of the shared kg_utils.temporal contract.

A library is the fleet's clearest *year-precision* case. The Internet Archive
gives a book a date and :mod:`gutenberg_kg.ia` already truncates it to the year,
because that is honestly all the source supports — an 1876 printing is not an
event on the 1st of January.

The contract preserves that. These pin the behaviour that makes it worth having:
``"1876"`` overlaps a February 1876 window, which a silent ``1876-01-01`` would
miss entirely.
"""

from __future__ import annotations

import json
import sqlite3

from kg_utils.temporal import read_span

from gutenberg_kg.temporal import publication_year, stamp_publication_year


def _reference(book_dir, date_line="- **Date**: 1876"):
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "reference.md").write_text(
        "# Reference\n\n"
        "- **Internet Archive ID**: someid\n\n"
        "## Publication\n\n"
        "- **Author**: Someone\n"
        "- **Publisher**: A Press\n"
        f"{date_line}\n"
        "- **Edition**: First\n",
        encoding="utf-8",
    )
    return book_dir


def _graph(db_path, n=3, metadata=None):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.executescript(
        """
        CREATE TABLE nodes (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
          title TEXT, file_path TEXT, char_start INTEGER, char_end INTEGER,
          heading_level INTEGER, text TEXT, metadata TEXT
        );
        """
    )
    for i in range(n):
        kind = "document" if i == 0 else "chunk"
        con.execute(
            "INSERT INTO nodes (id, kind, name, metadata) VALUES (?,?,?,?)",
            (f"{kind}:{i}", kind, f"n{i}", metadata),
        )
    con.commit()
    con.close()
    return db_path


class TestPublicationYear:
    def test_reads_the_year_from_reference(self, tmp_path):
        assert publication_year(_reference(tmp_path / "b")) == "1876"

    def test_missing_reference_is_not_an_error(self, tmp_path):
        """Gutenberg texts carry no IA metadata sheet. That is normal."""
        assert publication_year(tmp_path / "nothing") is None

    def test_reference_without_a_date_yields_none(self, tmp_path):
        book = _reference(tmp_path / "b", date_line="- **Edition**: First")
        assert publication_year(book) is None

    def test_a_non_year_date_is_not_accepted(self, tmp_path):
        book = _reference(tmp_path / "b", date_line="- **Date**: n.d.")
        assert publication_year(book) is None


class TestStamping:
    def test_every_node_is_dated(self, tmp_path):
        """Chunks too: a federated query hits chunks, not just the document."""
        db = _graph(tmp_path / ".dockg" / "graph.sqlite", n=4)
        assert stamp_publication_year(db, "1876") == 4

    def test_stored_value_keeps_year_precision(self, tmp_path):
        db = _graph(tmp_path / ".dockg" / "graph.sqlite")
        stamp_publication_year(db, "1876")
        con = sqlite3.connect(str(db))
        blob = con.execute("SELECT metadata FROM nodes LIMIT 1").fetchone()[0]
        con.close()
        assert json.loads(blob) == {"occurred_start": "1876"}

    def test_existing_metadata_is_merged_not_replaced(self, tmp_path):
        db = _graph(
            tmp_path / ".dockg" / "graph.sqlite",
            metadata=json.dumps({"genre": "fiction"}),
        )
        stamp_publication_year(db, "1876")
        con = sqlite3.connect(str(db))
        stored = json.loads(con.execute("SELECT metadata FROM nodes LIMIT 1").fetchone()[0])
        con.close()
        assert stored["genre"] == "fiction"
        assert stored["occurred_start"] == "1876"

    def test_unreadable_existing_metadata_does_not_lose_the_date(self, tmp_path):
        db = _graph(tmp_path / ".dockg" / "graph.sqlite", metadata="{not json")
        stamp_publication_year(db, "1876")
        con = sqlite3.connect(str(db))
        stored = json.loads(con.execute("SELECT metadata FROM nodes LIMIT 1").fetchone()[0])
        con.close()
        assert stored["occurred_start"] == "1876"

    def test_a_graph_without_the_column_is_skipped_quietly(self, tmp_path):
        """A book built before doc-kg persisted node metadata."""
        db = tmp_path / "old.sqlite"
        con = sqlite3.connect(str(db))
        con.executescript("CREATE TABLE nodes (id TEXT PRIMARY KEY, kind TEXT, name TEXT);")
        con.commit()
        con.close()
        assert stamp_publication_year(db, "1876") == 0

    def test_a_malformed_year_stamps_nothing(self, tmp_path):
        db = _graph(tmp_path / ".dockg" / "graph.sqlite")
        assert stamp_publication_year(db, "not a year") == 0


class TestYearPrecisionIsTheWholePoint:
    def _span(self, tmp_path):
        db = _graph(tmp_path / ".dockg" / "graph.sqlite")
        stamp_publication_year(db, "1876")
        con = sqlite3.connect(str(db))
        blob = con.execute("SELECT metadata FROM nodes LIMIT 1").fetchone()[0]
        con.close()
        return read_span(json.loads(blob))

    def test_a_february_window_finds_an_1876_book(self, tmp_path):
        """A silent 1876-01-01 would miss this. That is the bug being avoided."""
        assert self._span(tmp_path).overlaps("1876-02-01", "1876-02-28")

    def test_the_whole_year_matches(self, tmp_path):
        assert self._span(tmp_path).overlaps("1876-01-01", "1876-12-31")

    def test_the_next_year_does_not(self, tmp_path):
        assert not self._span(tmp_path).overlaps("1877-01-01", "1877-12-31")

    def test_a_decade_window_matches(self, tmp_path):
        assert self._span(tmp_path).overlaps("1870", "1879")
