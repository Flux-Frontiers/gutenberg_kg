"""Browsing a diary by dated entry, kept free of the handler's import-time startup.

A diary is a DiaryKG, not part of the consolidated DocKG the handler browses
books in: it has no ``section`` nodes and no single content ``file_path``, so
``get_chapters`` / ``get_chapter`` could not find one. Its chapters are its
dated entries instead, the same scheme the app's ``PassagePack.diaryEntries``
uses over ``diaries.pack``: one chapter per distinct chunk ``timestamp``, the
raw timestamp as the id, the entry's chunks joined in chunking order.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


def format_diary_date(timestamp: str) -> str:
    """Render an entry timestamp for reading, e.g. ``"August 15, 1773"``.

    :param timestamp: A DiaryKG timestamp, ``"YYYY-MM-DDTHH:MM"``.
    :returns: The date, or the timestamp unchanged when it does not parse.
    """
    try:
        d = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M")
    except ValueError:
        return timestamp
    return f"{d:%B} {d.day}, {d.year}"


def _connect(graph: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{graph}?mode=ro", uri=True)


def _timestamps(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT timestamp FROM nodes "
        "WHERE kind = 'chunk' AND timestamp IS NOT NULL ORDER BY timestamp"
    )
    return [r[0] for r in rows]


def diary_chapters(graph: Path) -> list[dict]:
    """A diary's dated entries, earliest first.

    :param graph: The diary's ``.diarykg/graph.sqlite``.
    :returns: ``[{"id", "title", "index"}, ...]``, one per entry.
    """
    with _connect(graph) as con:
        return [
            {"id": ts, "title": format_diary_date(ts), "index": i}
            for i, ts in enumerate(_timestamps(con))
        ]


def diary_chapter(graph: Path, timestamp: str) -> dict | None:
    """One dated entry's text, rebuilt from the chunks it spans.

    An entry can straddle more than one entry file, so chunks are ordered by
    ``file_path`` then ``char_start``, the order they were chunked in.

    :param graph: The diary's ``.diarykg/graph.sqlite``.
    :param timestamp: An entry id from :func:`diary_chapters`.
    :returns: ``{"title", "text", "index", "total", "prev_id", "next_id"}``,
        or ``None`` when no entry has that timestamp.
    """
    with _connect(graph) as con:
        stamps = _timestamps(con)
        if timestamp not in stamps:
            return None
        rows = con.execute(
            "SELECT text FROM nodes WHERE kind = 'chunk' AND timestamp = ? "
            "ORDER BY file_path, char_start",
            (timestamp,),
        )
        text = "\n\n".join(r[0] or "" for r in rows)
    index = stamps.index(timestamp)
    return {
        "title": format_diary_date(timestamp),
        "text": text,
        "index": index,
        "total": len(stamps),
        "prev_id": stamps[index - 1] if index > 0 else None,
        "next_id": stamps[index + 1] if index + 1 < len(stamps) else None,
    }
