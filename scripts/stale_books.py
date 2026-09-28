#!/usr/bin/env python3
# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
List prose books whose index is older than their text, and a stale bundle.

A book's text changes when it is downloaded again (``--force``), when its
reference.md is rewritten (``gutenkg authors --refresh``), or when a pull
brings in someone else's edit. Nothing downstream notices: the per-book
``.dockg/`` keeps the old chunks, and ``gutenkg build-corpus --update`` keeps
the old vectors because it matches on node ids, not content. This script
compares modification times so the stale surfaces can be named:

- a book whose ``*.md`` is newer than its ``.dockg/graph.sqlite``, or which
  has no index at all;
- the bundle, when any per-book index is newer than
  ``bundles/<bundle>/.dockg/graph.sqlite``.

Diaries are skipped: they are indexed into ``.diarykg/`` by
``make build-diaries``, which always rebuilds them.

Exit status is 1 when anything is stale, so ``make refresh-text`` can use it
as a gate. The last line prints the command that refreshes what it found.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKIP_GENRES = {"authors", "diaries"}


def book_dirs(corpus: Path) -> list[Path]:
    """Return every prose book directory under the corpus, sorted.

    :param corpus: The corpus root, ``corpus/``.
    :return: Directories of the form ``corpus/<genre>/<book>/`` that hold text.
    """
    return sorted(
        d
        for genre in corpus.iterdir()
        if genre.is_dir() and genre.name not in SKIP_GENRES
        for d in genre.iterdir()
        if d.is_dir() and any(d.glob("*.md"))
    )


def stale_books(corpus: Path) -> list[tuple[Path, str]]:
    """Return books whose index is missing or older than their text.

    :param corpus: The corpus root.
    :return: ``(book_dir, reason)`` pairs.
    """
    out = []
    for d in book_dirs(corpus):
        graph = d / ".dockg" / "graph.sqlite"
        if not graph.exists():
            out.append((d, "no index"))
            continue
        built = graph.stat().st_mtime
        newer = [p.name for p in d.glob("*.md") if p.stat().st_mtime > built]
        if newer:
            out.append((d, "text newer than index: " + ", ".join(sorted(newer))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--corpus", type=Path, default=Path("corpus"))
    ap.add_argument("--bundle", default="gutenberg-all")
    args = ap.parse_args()

    stale = stale_books(args.corpus)
    for d, reason in stale:
        print(f"book    {d.relative_to(args.corpus)}  ({reason})")

    bundle_graph = Path("bundles") / args.bundle / ".dockg" / "graph.sqlite"
    newest = max(
        (p.stat().st_mtime for p in args.corpus.glob("*/*/.dockg/graph.sqlite")),
        default=0.0,
    )
    bundle_stale = not bundle_graph.exists() or bundle_graph.stat().st_mtime < newest
    if bundle_stale:
        print(f"bundle  bundles/{args.bundle}  (older than a per-book index)")

    if not stale and not bundle_stale:
        print("Nothing stale.")
        return 0

    genres = sorted({d.parent.name for d, _ in stale})
    if genres:
        print(f'\nRefresh with: make refresh-text GENRE="{" ".join(genres)}"')
    else:
        print(
            "\nPer-book indices are current; rebuild the bundle and everything "
            'after it with: make refresh-text GENRE=""'
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
