"""Which HEADING_PATTERNS actually fire, across the whole cached corpus.

Step 4 of analysis/STRUCTURAL_PARSER_PLAN.md asks which of the vocabulary is
dead. Guessing from the regexes is how live patterns get deleted, so this
counts instead: every line of every cached raw text is run past the patterns
in order, and the first one that matches is credited with the hit -- the same
first-match-wins order _is_heading uses, so a pattern shadowed by an earlier
one correctly scores zero.

Reports per pattern: how many lines it claimed, in how many books, and a
sample, so a pattern with a handful of hits can be judged rather than counted.

Needs raw Gutenberg text, which this repo does not cache (conversion happens
at download time). Point --raw-dir at a directory of ``pg<id>.txt`` files and
--book-index at a JSON list of ``{"book", "genre", "ebook_id"}`` rows, the same
inputs scripts/profile_structure.py takes.

Usage:
    python scripts/census_heading_patterns.py --raw-dir <dir> --book-index <file>
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from gutenberg_kg.gutenberg import strip_boilerplate  # noqa: E402
from gutenberg_kg.headings import HEADING_PATTERNS  # noqa: E402

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument("--raw-dir", type=Path, required=True)
parser.add_argument("--book-index", type=Path, required=True)
args = parser.parse_args()

hits = defaultdict(int)
books = defaultdict(set)
samples = defaultdict(list)

rows = json.loads(args.book_index.read_text())
for row in rows:
    p = args.raw_dir / f"pg{row['ebook_id']}.txt"
    if not p.exists():
        continue
    data = p.read_bytes()
    try:
        raw = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = data.decode("latin-1")
    for line in strip_boilerplate(raw).split("\n"):
        stripped = line.strip()
        if not stripped or len(stripped) > 120:
            continue
        for idx, (pattern, _level) in enumerate(HEADING_PATTERNS):
            if pattern.match(stripped):
                hits[idx] += 1
                books[idx].add(row["book"])
                if len(samples[idx]) < 3 and stripped not in samples[idx]:
                    samples[idx].append(stripped)
                break

print(f"{len(HEADING_PATTERNS)} patterns, {len(rows)} books\n")
for idx, (pattern, level) in enumerate(HEADING_PATTERNS):
    n, nb = hits[idx], len(books[idx])
    flag = "  <-- DEAD" if n == 0 else ""
    src = pattern.pattern.replace("\n", " ")[:66]
    print(f"[{idx:2d}] h{level}  {n:6d} lines  {nb:3d} books{flag}")
    print(f"      {src}")
    for s in samples[idx]:
        print(f"      e.g. {s[:74]!r}")
    if 0 < n <= 12:
        print(f"      books: {sorted(books[idx])[:4]}")
    print()
