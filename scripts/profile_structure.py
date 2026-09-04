"""Report the numbered sequences gutenberg_kg.spine finds in the corpus.

Step 1 of analysis/STRUCTURAL_PARSER_PLAN.md: read-only, no behaviour
change. Converts nothing; prints what spine and contents runs each book's
raw text contains, so the density-separation hypothesis can be read against
the whole corpus before anything is built on it.

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
from gutenberg_kg.spine import Classification, classify, profile  # noqa: E402


def load_raw(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def report_book(book: str, genre: str, lines: list[str], verbose: bool) -> dict:
    result = profile(lines)
    classifications: dict[str, Classification] = {}
    for template, runs in result.items():
        c = classify(runs)
        if c is not None:
            classifications[template] = c

    with_contents = [c for c in classifications.values() if c.contents is not None]
    print(f"[{genre}] {book}")
    if not classifications:
        print("    no numbered sequence found")
    for template, c in sorted(
        classifications.items(), key=lambda kv: -len(kv[1].spine.hits) if kv[1].spine else 0
    ):
        s = c.spine
        tag = "spine+contents" if c.contents else "spine only"
        print(
            f"    {template:9s} {tag:15s} {len(s.hits):4d} hits  "
            f"lines {s.start:>7}-{s.end:<7}  density {s.density:.3f}  nums {s.first_number}..{s.last_number}"
        )
        if c.contents and verbose:
            k = c.contents
            print(
                f"    {'':9s} {'  contents':15s} {len(k.hits):4d} hits  "
                f"lines {k.start:>7}-{k.end:<7}  density {k.density:.3f}  nums {k.first_number}..{k.last_number}"
            )
    return {
        "book": book,
        "genre": genre,
        "templates_found": len(classifications),
        "spine_and_contents_found": len(with_contents),
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
    with_pair = sum(1 for s in summaries if s["spine_and_contents_found"] > 0)
    print("\n=== summary ===")
    print(f"{total} books profiled ({missing} skipped, no raw text found)")
    print(f"{with_any} have at least one numbered sequence")
    print(f"{with_pair} have a spine paired with its own contents list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
