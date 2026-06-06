"""
assess_front_matter.py — Scan corpus markdown files for front-matter content
and produce a per-book + aggregate report.

Front matter = introductions, prefaces, editor notes, biographical sketches,
translator notes, tables of contents, transcriber notes, and publisher pages
that precede the primary text of a book. These sections contaminate retrieval
because they are topically dense summaries that score high on semantic search.

Output: JSON summary + printed table sorted by front-matter percentage.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CORPUS_ROOT = Path(__file__).parent.parent / "corpus"

# Headings that signal a front-matter section.
# Rules:
#   - Only matched on headings that are NOT H1 (title) level
#   - Main-content keywords (chapter/book/part/…) take priority — if a heading
#     starts with one of those, it is never FM regardless of other words
#   - Appendix/bibliography/glossary are back-matter, not FM
#   - "life of X" removed — too broadly matches chapter headings in classical/
#     biography works where "Life of Plato" etc. ARE the main content
FRONT_MATTER_PATTERNS = re.compile(
    r"""
    \b(
        introduc\w*          # introduction, introductory, introductory note
      | preface
      | foreword
      | fore\s*word
      | prefator\w*          # prefatory
      | editor[‘’]?s?\s*(note|introduction|preface|remarks)
      | translator[‘’]?s?\s*(note|introduction|preface|remarks)
      | transcriber[‘’]?s?\s*note
      | biographical\s+sketch
      | about\s+the\s+author
      | about\s+this\s+(book|edition|text|translation)
      | table\s+of\s+contents
      | proleg\w*            # prolegomena
      | note[s]?\s*to\s+the
      | a\s+note\s+on
      | note\s+on\s+the\s+(text|translation|edition)
      | publisher[‘’]?s?\s*(note|preface)
      | copyright
      | by\s+way\s+of\s+introduction
      | introductory\s+essay
      | select\s+bibliography  # bibliography as explicit FM section title
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Back-matter: appendices, bibliography, glossary, index — at the END of a book
BACK_MATTER_PATTERNS = re.compile(
    r"\b(append\w*|bibliograph\w*|glossar\w*|index\b|errata)\b",
    re.IGNORECASE,
)

# Heading line: 1-3 # signs.  Group 1 = hashes, group 2 = text.
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)")

# A heading that unambiguously signals main content — beats FM heuristics.
MAIN_CONTENT_HEADING = re.compile(
    r"^(chapter|book|part|volume|canto|act|scene|letter|section|song|ode|tale|night|day)\b",
    re.IGNORECASE,
)

# Maximum fraction of a file at which a section can still be classified as FM.
# Sections starting after this point are likely embedded contextual intros or
# back matter, not preamble contamination.
FM_POSITION_CUTOFF = 0.40


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SectionSpan:
    heading: str
    start_line: int  # 0-based
    end_line: int  # exclusive
    is_front_matter: bool
    is_back_matter: bool


@dataclass
class BookResult:
    genre: str
    book: str
    md_file: str
    total_lines: int
    front_matter_lines: int
    back_matter_lines: int
    front_matter_pct: float
    back_matter_pct: float
    front_matter_sections: list[str] = field(default_factory=list)
    # DocKG chunk counts (if index exists)
    total_chunks: int | None = None
    front_matter_chunks: int | None = None
    fm_chunk_pct: float | None = None
    has_reference_md: bool = False


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def parse_sections(lines: list[str], total_lines: int) -> list[SectionSpan]:
    """Split a file into heading-delimited sections, label front/back matter.

    Rules applied per section:
      1. H1 title heading is never FM (it's just the book title).
      2. If the heading starts with a main-content keyword (chapter, book, part …)
         it is never FM — main-content wins even if other FM words appear.
      3. FM sections appearing after FM_POSITION_CUTOFF of the file are reclassified
         as back-matter (or plain body) — they are embedded contextual intros, not
         preamble contamination.
    """
    sections: list[SectionSpan] = []
    current_heading = "<preamble>"
    current_level = 0  # 0 = synthetic preamble
    current_start = 0
    first_heading_done = False  # track whether H1 has been seen

    def close_section(end: int) -> None:
        nonlocal first_heading_done
        heading_lower = current_heading.lower()

        # Rule 1: H1 (first real heading) is the book title — never FM
        is_title = current_level == 1 and not first_heading_done

        # Rule 2: main-content heading keyword overrides FM classification
        is_main = bool(MAIN_CONTENT_HEADING.match(current_heading))

        # Base FM detection
        raw_fm = bool(FRONT_MATTER_PATTERNS.search(heading_lower))
        raw_bm = bool(BACK_MATTER_PATTERNS.search(heading_lower))

        # Rule 3: position gate — FM only applies in first FM_POSITION_CUTOFF of file
        position_frac = current_start / max(total_lines, 1)
        within_gate = position_frac <= FM_POSITION_CUTOFF

        is_fm = raw_fm and not is_title and not is_main and within_gate
        is_bm = (raw_bm or (raw_fm and not within_gate)) and not is_fm

        if current_level == 1 and not first_heading_done:
            first_heading_done = True

        sections.append(
            SectionSpan(
                heading=current_heading,
                start_line=current_start,
                end_line=end,
                is_front_matter=is_fm,
                is_back_matter=is_bm,
            )
        )

    for i, line in enumerate(lines):
        m = HEADING_RE.match(line.rstrip())
        if m:
            close_section(i)
            current_level = len(m.group(1))
            current_heading = m.group(2).strip()
            current_start = i

    close_section(total_lines)
    return sections


