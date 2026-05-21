#!/usr/bin/env python3
"""Create stratified inputs for the SIMILAR_TO cap analysis.

This script scans selected corpus genres, estimates book size from the primary
markdown file, chooses a stratified sample per genre, and writes:

1. A book manifest CSV for the cap sweep.
2. A query/relevance template CSV for labeling retrieval quality.

Usage:

    poetry run python scripts/setup_similar_to_analysis.py

    poetry run python scripts/setup_similar_to_analysis.py \
        --genres biography philosophy science-fiction english-literature \
        --per-genre 3 \
        --manifest-out analysis/similar_to_book_manifest.csv \
        --queries-out analysis/similar_to_query_template.csv
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = REPO_ROOT / "corpus"

DEFAULT_GENRES = [
    "biography",
    "philosophy",
    "science-fiction",
    "english-literature",
]

QUERY_TYPES = [
    "factual_entity",
    "thematic_semantic",
    "cross_chunk_context",
]


@dataclass(frozen=True)
class BookRow:
    """A corpus book with size proxies.

    :param genre: Genre directory under corpus/.
    :param book_name: Book directory name.
    :param book_relpath: Relative path from repo root.
    :param markdown_file: Primary markdown file name.
    :param size_bytes: Size of markdown in bytes.
    :param line_count: Number of lines in markdown.
    :param rank: Size rank within genre, ascending.
    :param size_tier: short, medium, or long.
    """

    genre: str
    book_name: str
    book_relpath: str
    markdown_file: str
    size_bytes: int
    line_count: int
    rank: int
    size_tier: str


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--genres",
        nargs="+",
        default=DEFAULT_GENRES,
        help="Genres under corpus/ to include.",
    )
    p.add_argument(
        "--per-genre",
        type=int,
        default=3,
        help="Sample size per genre (default: 3).",
    )
    p.add_argument(
        "--manifest-out",
        default="analysis/similar_to_book_manifest.csv",
        help="Output CSV path for sampled-book manifest.",
    )
    p.add_argument(
        "--queries-out",
        default="analysis/similar_to_query_template.csv",
        help="Output CSV path for query/relevance labeling template.",
    )
    return p.parse_args()


def find_primary_markdown(book_dir: Path) -> Path | None:
    """Return the main markdown file for a book directory.

    Excludes reference.md and picks the largest remaining .md file.

    :param book_dir: Book directory path.
    :return: Primary markdown path or None if not found.
    """
    candidates = [p for p in book_dir.glob("*.md") if p.name.lower() != "reference.md"]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


def get_tier(rank: int, total: int) -> str:
    """Map an ascending size rank to short/medium/long.

    :param rank: Zero-based rank in ascending size order.
    :param total: Total book count in the genre.
    :return: Size tier label.
    """
    if total <= 1:
        return "medium"
    frac = rank / max(total - 1, 1)
    if frac < (1.0 / 3.0):
        return "short"
    if frac < (2.0 / 3.0):
        return "medium"
    return "long"


def collect_genre_books(genre: str) -> list[BookRow]:
    """Collect and rank books for one genre.

    :param genre: Genre directory name under corpus/.
    :return: Sorted list of BookRow (ascending by size).
    """
    genre_dir = CORPUS_ROOT / genre
    if not genre_dir.is_dir():
        return []

    rows: list[tuple[str, str, int, int]] = []
    for book_dir in sorted(genre_dir.iterdir()):
        if not book_dir.is_dir():
            continue
        primary = find_primary_markdown(book_dir)
        if primary is None:
            continue
        text = primary.read_text(encoding="utf-8", errors="ignore")
        size_bytes = primary.stat().st_size
        line_count = text.count("\n") + 1
        rows.append((book_dir.name, primary.name, size_bytes, line_count))

    rows.sort(key=lambda r: r[2])

    ranked: list[BookRow] = []
    total = len(rows)
    for idx, (book_name, md_name, size_bytes, line_count) in enumerate(rows):
        rel = Path("corpus") / genre / book_name
        ranked.append(
            BookRow(
                genre=genre,
                book_name=book_name,
                book_relpath=str(rel),
                markdown_file=md_name,
                size_bytes=size_bytes,
                line_count=line_count,
                rank=idx,
                size_tier=get_tier(idx, total),
            )
        )
    return ranked


def pick_stratified(rows: list[BookRow], per_genre: int) -> list[BookRow]:
    """Select evenly spaced rows across size distribution.

    :param rows: Sorted BookRow list by ascending size.
    :param per_genre: Number of books to choose.
    :return: Stratified subset.
    """
    if per_genre <= 0:
        return []
    if len(rows) <= per_genre:
        return rows

    picks: list[BookRow] = []
    seen: set[int] = set()
    n = len(rows)
    for i in range(per_genre):
        target = (i + 0.5) / per_genre
        idx = round(target * (n - 1))
        while idx in seen and idx + 1 < n:
            idx += 1
        while idx in seen and idx - 1 >= 0:
            idx -= 1
        if idx in seen:
            continue
        seen.add(idx)
        picks.append(rows[idx])

    picks.sort(key=lambda r: (r.genre, r.size_bytes, r.book_name))
    return picks


def write_manifest(rows: list[BookRow], out_path: Path) -> None:
    """Write sampled book manifest CSV.

    :param rows: Sampled books.
    :param out_path: Output CSV path.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "genre",
                "book_name",
                "book_relpath",
                "markdown_file",
                "size_bytes",
                "line_count",
                "size_tier",
                "notes",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.genre,
                    r.book_name,
                    r.book_relpath,
                    r.markdown_file,
                    r.size_bytes,
                    r.line_count,
                    r.size_tier,
                    "",
                ]
            )


