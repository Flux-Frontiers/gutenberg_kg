"""Report the numbered sequences gutenberg_kg.spine finds in the corpus.

Step 1 of analysis/STRUCTURAL_PARSER_PLAN.md: read-only, no behaviour
change. Converts nothing; prints the numbered-heading clusters each book's
raw text contains and which of them are contents-shaped, so the profile can
be read against the whole corpus before anything is built on it.

Needs raw Gutenberg text, which this repo does not cache (conversion happens
at download time -- see the plan). Point --raw-dir at a directory of
``pg<id>.txt`` files and --book-index at a JSON list of
``{"book", "genre", "ebook_id", "main_md"}`` rows describing which book each
belongs to; both were produced ad hoc while validating this module and are
not part of the repository.

Usage:
    python scripts/profile_structure.py --raw-dir <dir> --book-index <file>
    python scripts/profile_structure.py --raw-dir <dir> --book-index <file> -v
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from gutenberg_kg.gutenberg import strip_boilerplate  # noqa: E402
from gutenberg_kg.spine import contents_regions, profile  # noqa: E402


def load_raw(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def report_book(book: str, genre: str, lines: list[str], verbose: bool) -> dict:
    clusters = profile(lines)
    regions = contents_regions(lines)
    print(f"[{genre}] {book}")
    if not clusters:
        print("    no numbered sequence found")
    for region_start, region_end in regions:
        print(f"    contents-shaped region  lines {region_start:>7}-{region_end:<7}")
    for template, found in sorted(
        clusters.items(), key=lambda kv: -sum(len(c.hits) for c in kv[1])
    ):
        spine_hits = sum(len(c.hits) for c in found if not c.is_contents_shaped)
        listing = sum(1 for c in found if c.is_contents_shaped)
        print(f"    {template:9s} {spine_hits:4d} spine hits  {listing} contents-shaped cluster(s)")
        if verbose:
            for c in found:
                tag = "contents" if c.is_contents_shaped else "spine"
                print(
                    f"    {'':9s} {tag:8s} {len(c.hits):4d} hits  "
                    f"lines {c.start:>7}-{c.end:<7}  density {c.density:.3f}"
                )
    return {
        "book": book,
        "genre": genre,
        "templates_found": len(clusters),
        "contents_regions": len(regions),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--raw-dir", type=Path, required=True, help="directory of pg<id>.txt files")
    parser.add_argument(
        "--book-index", type=Path, required=True, help="JSON book index (see module docstring)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="also print each contents run found"
    )
    args = parser.parse_args()

    books = json.loads(args.book_index.read_text())
    summaries = []
    missing = 0
    for row in books:
        raw_path = args.raw_dir / f"pg{row['ebook_id']}.txt"
        if not raw_path.exists():
            missing += 1
            continue
        lines = strip_boilerplate(load_raw(raw_path)).split("\n")
        summaries.append(report_book(row["book"], row["genre"], lines, args.verbose))

    total = len(summaries)
    with_any = sum(1 for s in summaries if s["templates_found"] > 0)
    with_contents = sum(1 for s in summaries if s["contents_regions"] > 0)
    print("\n=== summary ===")
    print(f"{total} books profiled ({missing} skipped, no raw text found)")
    print(f"{with_any} have at least one numbered sequence")
    print(f"{with_contents} have a contents-shaped region")
    return 0


if __name__ == "__main__":
    sys.exit(main())