def estimate_front_matter_boundary(sections: list[SectionSpan], total_lines: int) -> int:
    """
    Heuristic: the preamble + any leading sections whose headings are front-matter
    count as front matter, up until we see the first clearly main-content heading.
    Returns the line number where main content begins.
    """
    for sec in sections:
        if MAIN_CONTENT_HEADING.match(sec.heading):
            return sec.start_line
    return 0


def count_dockg_chunks(
    book_dir: Path, front_matter_end_line: int, lines: list[str]
) -> tuple[int | None, int | None]:
    """
    Query the DocKG sqlite to count total chunks and estimate how many fall
    in front-matter by their position (chunk sequence number).

    Returns (total_chunks, front_matter_chunks) or (None, None) if no index.
    """
    db_path = book_dir / ".dockg" / "graph.sqlite"
    if not db_path.exists():
        return None, None

    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()

        # Total chunks
        cur.execute("SELECT COUNT(*) FROM nodes WHERE kind='chunk'")
        total = cur.fetchone()[0]
        if total == 0:
            return 0, 0

        # Estimate the chunk index at which main content begins
        # Proportion of front-matter lines → proportional chunk boundary
        if front_matter_end_line > 0:
            fm_frac = front_matter_end_line / max(len(lines), 1)
            boundary_idx = int(fm_frac * total)
        else:
            boundary_idx = 0

        con.close()
        return total, boundary_idx

    except Exception:  # noqa: BLE001
        return None, None