def write_query_template(rows: list[BookRow], out_path: Path) -> None:
    """Write query/relevance labeling template CSV.

    Creates three placeholder query rows per sampled book.

    :param rows: Sampled books.
    :param out_path: Output CSV path.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "query_id",
                "query_type",
                "genre",
                "book_relpath",
                "book_name",
                "query_text",
                "expected_signals",
                "expected_node_ids",
                "relevance_label",
                "assessor",
                "notes",
            ]
        )

        qid = 1
        for r in rows:
            for qtype in QUERY_TYPES:
                w.writerow(
                    [
                        f"Q{qid:04d}",
                        qtype,
                        r.genre,
                        r.book_relpath,
                        r.book_name,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )
                qid += 1


def print_summary(rows: list[BookRow]) -> None:
    """Print compact terminal summary of selected books.

    :param rows: Sampled books.
    """
    print(f"Selected books: {len(rows)}")
    by_genre: dict[str, list[BookRow]] = {}
    for r in rows:
        by_genre.setdefault(r.genre, []).append(r)

    for genre in sorted(by_genre):
        picks = by_genre[genre]
        print(f"\n[{genre}] {len(picks)} books")
        for r in sorted(picks, key=lambda x: x.size_bytes):
            print(
                f"  - {r.book_name} | {r.size_tier:6} | "
                f"{r.size_bytes:,} bytes | {r.line_count:,} lines"
            )


def main() -> None:
    """Run the manifest/template generation workflow."""
    args = parse_args()

    selected: list[BookRow] = []
    for genre in args.genres:
        rows = collect_genre_books(genre)
        if not rows:
            print(f"[warn] No books found for genre: {genre}")
            continue
        selected.extend(pick_stratified(rows, args.per_genre))

    if not selected:
        raise SystemExit("No books selected. Check --genres and corpus contents.")

    manifest_out = (REPO_ROOT / args.manifest_out).resolve()
    queries_out = (REPO_ROOT / args.queries_out).resolve()

    write_manifest(selected, manifest_out)
    write_query_template(selected, queries_out)
    print_summary(selected)

    print("\nWrote:")
    print(f"  - {manifest_out}")
    print(f"  - {queries_out}")


if __name__ == "__main__":
    main()
