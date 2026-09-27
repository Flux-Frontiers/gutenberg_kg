"""Unit tests for gutenberg_kg.serve.diary_browse: a diary read by dated entry."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gutenberg_kg.serve.diary_browse import diary_chapter, diary_chapters, format_diary_date


def _diary(tmp_path: Path) -> Path:
    graph = tmp_path / "graph.sqlite"
    with sqlite3.connect(str(graph)) as con:
        con.execute(
            "CREATE TABLE nodes (id TEXT, kind TEXT, file_path TEXT, char_start INT, "
            "text TEXT, timestamp TEXT)"
        )
        con.executemany(
            "INSERT INTO nodes VALUES (?,?,?,?,?,?)",
            [
                # Out of order on purpose: entries sort by timestamp, chunks by file then offset.
                ("c3", "chunk", "entry_0002_chunk_0.md", 0, "We set out.", "1773-08-18T00:00"),
                ("c2", "chunk", "entry_0001_chunk_1.md", 0, "Dined at Boyd's.", "1773-08-15T00:00"),
                (
                    "c1",
                    "chunk",
                    "entry_0001_chunk_0.md",
                    40,
                    "Johnson arrived.",
                    "1773-08-15T00:00",
                ),
                ("d1", "document", "entry_0001.md", 0, "not a chunk", "1773-08-01T00:00"),
                ("k1", "keyword", None, None, "Edinburgh", None),
            ],
        )
        con.commit()
    return graph


class TestDiaryBrowse:
    def test_entries_are_the_distinct_chunk_dates_in_order(self, tmp_path: Path):
        chapters = diary_chapters(_diary(tmp_path))
        assert [c["id"] for c in chapters] == ["1773-08-15T00:00", "1773-08-18T00:00"]
        assert chapters[0] == {"id": "1773-08-15T00:00", "title": "August 15, 1773", "index": 0}

    def test_entry_joins_its_chunks_in_chunking_order(self, tmp_path: Path):
        entry = diary_chapter(_diary(tmp_path), "1773-08-15T00:00")
        assert entry == {
            "title": "August 15, 1773",
            "text": "Johnson arrived.\n\nDined at Boyd's.",
            "index": 0,
            "total": 2,
            "prev_id": None,
            "next_id": "1773-08-18T00:00",
        }

    def test_unknown_entry_is_none(self, tmp_path: Path):
        assert diary_chapter(_diary(tmp_path), "1773-08-01T00:00") is None

    def test_unparseable_timestamp_passes_through(self):
        assert format_diary_date("sometime in 1660") == "sometime in 1660"