def analyse_book(md_path: Path, genre: str) -> BookResult:
    book_dir = md_path.parent
    book_name = book_dir.name

    with open(md_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    total_lines = len(lines)
    sections = parse_sections(lines, total_lines)

    fm_lines = sum(s.end_line - s.start_line for s in sections if s.is_front_matter)
    bm_lines = sum(s.end_line - s.start_line for s in sections if s.is_back_matter)
    fm_pct = 100 * fm_lines / total_lines if total_lines else 0.0
    bm_pct = 100 * bm_lines / total_lines if total_lines else 0.0

    fm_sections = [s.heading for s in sections if s.is_front_matter]

    fm_end_line = estimate_front_matter_boundary(sections, total_lines)
    total_chunks, fm_chunks = count_dockg_chunks(book_dir, fm_end_line, lines)
    fm_chunk_pct = (
        100 * fm_chunks / total_chunks if (total_chunks and fm_chunks is not None) else None
    )

    has_ref = (book_dir / "reference.md").exists()

    return BookResult(
        genre=genre,
        book=book_name,
        md_file=md_path.name,
        total_lines=total_lines,
        front_matter_lines=fm_lines,
        back_matter_lines=bm_lines,
        front_matter_pct=round(fm_pct, 2),
        back_matter_pct=round(bm_pct, 2),
        front_matter_sections=fm_sections,
        total_chunks=total_chunks,
        front_matter_chunks=fm_chunks,
        fm_chunk_pct=round(fm_chunk_pct, 2) if fm_chunk_pct is not None else None,
        has_reference_md=has_ref,
    )


def scan_corpus() -> list[BookResult]:
    results: list[BookResult] = []
    skip_dirs = {".snapshots", "authors", ".dockg"}

    for genre_dir in sorted(CORPUS_ROOT.iterdir()):
        if not genre_dir.is_dir() or genre_dir.name in skip_dirs:
            continue
        genre = genre_dir.name
        for book_dir in sorted(genre_dir.iterdir()):
            if not book_dir.is_dir() or book_dir.name.startswith("."):
                continue
            mds = [p for p in book_dir.glob("*.md") if p.name != "reference.md"]
            if not mds:
                continue
            # If multiple .md files (rare), pick the largest
            md = max(mds, key=lambda p: p.stat().st_size)
            try:
                results.append(analyse_book(md, genre))
            except Exception as e:  # noqa: BLE001
                print(f"  WARN: {genre}/{book_dir.name} — {e}", file=sys.stderr)

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_table(results: list[BookResult]) -> None:
    sorted_r = sorted(results, key=lambda r: -r.front_matter_pct)

    print(
        f"\n{'Genre':<22} {'Book':<42} {'FM%':>5} {'FM lines':>9} {'Total':>7} "
        f"{'Chunks':>7} {'FM Sections'}"
    )
    print("-" * 120)
    for r in sorted_r:
        fm_sec_str = ", ".join(r.front_matter_sections[:3])
        if len(r.front_matter_sections) > 3:
            fm_sec_str += f" (+{len(r.front_matter_sections) - 3})"
        chunks_str = f"{r.front_matter_chunks}/{r.total_chunks}" if r.total_chunks else "no-idx"
        print(
            f"{r.genre:<22} {r.book[:42]:<42} {r.front_matter_pct:>5.1f}% "
            f"{r.front_matter_lines:>8,} {r.total_lines:>7,} "
            f"{chunks_str:>12}  {fm_sec_str}"
        )


def print_summary(results: list[BookResult]) -> None:
    total_books = len(results)
    books_with_fm = sum(1 for r in results if r.front_matter_lines > 0)
    all_fm_pcts = [r.front_matter_pct for r in results if r.front_matter_lines > 0]
    mean_fm = sum(all_fm_pcts) / len(all_fm_pcts) if all_fm_pcts else 0.0
    median_fm = sorted(all_fm_pcts)[len(all_fm_pcts) // 2] if all_fm_pcts else 0.0
    max_fm = max(all_fm_pcts) if all_fm_pcts else 0.0

    threshold_5 = sum(1 for p in all_fm_pcts if p >= 5)
    threshold_10 = sum(1 for p in all_fm_pcts if p >= 10)
    threshold_20 = sum(1 for p in all_fm_pcts if p >= 20)

    total_lines_all = sum(r.total_lines for r in results)
    total_fm_lines = sum(r.front_matter_lines for r in results)
    total_ref_md = sum(1 for r in results if r.has_reference_md)

    # Section-type frequency
    section_freq: dict[str, int] = {}
    for r in results:
        for s in r.front_matter_sections:
            key = s.lower()[:40]
            section_freq[key] = section_freq.get(key, 0) + 1
    top_sections = sorted(section_freq.items(), key=lambda x: -x[1])[:15]

    print("\n" + "=" * 70)
    print("CORPUS FRONT-MATTER ASSESSMENT")
    print("=" * 70)
    print(f"  Total books scanned:          {total_books}")
    print(
        f"  Books with front matter:      {books_with_fm}  ({100 * books_with_fm / total_books:.1f}%)"
    )
    print(f"  Mean FM% (books with FM):     {mean_fm:.1f}%")
    print(f"  Median FM%:                   {median_fm:.1f}%")
    print(f"  Max FM%:                      {max_fm:.1f}%")
    print(f"  Books ≥5% FM:                 {threshold_5}")
    print(f"  Books ≥10% FM:                {threshold_10}")
    print(f"  Books ≥20% FM:                {threshold_20}")
    print(f"  Total corpus lines:           {total_lines_all:,}")
    print(
        f"  Total FM lines:               {total_fm_lines:,}  ({100 * total_fm_lines / total_lines_all:.1f}% of corpus)"
    )
    print(f"  Books with reference.md:      {total_ref_md}")
    print()
    print("  Top front-matter section types:")
    for label, count in top_sections:
        bar = "█" * min(count, 40)
        print(f"    {count:3d}  {label[:42]:<42}  {bar}")
    print()

    print("  By genre (mean FM%):")
    genre_data: dict[str, list[float]] = {}
    for r in results:
        genre_data.setdefault(r.genre, []).append(r.front_matter_pct)
    for genre, pcts in sorted(genre_data.items(), key=lambda x: -sum(x[1]) / len(x[1])):
        mean = sum(pcts) / len(pcts)
        print(f"    {genre:<28} mean {mean:5.1f}%  n={len(pcts)}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", metavar="PATH", help="Write full results to JSON")
    parser.add_argument(
        "--min-pct", type=float, default=0.0, help="Only show books with FM%% >= this in the table"
    )
    args = parser.parse_args()

    print(f"Scanning corpus at {CORPUS_ROOT} …", file=sys.stderr)
    results = scan_corpus()
    print(f"  {len(results)} books found.", file=sys.stderr)

    filtered = [r for r in results if r.front_matter_pct >= args.min_pct]
    print_table(filtered)
    print_summary(results)

    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)
        print(f"\nFull results written to {out_path}")


if __name__ == "__main__":
    main()
