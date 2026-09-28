# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
sections.py — measure how much of each book's text lives in a single
oversized section, and flag books whose structure suggests missing headings.

This is the Phase 0 check from analysis/MONOLITHIC_SECTIONS_PLAN.md: it
promotes the ad hoc query that produced analysis/monolithic_sections_20260903.csv
into a reusable check with a baseline-diff gate, so a heading-pattern change
that fires spuriously in an unrelated book is caught by name instead of
discovered later. It was scripts/check_sections.py until v1.26.0.

Reads each book's own per-book DocKG store
(corpus/<genre>/<Title>/.dockg/graph.sqlite) directly -- not the exported
Swift pack -- since every book already carries one and it is the ground
truth the pack is built from.

Usage:
    gutenkg audit --sections
    gutenkg audit --sections --csv-out analysis/monolithic_sections_TODAY.csv
    gutenkg audit --sections --baseline analysis/monolithic_sections_20260903.csv
"""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

FLAG_SHARE = 0.90
FLAG_CHARS = 100_000


@dataclass
class BookSections:
    book: str
    genre: str
    sections: int
    largest_chars: int
    largest_section_title: str
    chunks_in_largest: int
    total_chars: int

    @property
    def share_in_largest(self) -> float:
        return self.largest_chars / self.total_chars if self.total_chars else 0.0


def _book_main_md(book_dir: Path) -> str | None:
    """Return the filename of the book's own markdown file (not reference.md)."""
    for path in sorted(book_dir.glob("*.md")):
        if path.name != "reference.md":
            return path.name
    return None


def measure_book(book_dir: Path, genre: str) -> BookSections | None:
    db_path = book_dir / ".dockg" / "graph.sqlite"
    if not db_path.exists():
        return None
    main_md = _book_main_md(book_dir)
    if main_md is None:
        return None

    conn = sqlite3.connect(str(db_path))
    try:
        sections = conn.execute(
            "SELECT title, char_start, char_end FROM nodes "
            "WHERE kind='section' AND file_path=? ORDER BY char_start",
            (main_md,),
        ).fetchall()
        if not sections:
            return None
        chunk_starts = [
            row[0]
            for row in conn.execute(
                "SELECT char_start FROM nodes WHERE kind='chunk' AND file_path=?",
                (main_md,),
            )
        ]
    finally:
        conn.close()

    total_chars = sum(max(0, end - start) for _, start, end in sections)
    if total_chars == 0:
        return None

    title, start, end = max(sections, key=lambda s: s[2] - s[1])
    largest_chars = end - start
    chunks_in_largest = sum(1 for cs in chunk_starts if start <= cs < end)

    return BookSections(
        book=book_dir.name,
        genre=genre,
        sections=len(sections),
        largest_chars=largest_chars,
        largest_section_title=title,
        chunks_in_largest=chunks_in_largest,
        total_chars=total_chars,
    )


def scan_corpus(corpus: Path, genres: Iterable[str] = ()) -> list[BookSections]:
    """Measure every book with a per-book DocKG store.

    :param corpus: The corpus root.
    :param genres: Genres to measure; empty measures all of them.
    :return: One ``BookSections`` per measured book, sorted by the share of
        text in the largest section, largest first.
    """
    wanted = set(genres)
    results = []
    for genre_dir in sorted(p for p in corpus.iterdir() if p.is_dir()):
        if genre_dir.name == "authors" or (wanted and genre_dir.name not in wanted):
            continue
        for book_dir in sorted(p for p in genre_dir.iterdir() if p.is_dir()):
            measured = measure_book(book_dir, genre_dir.name)
            if measured:
                results.append(measured)
    results.sort(key=lambda r: r.share_in_largest, reverse=True)
    return results


def flagged(results: list[BookSections]) -> list[BookSections]:
    """Return the books with most of their text in one oversized section.

    :param results: Output of :func:`scan_corpus`.
    :return: Books over ``FLAG_SHARE`` of their text in one section longer
        than ``FLAG_CHARS`` characters.
    """
    return [r for r in results if r.share_in_largest > FLAG_SHARE and r.largest_chars > FLAG_CHARS]


def baseline_changes(
    results: list[BookSections], baseline: dict[str, int]
) -> list[tuple[str, int | None, int | None]]:
    """Return books whose section count differs from a baseline.

    :param results: Output of :func:`scan_corpus`.
    :param baseline: Output of :func:`load_baseline`.
    :return: ``(book, baseline_sections, current_sections)``; ``None`` where
        the book is absent on that side.
    """
    current = {r.book: r.sections for r in results}
    return [
        (book, baseline.get(book), current.get(book))
        for book in sorted(set(baseline) | set(current))
        if baseline.get(book) != current.get(book)
    ]


def load_baseline(path: Path) -> dict[str, int]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        return {row["book"]: int(row["sections"]) for row in reader}


def write_csv(results: list[BookSections], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "share_in_largest_section",
                "sections",
                "chunks_in_largest",
                "largest_chars",
                "total_chars",
                "largest_section_title",
                "genre",
                "book",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    f"{r.share_in_largest:.4f}",
                    r.sections,
                    r.chunks_in_largest,
                    r.largest_chars,
                    r.total_chars,
                    r.largest_section_title,
                    r.genre,
                    r.book,
                ]
            )
