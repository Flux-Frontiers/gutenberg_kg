"""Publication dates for corpus books, as the shared temporal contract.

A library is the clearest case in the fleet for *year* precision. Internet
Archive gives a book a date and GutenbergKG already truncates it to the year
(:mod:`gutenberg_kg.ia` keeps ``raw_date[:4]``), because that is honestly all
the source supports — an 1876 printing is not an event on the 1st of January.

:mod:`kg_utils.temporal` preserves that. ``"1876"`` stays a year and overlaps
any query touching 1876, rather than collapsing to a silent ``1876-01-01``
that a February window would miss.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from kg_utils.temporal import temporal_metadata

__all__ = ["publication_year", "stamp_publication_year"]

#: The ``- **Date**: 1876`` line in a book's ``reference.md`` metadata sheet,
#: written by :func:`gutenberg_kg.ia.write_reference`.
_DATE_LINE_RE = re.compile(r"^-\s+\*\*Date\*\*:\s*(\d{4})\s*$", re.M)


def publication_year(book_dir: Path) -> str | None:
    """Read a book's publication year from its ``reference.md``.

    :param book_dir: Directory holding the book's files.
    :return: A four-digit year, or ``None`` when the sheet is absent or carries
        no usable date. Books downloaded from Gutenberg rather than the
        Internet Archive frequently have none, which is not an error.
    """
    ref = book_dir / "reference.md"
    try:
        text = ref.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = _DATE_LINE_RE.search(text)
    return match.group(1) if match else None


def stamp_publication_year(db_path: Path, year: str) -> int:
    """Write ``year`` onto every node of a book's graph as the temporal contract.

    Every node, not only the document row: a federated query hits *chunks*, and
    a chunk that cannot say when its book was published drops out of any
    time-scoped query even though the book beside it is dated.

    Existing metadata is merged rather than replaced, so this can run after any
    other enrichment without eating its keys.

    :param db_path: Path to the book's DocKG SQLite graph.
    :param year: Four-digit publication year.
    :return: Number of node rows updated.
    """
    try:
        temporal = temporal_metadata(occurred_start=year)
    except (ValueError, TypeError):
        return 0
    if not temporal:
        return 0

    updated = 0
    with sqlite3.connect(str(db_path)) as con:
        try:
            rows = con.execute("SELECT id, metadata FROM nodes").fetchall()
        except sqlite3.OperationalError:
            # A graph built before doc-kg persisted node metadata.
            return 0
        for node_id, blob in rows:
            existing = {}
            if blob:
                try:
                    loaded = json.loads(blob)
                    existing = loaded if isinstance(loaded, dict) else {}
                except (TypeError, ValueError):
                    existing = {}
            merged = {**existing, **temporal}
            con.execute(
                "UPDATE nodes SET metadata = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii=False), node_id),
            )
            updated += 1
        con.commit()
    return updated
