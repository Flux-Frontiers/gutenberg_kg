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

Chunk strategies are applied per-genre group.  Sacred texts (Bible KJV, Quran,
Torah, etc.) use the ``verse`` chunker which honours ``chapter:verse`` numbering.
All other genres default to ``semantic``.  Override via ``--strategy genre:strategy``
or the ``strategy_overrides`` field on :class:`BuildCorpusOptions`.

DiaryKG indices (already built per-diary with temporal metadata) are **not**
re-ingested through DocKG.  Instead, each ``corpus/diaries/*/.diarykg/`` index
is copied verbatim into ``bundles/<name>/diaries/``; the handler can register
both the DocKG and the DiaryKG indices through KGRAG.

Output layout::

    bundles/
      gutenberg-all/
        .dockg/
          graph.sqlite
          lancedb/
          catalog.json
        diaries/
          pepys-complete/.diarykg/
          evelyn-vol1/.diarykg/
          …

``bundles/`` is gitignored and already in ``[tool.dockg].exclude``, so the
consolidated index is never re-ingested by a stray repo-root ``dockg build``.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
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

# Per-genre default chunk strategy.  Genres not listed here get "semantic".
# "verse" fires the VerseChunker which respects chapter:verse numbering and
# also auto-detects verse format (>10% of lines match ^\d+:\d+\s).
GENRE_STRATEGY: dict[str, str] = {
    "sacred-texts": "verse",
}


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
    # Per-genre chunk strategy overrides (merged on top of GENRE_STRATEGY).
    # Keys are genre names; values are DocKG strategy strings: "semantic",
    # "sentence_group", "fixed", or "verse".
    strategy_overrides: dict[str, str] = field(default_factory=dict)


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
    from doc_kg.dockg import SKIP_DIRS

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
    from gutenberg_kg.authors import parse_reference

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


def bundle_diaries(out_dir: Path) -> int:
    """Copy existing ``.diarykg/`` indices from ``corpus/diaries/`` into the bundle.

    DiaryKG indices carry temporal metadata (YAML timestamps, diary-specific
    chunks) that DocKG's semantic pipeline cannot reproduce.  We copy them
    verbatim so the handler can register both ``KGKind.GUTENBERG`` (the DocKG
    index) and ``KGKind.DIARY`` (each DiaryKG) through KGRAG — without
    re-ingesting the diaries.

    Destination layout::

        bundles/<name>/diaries/<diary-name>/.diarykg/

    :param out_dir: The bundle's ``.dockg/`` directory (sibling of ``diaries/``).
    :return: Number of diary indices copied.
    """
    import shutil

    diaries_root = CORPUS_ROOT / "diaries"
    if not diaries_root.exists():
        return 0

    bundle_diaries_dir = out_dir.parent / "diaries"
    n = 0
    for diary_dir in sorted(diaries_root.iterdir()):
        if not diary_dir.is_dir() or diary_dir.name.startswith("."):
            continue
        diarykg_dir = diary_dir / ".diarykg"
        if not diarykg_dir.exists():
            continue
        dest = bundle_diaries_dir / diary_dir.name / ".diarykg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(diarykg_dir), str(dest), dirs_exist_ok=True)
        n += 1
    return n


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

    Genres are grouped by their effective chunk strategy, then each group is
    walked and parsed into the *same* ``graph.sqlite`` (first group wipes, the
    rest append).  A single embedding pass and a single LanceDB index pass run
    over the combined node table.  Finally, any DiaryKG indices found under
    ``corpus/diaries/`` are copied verbatim into the bundle.

    :param genres: Genre names to include (already validated; empty == all).
    :param opts: Build option flags.
    :return: 0 on success, 1 on failure.
    """
    genres = sorted(genres) if genres else list(ALL_GENRES)
    name = derive_output_name(genres, opts.output)
    out_dir = BUNDLES_ROOT / name / ".dockg"
    sqlite_path = out_dir / "graph.sqlite"
    lancedb_path = out_dir / "lancedb"

    # Effective strategy: defaults merged with caller overrides.
    effective_strategy: dict[str, str] = {**GENRE_STRATEGY, **opts.strategy_overrides}

    # Group genres by chunk strategy.
    strategy_groups: dict[str, list[str]] = defaultdict(list)
    for genre in genres:
        strategy = effective_strategy.get(genre, "semantic")
        strategy_groups[strategy].append(genre)

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
    print("  strategy groups:")
    for strategy, sg_genres in sorted(strategy_groups.items()):
        print(f"    {strategy:16s} : {', '.join(sorted(sg_genres))}")
    print()

    if opts.dry_run:
        print("[dry-run] phase 1: build graph — sequential per strategy group:")
        for strategy, sg_genres in sorted(strategy_groups.items()):
            sg_exclude = derive_exclude(sg_genres)
            print(f"  strategy={strategy}, genres={sorted(sg_genres)}")
            print(f"    exclude={sorted(sg_exclude)}")
        print(f"[dry-run] phase 2: embed all nodes → {sqlite_path}")
        print(f"[dry-run] phase 3: lancedb index + SIMILAR_TO → {lancedb_path}")
        print("[dry-run] phase 4: bundle DiaryKG indices → bundles dir")
        print(f"[dry-run] would write {out_dir / 'catalog.json'} (author/title per book)")
        return 0

    try:
        from doc_kg.index import SentenceTransformerEmbedder
        from doc_kg.kg import DocKG
    except ImportError as exc:
        print(f"[x] doc_kg not installed (needed for build-corpus): {exc}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    embedder = SentenceTransformerEmbedder()
    print(f"  [embedder] {embedder!r}\n")

    try:
        # ------------------------------------------------------------------
        # Phase 1: parse each strategy group into the shared SQLite graph.
        # First group wipes (if opts.wipe); subsequent groups append.
        # ------------------------------------------------------------------
        n_groups = len(strategy_groups)
        print(f"[1/4] parsing corpus → SQLite ({n_groups} strategy group(s)) …")
        first = True
        for strategy, sg_genres in sorted(strategy_groups.items()):
            sg_exclude = derive_exclude(sg_genres)
            print(f"  [{strategy}] {', '.join(sorted(sg_genres))}")
            kg = DocKG(
                corpus_root=CORPUS_ROOT,
                db_path=sqlite_path,
                lancedb_dir=lancedb_path,
                exclude=sg_exclude,
                embedder=embedder,
                chunk_strategy=strategy,
            )
            kg.build_graph(wipe=first and opts.wipe, quiet=opts.quiet)
            kg.close()
            first = False

        # ------------------------------------------------------------------
        # Phase 2: embed all nodes in the combined graph.
        # ------------------------------------------------------------------
        print("[2/4] embedding nodes …")
        kg_all = DocKG(
            corpus_root=CORPUS_ROOT,
            db_path=sqlite_path,
            lancedb_dir=lancedb_path,
            embedder=embedder,
        )
        cache_path = out_dir / "embeddings.json"
        kg_all.build_embeddings(out=cache_path, n_workers=opts.n_workers, quiet=opts.quiet)

        # ------------------------------------------------------------------
        # Phase 3: build LanceDB index + SIMILAR_TO edges.
        # ------------------------------------------------------------------
        print("[3/4] building LanceDB index + SIMILAR_TO edges …")
        stats = kg_all.build_index_from_cache(
            cache_path,
            wipe=opts.wipe,
            discover_similar=opts.discover_similar,
            similar_k=opts.similar_k,
            quiet=opts.quiet,
        )
        kg_all.close()
        cache_path.unlink(missing_ok=True)

        # ------------------------------------------------------------------
        # Phase 4: bundle DiaryKG indices (copy, do not re-ingest).
        # ------------------------------------------------------------------
        print("[4/4] bundling DiaryKG indices …")
        n_diaries = bundle_diaries(out_dir)
        if n_diaries:
            print(f"  copied {n_diaries} diary index(es) → bundles/{name}/diaries/")
        else:
            print("  (no .diarykg indices found under corpus/diaries/)")

        print("[+] writing catalog.json (author/title from reference.md) …")
        n_cat, n_auth = build_catalog(genres, out_dir)

    except Exception as exc:  # noqa: BLE001
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
    print(f"  diaries       : {n_diaries} index(es) bundled")
    print(f"  index size    : {size_mb:,.1f} MB")
    print(f"  elapsed       : {fmt_duration(elapsed)}")
    print(f"  written to    : {out_dir}")
    print()
    return 0
