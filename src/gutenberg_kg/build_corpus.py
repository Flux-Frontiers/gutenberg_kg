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

Author: Eric G. Suchanek, PhD
Last Revision: 2026-06-06 19:13:24
License: Elastic 2.0
"""

from __future__ import annotations

import json
import os
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

# Default cap on SIMILAR_TO out-edges per chunk, applied only when discovery is
# explicitly enabled (--similar). Cross-book, cross-author similarity is
# high-signal (the "Tolstoy vs Dostoevsky" edges), but the served handler is
# semantic-first and never traverses these edges, so consolidated builds default
# to NOT discovering them — recomputing ~800k edges only bloats the shipped
# graph.sqlite. The cap-8 SIMILAR_TO validation applies to DocKG.query()'s
# hop-expansion path (per-book CLI queries, viz3d arcs), not this bundle.
DEFAULT_SIMILAR_K = 8

# Per-genre default chunk strategy.  Genres not listed here get "semantic".
# "verse" fires the VerseChunker which respects chapter:verse numbering and
# also auto-detects verse format (>10% of lines match ^\d+:\d+\s).
# sacred-texts is NOT listed here: only the KJV Bible uses N:M verse format,
# and it lives in ancient-classical. The other sacred texts are prose translations
# that auto-detection correctly leaves as "semantic".
GENRE_STRATEGY: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


@dataclass
class BuildCorpusOptions:
    """Flags controlling a consolidated corpus build."""

    output: str | None = None  # output bundle name; default derived from genres
    similar_k: int = DEFAULT_SIMILAR_K
    similar_max_degree: int = DEFAULT_SIMILAR_K  # hard per-node degree cap
    discover_similar: bool = False  # served handler never traverses SIMILAR_TO; opt-in only
    n_workers: int = 4
    embed_batch_size: int = 64
    embed_device: str = "auto"  # auto|cpu|mps|cuda
    wipe: bool = True
    update: bool = False  # incremental: embed only new/changed nodes, upsert, prune
    dry_run: bool = False
    quiet: bool = False
    diaries_only: bool = False  # skip phases 1-3; re-bundle diary indices only
    # Per-genre chunk strategy overrides (merged on top of GENRE_STRATEGY).
    # Keys are genre names; values are DocKG strategy strings: "semantic",
    # "sentence_group", "fixed", or "verse".
    strategy_overrides: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mps_available() -> bool:
    """Return True when torch reports a usable MPS backend.

    :return: ``True`` if MPS is available; ``False`` on any import/probe failure.
    """
    try:
        import torch  # pylint: disable=import-outside-toplevel

        return bool(torch.backends.mps.is_available())
    except Exception:  # noqa: BLE001
        return False


def _cuda_available() -> bool:
    """Return True when torch reports a usable CUDA backend.

    :return: ``True`` if CUDA is available; ``False`` on any import/probe failure.
    """
    try:
        import torch  # pylint: disable=import-outside-toplevel

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        return False


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
        if dest.exists() or dest.is_symlink():
            shutil.rmtree(dest)
        shutil.copytree(str(diarykg_dir), str(dest), symlinks=True)
        n += 1
    return n


def ensure_diaries_built(dry_run: bool = False, quiet: bool = False) -> int:
    """Reconstruct any unbuilt diary indices so :func:`bundle_diaries` finds them.

    Runs the DiaryKG pipeline — ``chunk-diaries`` (``.md`` → ``.diary/``) then
    ``build-diaries`` (``.diary/`` → ``.diarykg/``) — idempotently: diaries that
    already have a ``.diary/`` and ``.diarykg/`` are skipped.  This makes
    ``gutenkg build-corpus`` self-sufficient on a clean clone instead of relying
    on the Makefile to sequence ``build-diaries`` first.

    :param dry_run: Print the plan without executing.
    :param quiet: Suppress per-stage DiaryKG build progress.
    :return: 0 on success, 1 if chunking or building any diary failed.
    """
    from gutenberg_kg.build_diaries import BuildDiariesOptions, run_build_diaries
    from gutenberg_kg.diary.chunk import ChunkDiariesOptions, run_chunk_diaries

    rc = run_chunk_diaries([], ChunkDiariesOptions(force=False, dry_run=dry_run))
    if rc != 0:
        return rc
    return run_build_diaries([], BuildDiariesOptions(force=False, dry_run=dry_run, quiet=quiet))


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
    _mode = {
        "cpu": f"parallel (CPU multiprocessing, {opts.n_workers} workers)",
        "mps": "streaming (single-process; GPU can't be shared across workers)",
        "cuda": "streaming (single-process; GPU can't be shared across workers)",
    }.get(
        opts.embed_device,
        "auto → streaming MPS (single-process)"
        if _mps_available()
        else f"auto → parallel CPU ({opts.n_workers} workers)",
    )
    print(f"  embed mode    : {_mode}")
    print(f"  embed batch   : {opts.embed_batch_size}")
    print(f"  embed device  : {opts.embed_device}")
    print()
    print("  strategy groups:")
    for strategy, sg_genres in sorted(strategy_groups.items()):
        print(f"    {strategy:16s} : {', '.join(sorted(sg_genres))}")
    print()

    if opts.diaries_only:
        print("[diaries-only] skipping phases 1-3; building + bundling diary indices …")
        if ensure_diaries_built(dry_run=opts.dry_run, quiet=opts.quiet) != 0:
            print("[x] diary build failed")
            return 1
        try:
            n_diaries = bundle_diaries(out_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"[x] bundle_diaries failed: {exc}")
            return 1
        if n_diaries:
            print(f"  copied {n_diaries} diary index(es) → bundles/{name}/diaries/")
        else:
            print("  (no .diarykg indices found under corpus/diaries/)")
        return 0

    if opts.dry_run:
        print("[dry-run] phase 1: build graph — sequential per strategy group:")
        for strategy, sg_genres in sorted(strategy_groups.items()):
            sg_exclude = derive_exclude(sg_genres)
            print(f"  strategy={strategy}, genres={sorted(sg_genres)}")
            print(f"    exclude={sorted(sg_exclude)}")
        print(f"[dry-run] phase 2: embed all nodes → {sqlite_path}")
        print(f"[dry-run] phase 3: lancedb index + SIMILAR_TO → {lancedb_path}")
        print("[dry-run] phase 4: build (if needed) + bundle DiaryKG indices → bundles dir")
        print(f"[dry-run] would write {out_dir / 'catalog.json'} (author/title per book)")
        return 0

    try:
        from doc_kg.index import make_embedder
        from doc_kg.kg import DocKG
    except ImportError as exc:
        print(f"[x] doc_kg not installed (needed for build-corpus): {exc}")
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    # Build the embedder on the requested device. The consolidated build embeds
    # 700k+ nodes in one pass; on Apple MPS the unified-memory watermark contends
    # with the system file cache and OOMs on "other allocations", so
    # `--embed-device cpu` is the reliable choice for the full corpus.
    if opts.embed_device == "mps" and not _mps_available():
        print("[x] --embed-device mps requested but MPS is not available")
        return 1
    if opts.embed_device == "cuda" and not _cuda_available():
        print("[x] --embed-device cuda requested but CUDA is not available")
        return 1
    try:
        embedder = make_embedder(device=opts.embed_device)
    except Exception as exc:  # noqa: BLE001
        print(f"[x] failed to build embedder on device {opts.embed_device!r}: {exc}")
        return 1
    print(f"  [embedder] {embedder!r}  (device={opts.embed_device})\n")

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
        # Resolve the effective device to pick the embedding path: CPU can fan
        # out across processes safely; MPS/CUDA cannot (one shared allocator).
        # `auto` prefers a GPU when available (MPS on Macs, CUDA elsewhere —
        # e.g. RunPod), falling back to parallel CPU when no GPU is present.
        #
        # CAUTION: unlike `dockg build-index` (SemanticIndex.build(), which
        # hard-caps its encode sub-batch at 128 — doc_kg PR #7 / kgmodule-utils
        # 0.4.6), this streaming path (DocKG.build_embeddings ->
        # precompute_embeddings -> _precompute_embeddings_jsonl_stream) has NO
        # internal cap: --embed-batch-size is passed straight to
        # model.encode() uncapped. It's safe today only because our own
        # --embed-batch-size default (64) is small. Raising it for throughput
        # while on MPS/CUDA for the full 700k+ node corpus reintroduces the
        # batch x seq^2 unified-memory OOM PR #7 fixed elsewhere -- that fix
        # does not reach this code path.
        if opts.embed_device == "auto":
            if _mps_available():
                effective_device = "mps"
            elif _cuda_available():
                effective_device = "cuda"
            else:
                effective_device = "cpu"
        else:
            effective_device = opts.embed_device

        if effective_device == "cpu" or opts.update:
            # CPU (or any --update) → PARALLEL embedding via doc_kg's multi-process
            # CorpusEmbedder (`.json` cache). This is the only path that supports
            # incremental `only_missing` embedding. Pin every worker via
            # KG_EMBED_DEVICE — even when the resolved device is MPS (--update):
            # without the pin each worker auto-selects MPS and N workers stack
            # N GPU allocations → OOM.
            os.environ["KG_EMBED_DEVICE"] = "cpu"
            # .jsonl streams vectors to disk as shards complete (CorpusEmbedder.
            # embed_to_cache) instead of holding the whole corpus in RAM — peak memory
            # is bounded by shard size, which is what kept the 689k-node build off swap.
            cache_path = out_dir / "embeddings.jsonl"
            mode = "incremental — embed only new/changed nodes" if opts.update else "full"
            print(f"  [parallel] CPU multiprocessing ({mode})")
            kg_all.build_embeddings(
                out=cache_path,
                n_workers=opts.n_workers,  # each worker loads its own model copy (~1.2 GB)
                batch_size=opts.embed_batch_size,
                only_missing=opts.update,
                quiet=opts.quiet,
            )
        else:
            # MPS/CUDA → single-process streaming to a `.jsonl` cache. The GPU
            # allocator can't be shared across spawn workers without OOM, so
            # parallelism is off here by design; streaming keeps GPU + host
            # memory flat across the whole corpus (700k+ nodes).
            cache_path = out_dir / "embeddings.jsonl"
            print(f"  [stream] single-process on {effective_device}")
            kg_all.build_embeddings(
                out=cache_path,
                n_workers=None,
                batch_size=opts.embed_batch_size,
                quiet=opts.quiet,
            )

        # ------------------------------------------------------------------
        # Phase 3: build LanceDB index + SIMILAR_TO edges.
        # ------------------------------------------------------------------
        # On --update we UPSERT into the existing vector index (wipe=False) and skip
        # SIMILAR_TO — the served handler is semantic-first and never traverses those
        # edges, so recomputing 800k+ of them every update is pure waste.
        index_wipe = opts.wipe and not opts.update
        discover_similar = opts.discover_similar and not opts.update
        print(
            f"[3/4] building LanceDB index{' + SIMILAR_TO edges' if discover_similar else ' (upsert)' if opts.update else ''} …"
        )
        stats = kg_all.build_index_from_cache(
            cache_path,
            wipe=index_wipe,
            discover_similar=discover_similar,
            similar_k=opts.similar_k,
            similar_max_degree=opts.similar_max_degree,
            quiet=opts.quiet,
        )

        # Rebuild the FTS5 lexical index over the *full* consolidated graph so
        # the handler's hybrid (dense + BM25) retrieval activates. build_graph()
        # rebuilds it per strategy group, but we do it once more here as an
        # explicit guard: it is the single artifact the lexical channel depends
        # on, and an absent nodes_fts silently degrades retrieval to dense-only.
        print("[3/4] building FTS5 lexical index (nodes_fts) over the full graph …")
        n_fts = kg_all.store.rebuild_fts(quiet=opts.quiet)
        print(f"  lexical index: {n_fts:,} chunks")

        # Incremental adds only; drop index vectors for nodes that left the graph
        # (removed/renamed books) so they can't return stale hits.
        if opts.update:
            print("[3/4] pruning orphan vectors (removed/renamed nodes) …")
            kg_all.prune_index(quiet=opts.quiet)

        kg_all.close()
        # The embedding cache (.json / .jsonl) is a build-only intermediate — it can
        # be several GB and must never ship in the bundle. Remove BOTH variants so a
        # stale cache from a prior or killed run can't bloat the bundle (and the image
        # COPY). .dockerignore guards the same at pack time as a belt-and-suspenders.
        for _cache in ("embeddings.json", "embeddings.jsonl"):
            (out_dir / _cache).unlink(missing_ok=True)

        # ------------------------------------------------------------------
        # Phase 4: build (if needed) + bundle DiaryKG indices.
        # ------------------------------------------------------------------
        print("[4/4] building + bundling DiaryKG indices …")
        if ensure_diaries_built(dry_run=opts.dry_run, quiet=opts.quiet) != 0:
            print("[x] diary build failed")
            return 1
        n_diaries = bundle_diaries(out_dir)
        if n_diaries:
            print(f"  copied {n_diaries} diary index(es) → bundles/{name}/diaries/")
        else:
            print("  (no .diarykg indices found under corpus/diaries/)")

        print("[+] writing catalog.json (author/title from reference.md) …")
        n_cat, n_auth = build_catalog(genres, out_dir)

    except Exception as exc:  # noqa: BLE001
        print(f"[x] build failed: {exc}")
        msg = str(exc)
        if "MPS backend out of memory" in msg:
            print("[hint] Apple MPS OOM during embedding pass.")
            print("[hint] Retry with CPU embeddings and a smaller embed batch:")
            print("       gutenkg build-corpus --embed-device cpu --embed-batch-size 16")
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
