"""
check_sections.py — measure how much of each book's text lives in a single
oversized section, and flag books whose structure suggests missing headings.

This is the Phase 0 check from analysis/MONOLITHIC_SECTIONS_PLAN.md: it
promotes the ad hoc query that produced analysis/monolithic_sections_20260903.csv
into a reusable script with a baseline-diff gate, so a heading-pattern change
that fires spuriously in an unrelated book is caught by name instead of
discovered later.

Reads each book's own per-book DocKG store
(corpus/<genre>/<Title>/.dockg/graph.sqlite) directly -- not the exported
Swift pack -- since every book already carries one and it is the ground
truth the pack is built from.

Usage:
    python scripts/check_sections.py
    python scripts/check_sections.py --csv-out analysis/monolithic_sections_TODAY.csv
    python scripts/check_sections.py --baseline analysis/monolithic_sections_20260903.csv
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "corpus"

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


def scan_corpus() -> list[BookSections]:
    results = []
    for genre_dir in sorted(p for p in CORPUS_ROOT.iterdir() if p.is_dir()):
        if genre_dir.name == "authors":
            continue
        for book_dir in sorted(p for p in genre_dir.iterdir() if p.is_dir()):
            measured = measure_book(book_dir, genre_dir.name)
            if measured:
                results.append(measured)
    return results


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, help="baseline CSV to diff section counts against")
    parser.add_argument("--csv-out", type=Path, help="write full per-book results as CSV")
    args = parser.parse_args()

    results = scan_corpus()
    results.sort(key=lambda r: r.share_in_largest, reverse=True)

    flagged = [
        r for r in results if r.share_in_largest > FLAG_SHARE and r.largest_chars > FLAG_CHARS
    ]
    print(
        f"{len(flagged)} books have >{FLAG_SHARE:.0%} of their text in a single "
        f"section over {FLAG_CHARS:,} characters:\n"
    )
    for r in flagged:
        print(
            f"{r.share_in_largest * 100:5.1f}%  {r.sections:3d} secs  {r.largest_chars:>10,} ch  "
            f"[{r.genre}]  {r.book}  -- {r.largest_section_title}"
        )

    if args.csv_out:
        write_csv(results, args.csv_out)
        print(f"\nWrote {len(results)} rows to {args.csv_out}")

    if args.baseline:
        baseline = load_baseline(args.baseline)
        current = {r.book: r.sections for r in results}
        changed = [
            (book, baseline.get(book), current.get(book))
            for book in sorted(set(baseline) | set(current))
            if baseline.get(book) != current.get(book)
        ]
        if changed:
            print(f"\n{len(changed)} book(s) changed section count vs baseline:")
            for book, old, new in changed:
                print(f"  {book}: {old} -> {new}")
        else:
            print("\nNo section-count changes vs baseline.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
