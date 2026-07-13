#!/usr/bin/env python3
"""Build the consolidated ``gutenberg-all`` DocKG bundle one genre at a time.

Why this exists
---------------
``gutenkg build-corpus`` embeds the whole corpus (~690k nodes) in a single
pass. On CPU that path (doc_kg → kg_utils ``CorpusEmbedder``) holds every
shard's vectors in RAM until the end, so the parent process balloons to
~10+ GB and drives a memory-constrained Mac deep into swap (observed: 45 GB
swap used, throughput collapsing). This script bounds peak memory by embedding
**one genre per pass** and upserting into the shared index, so the in-RAM
vector set is only ever one genre's worth (tens of thousands of nodes).

It produces the *same* consolidated bundle at ``bundles/gutenberg-all/.dockg/``
(single graph.sqlite + one LanceDB index spanning all genres, genre recoverable
from each node's ``file_path`` prefix) — just assembled incrementally.

Model: a genre is the unit of change. You can ``build`` the whole set, ``add``
a genre, or ``delete`` a genre; each finalizes the FTS index + catalog over
whatever genres remain. Diaries are handled as in ``build-corpus`` — their
prebuilt ``.diarykg`` indices are copied verbatim, never embedded here.

Usage
-----
    # Full build, low memory (resumable: re-run to add only missing genres):
    poetry run python scripts/build_corpus_by_genre.py build

    # Force a clean rebuild from scratch:
    poetry run python scripts/build_corpus_by_genre.py build --fresh

    # Add or remove a single genre against the existing bundle:
    poetry run python scripts/build_corpus_by_genre.py add horror
    poetry run python scripts/build_corpus_by_genre.py delete travel

    # Gentler / faster embedding (fewer workers = less RAM, more = faster):
    poetry run python scripts/build_corpus_by_genre.py build --workers 2

This is a stopgap. The real fix — streaming shard vectors to disk so the full
single-pass build stays flat in memory — is handed off to kg_utils in
``../kg_utils/HANDOFF_STREAMING_EMBED.md``.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

from gutenberg_kg.build_corpus import (
    BUNDLES_ROOT,
    CORPUS_ROOT,
    GENRE_STRATEGY,
    build_catalog,
    bundle_diaries,
    derive_exclude,
    ensure_diaries_built,
    fmt_duration,
)
from gutenberg_kg.cli.options import ALL_GENRES

# Diaries are copied verbatim (prebuilt .diarykg), never parsed/embedded here.
SKIP_GENRES = {"diaries"}
DEFAULT_SIMILAR_MAX_DEGREE = 8  # matches per-book ingest; SIMILAR_TO discovery stays off


def _present_genres(sqlite_path: Path) -> set[str]:
    """Return the set of genres that already have nodes in the bundle graph."""
    if not sqlite_path.exists():
        return set()
    con = sqlite3.connect(str(sqlite_path))
    try:
        rows = con.execute(
            "SELECT DISTINCT substr(file_path, 1, instr(file_path, '/') - 1) AS g "
            "FROM nodes WHERE file_path LIKE '%/%'"
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in rows if r[0]}


def _sync_counts(sqlite_path: Path, lancedb_path: Path) -> tuple[int, int]:
    """Return (indexable graph nodes, indexed vectors) to detect graph/index drift."""
    from doc_kg.kg import DocKG  # noqa: PLC0415

    kg = DocKG(corpus_root=CORPUS_ROOT, db_path=sqlite_path, lancedb_dir=lancedb_path)
    try:
        g_nodes = len(kg.store.query_nodes(kinds=list(kg.index.index_kinds)))
        i_vecs = len(kg.index._existing_index_ids())
    finally:
        kg.close()
    return g_nodes, i_vecs


def _make_embedder():
    """Build the CPU embedder and pin all embedding workers to CPU.

    Pinning via ``KG_EMBED_DEVICE`` is what stops each spawned CorpusEmbedder
    worker from auto-selecting MPS and stacking N GPU allocations into an OOM.
    """
    os.environ["KG_EMBED_DEVICE"] = "cpu"
    from doc_kg.index import make_embedder  # noqa: PLC0415

    return make_embedder(device="cpu")


def _add_genre(
    genre: str,
    *,
    sqlite_path: Path,
    lancedb_path: Path,
    embedder,
    first: bool,
    workers: int,
    batch_size: int,
    quiet: bool,
) -> None:
    """Parse + embed + upsert one genre into the shared bundle.

    ``first`` wipes the graph and index (fresh bundle). Otherwise the genre is
    appended: the graph grows, and only nodes not already vectorized are
    embedded (``only_missing``), so peak RAM is one genre's vectors — not the
    whole corpus.
    """
    from doc_kg.kg import DocKG  # noqa: PLC0415

    strategy = {**GENRE_STRATEGY}.get(genre, "semantic")
    kg = DocKG(
        corpus_root=CORPUS_ROOT,
        db_path=sqlite_path,
        lancedb_dir=lancedb_path,
        exclude=derive_exclude([genre]),
        embedder=embedder,
        chunk_strategy=strategy,
    )
    try:
        kg.build_graph(wipe=first, quiet=quiet)
        # .jsonl routes CPU embedding through CorpusEmbedder.embed_to_cache — parallel
        # AND streamed to disk, so peak RAM is one shard, not the whole genre.
        cache = sqlite_path.parent / "embeddings.jsonl"
        try:
            # only_missing is a no-op on the first pass (empty index) and embeds
            # just this genre's new nodes on every later pass.
            kg.build_embeddings(
                out=cache,
                n_workers=workers,
                batch_size=batch_size,
                only_missing=not first,
                quiet=quiet,
            )
            kg.build_index_from_cache(
                cache,
                wipe=first,
                discover_similar=False,
                similar_max_degree=DEFAULT_SIMILAR_MAX_DEGREE,
                quiet=quiet,
            )
        finally:
            cache.unlink(missing_ok=True)
    finally:
        kg.close()


def _delete_genre(genre: str, *, sqlite_path: Path, lancedb_path: Path, quiet: bool) -> int:
    """Remove one genre's nodes + edges from the graph and prune its vectors.

    :return: Number of graph nodes deleted (0 if the genre was not present).
    """
    if not sqlite_path.exists():
        print(f"  [x] no bundle graph at {sqlite_path}")
        return 0
    from doc_kg.kg import DocKG  # noqa: PLC0415

    like = f"{genre}/%"
    kg = DocKG(corpus_root=CORPUS_ROOT, db_path=sqlite_path, lancedb_dir=lancedb_path)
    try:
        con = kg.store.con
        n = con.execute("SELECT count(*) FROM nodes WHERE file_path LIKE ?", (like,)).fetchone()[0]
        if not n:
            print(f"  genre {genre!r} not present — nothing to delete")
            return 0
        con.execute(
            "DELETE FROM edges WHERE src IN (SELECT id FROM nodes WHERE file_path LIKE ?) "
            "OR dst IN (SELECT id FROM nodes WHERE file_path LIKE ?)",
            (like, like),
        )
        con.execute("DELETE FROM nodes WHERE file_path LIKE ?", (like,))
        con.commit()
        # Drop the now-orphaned vectors from the LanceDB index.
        kg.prune_index(quiet=quiet)
        print(f"  deleted {n:,} nodes for genre {genre!r}")
    finally:
        kg.close()
    return n


def _finalize(sqlite_path: Path, lancedb_path: Path, out_dir: Path, *, quiet: bool) -> None:
    """Rebuild FTS over the full graph, copy diaries, and rewrite the catalog.

    Run once after all per-genre passes so the lexical index and catalog reflect
    the *whole* bundle rather than the last genre touched.
    """
    from doc_kg.kg import DocKG  # noqa: PLC0415

    print("[finalize] rebuilding FTS5 lexical index over the full graph …")
    kg = DocKG(corpus_root=CORPUS_ROOT, db_path=sqlite_path, lancedb_dir=lancedb_path)
    try:
        n_fts = kg.store.rebuild_fts(quiet=quiet)
        print(f"  lexical index: {n_fts:,} chunks")
    finally:
        kg.close()

    present = sorted(_present_genres(sqlite_path))
    print("[finalize] building + bundling DiaryKG indices …")
    if ensure_diaries_built(quiet=quiet) != 0:
        print("  [x] diary build failed (continuing; diaries not bundled)")
    else:
        n_diaries = bundle_diaries(out_dir)
        print(f"  copied {n_diaries} diary index(es)")

    print("[finalize] writing catalog.json …")
    n_cat, n_auth = build_catalog(present, out_dir)
    print(f"  catalog: {n_cat} books ({n_auth} with author) across {len(present)} genre(s)")


def _resolve_paths(output: str) -> tuple[Path, Path, Path]:
    out_dir = BUNDLES_ROOT / output / ".dockg"
    return out_dir, out_dir / "graph.sqlite", out_dir / "lancedb"


def cmd_build(args: argparse.Namespace) -> int:
    out_dir, sqlite_path, lancedb_path = _resolve_paths(args.output)
    requested = [g for g in (args.genres or sorted(ALL_GENRES)) if g not in SKIP_GENRES]

    fresh = args.fresh or not sqlite_path.exists()
    already = set() if fresh else _present_genres(sqlite_path)
    todo = [g for g in requested if g not in already]

    if not fresh and already:
        print(f"  existing bundle has {len(already)} genre(s); adding {len(todo)} missing")
    if not todo and not fresh:
        # Every requested genre is already in the graph. Only safe to no-op if the
        # index is in sync with the graph — otherwise the bundle is a mixed state
        # (e.g. graph re-parsed but vectors stale/partial) and needs --fresh.
        g_nodes, i_vecs = _sync_counts(sqlite_path, lancedb_path)
        if g_nodes == i_vecs:
            print(
                f"  bundle already covers all requested genres (index in sync: {i_vecs:,} vectors)"
            )
            _finalize(sqlite_path, lancedb_path, out_dir, quiet=args.quiet)
            return 0
        print(
            f"  [!] bundle looks out of sync: graph has {g_nodes:,} indexable nodes but the "
            f"index has {i_vecs:,} vectors.\n"
            f"      This happens when graph.sqlite and lancedb come from different runs.\n"
            f"      Re-run with --fresh for a clean, consistent rebuild (bounded memory)."
        )
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    embedder = _make_embedder()
    t0 = time.perf_counter()
    for i, genre in enumerate(todo):
        first = fresh and i == 0
        print(f"\n[{i + 1}/{len(todo)}] {genre}  ({'fresh' if first else 'append'})")
        _add_genre(
            genre,
            sqlite_path=sqlite_path,
            lancedb_path=lancedb_path,
            embedder=embedder,
            first=first,
            workers=args.workers,
            batch_size=args.embed_batch_size,
            quiet=args.quiet,
        )
        print(f"  [+] {genre} indexed")

    _finalize(sqlite_path, lancedb_path, out_dir, quiet=args.quiet)
    print(f"\n=== build complete in {fmt_duration(time.perf_counter() - t0)} → {out_dir} ===")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    out_dir, sqlite_path, lancedb_path = _resolve_paths(args.output)
    if not sqlite_path.exists():
        print(f"  [x] no bundle at {sqlite_path}; run 'build' first")
        return 1
    present = _present_genres(sqlite_path)
    embedder = _make_embedder()
    for genre in args.genres:
        if genre in SKIP_GENRES:
            print(f"  skipping {genre!r} (handled via diaries bundling)")
            continue
        if genre in present:
            print(f"  {genre!r} already present — delete first to re-add; skipping")
            continue
        print(f"\n[add] {genre}")
        _add_genre(
            genre,
            sqlite_path=sqlite_path,
            lancedb_path=lancedb_path,
            embedder=embedder,
            first=False,
            workers=args.workers,
            batch_size=args.embed_batch_size,
            quiet=args.quiet,
        )
        print(f"  [+] {genre} indexed")
    _finalize(sqlite_path, lancedb_path, out_dir, quiet=args.quiet)
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    out_dir, sqlite_path, lancedb_path = _resolve_paths(args.output)
    any_deleted = False
    for genre in args.genres:
        print(f"\n[delete] {genre}")
        if _delete_genre(
            genre, sqlite_path=sqlite_path, lancedb_path=lancedb_path, quiet=args.quiet
        ):
            any_deleted = True
    if any_deleted:
        _finalize(sqlite_path, lancedb_path, out_dir, quiet=args.quiet)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Shared options live on a parent parser so they can follow the subcommand
    # (e.g. `build --output X --workers 2`), which reads more naturally.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--output",
        default="gutenberg-all",
        help="Bundle name under bundles/ (default: gutenberg-all).",
    )
    common.add_argument(
        "--workers",
        type=int,
        default=2,
        help="CPU embedding workers per genre (default: 2; raise for speed, lower for RAM).",
    )
    common.add_argument(
        "--embed-batch-size",
        type=int,
        default=64,
        help="Embedding encode() batch size (default: 64).",
    )
    common.add_argument(
        "--quiet", action="store_true", help="Suppress per-stage DocKG progress output."
    )

    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser(
        "build", parents=[common], help="Build the consolidated bundle genre-by-genre (resumable)."
    )
    b.add_argument("--fresh", action="store_true", help="Wipe and rebuild from scratch.")
    b.add_argument("--genres", nargs="*", help="Genres to include (default: all non-diary genres).")
    b.set_defaults(func=cmd_build)

    a = sub.add_parser(
        "add", parents=[common], help="Add one or more genres to the existing bundle."
    )
    a.add_argument("genres", nargs="+")
    a.set_defaults(func=cmd_add)

    d = sub.add_parser(
        "delete", parents=[common], help="Delete one or more genres from the existing bundle."
    )
    d.add_argument("genres", nargs="+")
    d.set_defaults(func=cmd_delete)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
