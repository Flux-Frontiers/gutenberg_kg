# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Find prose books whose index is older than their text, and a stale bundle.

A book's text changes when it is downloaded again (``--force``), when its
reference.md is rewritten (``gutenkg authors --refresh``), or when a pull
brings in someone else's edit. Nothing downstream notices: the per-book
``.dockg/`` keeps the old chunks, and ``gutenkg build-corpus --update`` keeps
the old vectors because it matches on node ids, not content. Comparing
modification times names the stale surfaces:

- a book whose ``*.md`` is newer than its ``.dockg/graph.sqlite``, or which
  has no index at all;
- the bundle, when any per-book index is newer than
  ``bundles/<bundle>/.dockg/graph.sqlite``.

Diaries are skipped: they are indexed into ``.diarykg/`` by
``make build-diaries``, which always rebuilds them.
"""

from __future__ import annotations

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


def bundle_is_stale(corpus: Path, bundle: Path) -> bool:
    """Return whether the bundle is missing or older than a per-book index.

    :param corpus: The corpus root.
    :param bundle: The bundle directory, e.g. ``bundles/gutenberg-all``.
    :return: True when ``bundle/.dockg/graph.sqlite`` is missing or older than
        the newest ``corpus/<genre>/<book>/.dockg/graph.sqlite``.
    """
    graph = bundle / ".dockg" / "graph.sqlite"
    newest = max(
        (p.stat().st_mtime for p in corpus.glob("*/*/.dockg/graph.sqlite")),
        default=0.0,
    )
    return not graph.exists() or graph.stat().st_mtime < newest
