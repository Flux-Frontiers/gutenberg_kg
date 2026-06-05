#!/usr/bin/env python3
"""
build_corpus.py — Build a single *consolidated* DocKG over the whole Gutenberg
corpus (or a chosen subset of genres), written to ``bundles/<name>/.dockg/``.

This differs from :mod:`gutenberg_kg.ingest`, which builds one DocKG *per book*
and federates them through the KGRAG registry. Here we walk ``corpus/`` once and
produce a single ``graph.sqlite`` + ``lancedb`` index — the artifact that gets
baked into the standalone "fat image" (Pepys-style: pull, run, query directly).

Genre is recoverable for free at query time: with the walk rooted at ``corpus/``,
every node's ``file_path`` is ``<genre>/<book>/<file>.md``, so the genre is just
the first path segment — no schema change, no tagging pass.

Output layout::

    bundles/
      gutenberg-all/                 # or gutenberg-<genre> for a subset
        .dockg/
          graph.sqlite
          lancedb/

``bundles/`` is gitignored and already in ``[tool.dockg].exclude``, so the
consolidated index is never re-ingested by a stray repo-root ``dockg build``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from gutenberg_kg.genres import ALL_GENRES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPO_ROOT / "corpus"
BUNDLES_ROOT = REPO_ROOT / "bundles"

# Corpus subdirectories that are not book-text genres and must never be folded
# into the consolidated index (author index pages, the DiaryKG-built diaries).
NON_GENRE_DIRS = {"authors", "diaries"}

# Default cap on SIMILAR_TO out-edges per chunk. Cross-book, cross-author
# similarity is high-signal here (the "Tolstoy vs Dostoevsky" edges), unlike a
# single-author diary — but capping keeps the edge table from exploding.
# See the SIMILAR_TO decision (cap 8, default-on).
DEFAULT_SIMILAR_K = 8


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


@dataclass
class BuildCorpusOptions:
    """Flags controlling a consolidated corpus build."""

    output: str | None = None  # output bundle name; default derived from genres
    similar_k: int = DEFAULT_SIMILAR_K
    discover_similar: bool = True
    n_workers: int = 4
    wipe: bool = True
    dry_run: bool = False
    quiet: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def derive_output_name(genres: list[str], override: str | None) -> str:
    """Return the bundle directory name for a genre selection.

    :param genres: Selected genres (sorted by caller; full set == all genres).
    :param override: Explicit ``--output`` name; wins if given.
    :return: ``gutenberg-all`` for the full corpus, ``gutenberg-<genre>`` for a
             single genre, else a hyphen-joined ``gutenberg-<g1>-<g2>…`` slug.
    """
    if override:
        return override
    if set(genres) == set(ALL_GENRES):
        return "gutenberg-all"
    if len(genres) == 1:
        return f"gutenberg-{genres[0]}"
    return "gutenberg-" + "-".join(genres)


def derive_exclude(genres: list[str]) -> set[str]:
    """Return the set of directory names to prune from the ``corpus/`` walk.

    Excludes every genre *not* selected, the non-genre corpus dirs, and the
    built-in DocKG ``SKIP_DIRS`` (``.git``, ``.dockg``, ``.venv``, …). Pruning
    the unselected genres lets us keep the walk rooted at ``corpus/`` so node
    ``file_path``s stay genre-prefixed regardless of the subset chosen.

    :param genres: Selected genres.
    :return: Directory names to exclude at every level of the walk.
    """
    from doc_kg.dockg import SKIP_DIRS  # pylint: disable=import-outside-toplevel

    unselected = set(ALL_GENRES) - set(genres)
    return unselected | NON_GENRE_DIRS | set(SKIP_DIRS)


def build_catalog(genres: list[str], out_dir: Path) -> tuple[int, int]:
    """Write a ``catalog.json`` sidecar mapping ``<genre>/<book>`` → book metadata.

    Parses each selected book's ``reference.md`` for author, title, and Gutenberg
    ID. The key matches the ``<genre>/<book>`` prefix of every node's
    ``file_path``, so the handler can join author/title onto a hit at query time
    — no node-schema change, and the file bakes into the image alongside the
    index (it lives inside ``.dockg/``).

    :param genres: Selected genres.
    :param out_dir: The bundle's ``.dockg/`` directory (where the index lives).
    :return: ``(books_catalogued, books_with_author)``.
    """
    from gutenberg_kg.authors import parse_reference  # pylint: disable=import-outside-toplevel

    catalog: dict[str, dict] = {}
    with_author = 0
    for genre in genres:
        for ref in sorted((CORPUS_ROOT / genre).glob("*/reference.md")):
            meta = parse_reference(ref)
            key = f"{genre}/{ref.parent.name}"  # matches file_path prefix
            catalog[key] = {
                "genre": genre,
                "book": ref.parent.name,
                "title": meta.get("title"),
                "author": meta.get("author"),
                "author_birth": meta.get("author_birth"),
                "author_death": meta.get("author_death"),
                "author_url": meta.get("author_url"),
                "ebook_id": meta.get("ebook_id"),
            }
            if meta.get("author"):
                with_author += 1

    (out_dir / "catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return len(catalog), with_author


def _dir_size_mb(path: Path) -> float:
    """Total size of *path* (recursively) in megabytes."""
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / 1024 / 1024


def fmt_duration(seconds: float) -> str:
    """Human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def run_build_corpus(genres: list[str], opts: BuildCorpusOptions) -> int:
    """Build one consolidated DocKG over the selected genres.

    :param genres: Genre names to include (already validated; empty == all).
    :param opts: Build option flags.
    :return: 0 on success, 1 on failure.
    """
    genres = sorted(genres) if genres else list(ALL_GENRES)
    name = derive_output_name(genres, opts.output)
    exclude = derive_exclude(genres)
    out_dir = BUNDLES_ROOT / name / ".dockg"
    sqlite_path = out_dir / "graph.sqlite"
    lancedb_path = out_dir / "lancedb"

    n_books = sum(
        1
        for g in genres
        for p in (CORPUS_ROOT / g).iterdir()
        if (CORPUS_ROOT / g).is_dir() and p.is_dir() and not p.name.startswith(".")
    )

    print("=== gutenkg build-corpus ===")
    print(f"  bundle        : {name}")
    print(f"  output        : {out_dir}")
    print(
        f"  genres        : {len(genres)} ({'all' if set(genres) == set(ALL_GENRES) else ', '.join(genres)})"
    )
    print(f"  books         : ~{n_books}")
    print(f"  similar_k     : {opts.similar_k if opts.discover_similar else 'disabled'}")
    print(f"  embed workers : {opts.n_workers}")
    print()

    if opts.dry_run:
        print("[dry-run] would walk corpus/ excluding:")
        print(f"          {sorted(exclude)}")
        print(f"[dry-run] would write {sqlite_path} + {lancedb_path}")
        print(f"[dry-run] would write {out_dir / 'catalog.json'} (author/title per book)")
        return 0

    try:
        from doc_kg.index import (  # pylint: disable=import-outside-toplevel
            SentenceTransformerEmbedder,
        )
        from doc_kg.kg import DocKG  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        print(f"[x] doc_kg not installed (needed for build-corpus): {exc}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    embedder = SentenceTransformerEmbedder()
    print(f"  [embedder] {embedder!r}\n")

    kg = DocKG(
        corpus_root=CORPUS_ROOT,
        db_path=sqlite_path,
        lancedb_dir=lancedb_path,
        exclude=exclude,
        embedder=embedder,
    )

    try:
        print("[1/3] parsing corpus → SQLite …")
        kg.build_graph(wipe=opts.wipe, quiet=opts.quiet)

        print("[2/3] embedding nodes …")
        cache_path = out_dir / "embeddings.json"
        kg.build_embeddings(out=cache_path, n_workers=opts.n_workers, quiet=opts.quiet)

        print("[3/3] building LanceDB index + SIMILAR_TO edges …")
        stats = kg.build_index_from_cache(
            cache_path,
            wipe=opts.wipe,
            discover_similar=opts.discover_similar,
            similar_k=opts.similar_k,
            quiet=opts.quiet,
        )
        kg.close()
        cache_path.unlink(missing_ok=True)

        print("[+] writing catalog.json (author/title from reference.md) …")
        n_cat, n_auth = build_catalog(genres, out_dir)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"[x] build failed: {exc}")
        return 1

    elapsed = time.perf_counter() - t0
    size_mb = _dir_size_mb(out_dir)

    print()
    print("=== build complete ===")
    print(f"  bundle        : {name}")
    print(f"  nodes         : {stats.total_nodes:,}")
    print(f"  edges         : {stats.total_edges:,}")
    if stats.similar_edges_added is not None:
        print(f"  SIMILAR_TO    : {stats.similar_edges_added:,}")
    print(f"  catalog       : {n_cat} books ({n_auth} with author)")
    print(f"  index size    : {size_mb:,.1f} MB")
    print(f"  elapsed       : {fmt_duration(elapsed)}")
    print(f"  written to    : {out_dir}")
    print()
    return 0
