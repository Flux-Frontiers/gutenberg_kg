"""
build_diaries.py — Build .diarykg/ DocKG indices for diary corpora.

Each diary lives under corpus/diaries/<name>/ with pre-chunked entries in
.diary/ and the DocKG index written to .diarykg/.  This is a prerequisite for
bundle_diaries() in build_corpus.py — it copies the indices but does not build
them.

Chunk strategy and flags match docs/DIARY_INGEST_HANDOFF.md:
- chunk_strategy = sentence_group  (preserves temporal entry structure)
- discover_similar = False         (chronologically dense entries produce noise)
- model = BAAI/bge-small-en-v1.5   (must match EMBED_MODEL in the Docker image)
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from gutenberg_kg.build_corpus import fmt_duration

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPO_ROOT / "corpus"
DIARIES_ROOT = CORPUS_ROOT / "diaries"

DIARY_CHUNK_STRATEGY = "sentence_group"
DIARY_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DiaryBuildResult:
    """Outcome for one diary index build."""

    name: str
    status: str  # 'built' | 'skipped' | 'failed'
    elapsed: float = 0.0
    nodes: int = 0
    edges: int = 0
    message: str = ""


@dataclass
class BuildDiariesOptions:
    """Flags controlling a diary index build."""

    force: bool = False
    n_workers: int = 4
    dry_run: bool = False
    quiet: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sqlite_counts(sqlite_path: Path) -> tuple[int, int]:
    """Return (node_count, edge_count) from graph.sqlite, or (0, 0)."""
    if not sqlite_path.exists():
        return 0, 0
    try:
        with sqlite3.connect(sqlite_path) as con:
            nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return nodes, edges
    except Exception:  # noqa: BLE001
        return 0, 0


def list_diary_dirs(names: list[str] | None = None) -> list[Path]:
    """Return sorted diary root directories under corpus/diaries/.

    :param names: Optional list of diary directory names to filter to.
    :return: Matching (or all) diary directories, sorted alphabetically.
    """
    if not DIARIES_ROOT.exists():
        return []
    dirs = sorted(p for p in DIARIES_ROOT.iterdir() if p.is_dir() and not p.name.startswith("."))
    if names:
        name_set = set(names)
        dirs = [d for d in dirs if d.name in name_set]
    return dirs


# ---------------------------------------------------------------------------
# Core per-diary build
# ---------------------------------------------------------------------------


def build_diary_index(
    diary_dir: Path,
    opts: BuildDiariesOptions,
    embedder=None,
) -> DiaryBuildResult:
    """Build (or rebuild) the .diarykg/ DocKG index for one diary.

    :param diary_dir: Root directory of the diary (e.g. corpus/diaries/Pepys/).
    :param opts: Build option flags.
    :param embedder: Shared SentenceTransformerEmbedder instance (reused across diaries).
    :return: DiaryBuildResult with timing and graph stats.
    """
    import shutil

    name = diary_dir.name
    diary_chunks_dir = diary_dir / ".diary"
    diarykg_dir = diary_dir / ".diarykg"
    sqlite_path = diarykg_dir / "graph.sqlite"
    lancedb_path = diarykg_dir / "lancedb"

    t0 = time.perf_counter()

    if not diary_chunks_dir.exists() or not any(diary_chunks_dir.iterdir()):
        return DiaryBuildResult(
            name=name,
            status="failed",
            elapsed=time.perf_counter() - t0,
            message=f".diary/ not found or empty: {diary_chunks_dir}",
        )

    already_built = sqlite_path.exists()
    if already_built and not opts.force:
        nodes, edges = _sqlite_counts(sqlite_path)
        return DiaryBuildResult(
            name=name,
            status="skipped",
            elapsed=time.perf_counter() - t0,
            nodes=nodes,
            edges=edges,
            message="already built (use --force to rebuild)",
        )

    if opts.dry_run:
        chunk_count = sum(1 for _ in diary_chunks_dir.glob("entry_*.md"))
        return DiaryBuildResult(
            name=name,
            status="skipped",
            elapsed=time.perf_counter() - t0,
            message=f"[dry-run] would build from {chunk_count} chunk files in {diary_chunks_dir}",
        )

    if already_built and opts.force:
        shutil.rmtree(diarykg_dir)

    diarykg_dir.mkdir(parents=True, exist_ok=True)

    try:
        from doc_kg.index import SentenceTransformerEmbedder
        from doc_kg.kg import DocKG
    except ImportError as exc:
        return DiaryBuildResult(
            name=name,
            status="failed",
            elapsed=time.perf_counter() - t0,
            message=f"doc_kg not installed: {exc}",
        )

    try:
        if embedder is None:
            embedder = SentenceTransformerEmbedder(DIARY_EMBED_MODEL)

        kg = DocKG(
            corpus_root=diary_chunks_dir,
            db_path=sqlite_path,
            lancedb_dir=lancedb_path,
            embedder=embedder,
            chunk_strategy=DIARY_CHUNK_STRATEGY,
        )
        kg.build_graph(wipe=True, quiet=opts.quiet)

        cache_path = diarykg_dir / "embeddings.json"
        kg.build_embeddings(out=cache_path, n_workers=opts.n_workers, quiet=opts.quiet)
        kg.build_index_from_cache(cache_path, wipe=True, discover_similar=False, quiet=opts.quiet)
        kg.close()
        cache_path.unlink(missing_ok=True)

    except Exception as exc:  # noqa: BLE001
        return DiaryBuildResult(
            name=name,
            status="failed",
            elapsed=time.perf_counter() - t0,
            message=str(exc),
        )

    nodes, edges = _sqlite_counts(sqlite_path)
    return DiaryBuildResult(
        name=name,
        status="built",
        elapsed=time.perf_counter() - t0,
        nodes=nodes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_build_diaries(
    diary_names: list[str],
    opts: BuildDiariesOptions,
) -> int:
    """Build .diarykg/ indices for all (or selected) diaries.

    :param diary_names: Diary directory names to process (empty = all).
    :param opts: Build option flags.
    :return: 0 on full success, 1 if any diary failed.
    """
    diary_dirs = list_diary_dirs(diary_names if diary_names else None)

    if not diary_dirs:
        print("[!] No diary directories found under corpus/diaries/")
        if diary_names:
            print(f"    Requested: {diary_names}")
        return 1

    print("=== gutenkg build-diaries ===")
    print(f"  diaries       : {len(diary_dirs)}")
    print(f"  strategy      : {DIARY_CHUNK_STRATEGY}")
    print(f"  embed model   : {DIARY_EMBED_MODEL}")
    print("  SIMILAR_TO    : disabled")
    print(f"  force rebuild : {opts.force}")
    print(f"  embed workers : {opts.n_workers}")
    if opts.dry_run:
        print("  mode          : DRY RUN")
    print()

    results: list[DiaryBuildResult] = []
    t_total = time.perf_counter()

    # Share one embedder across all diary builds to avoid reloading the model.
    shared_embedder = None
    if not opts.dry_run:
        try:
            from doc_kg.index import SentenceTransformerEmbedder

            shared_embedder = SentenceTransformerEmbedder(DIARY_EMBED_MODEL)
            print(f"  [embedder] {shared_embedder!r}\n")
        except ImportError as exc:
            print(f"[x] doc_kg not installed: {exc}")
            return 1

    for diary_dir in diary_dirs:
        name = diary_dir.name
        chunk_count = sum(1 for _ in (diary_dir / ".diary").glob("entry_*.md"))
        print(f"[{name}]  ({chunk_count:,} chunk files)")

        result = build_diary_index(diary_dir, opts, embedder=shared_embedder)
        results.append(result)

        icon = {"built": "[+]", "skipped": "[=]", "failed": "[x]"}.get(result.status, "[ ]")
        detail = (
            f"nodes={result.nodes:,}  edges={result.edges:,}  {fmt_duration(result.elapsed)}"
            if result.status == "built"
            else result.message
        )
        print(f"  {icon} {result.status}  {detail}")
        print()

    elapsed = time.perf_counter() - t_total
    built = sum(1 for r in results if r.status == "built")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    total_nodes = sum(r.nodes for r in results)
    total_edges = sum(r.edges for r in results)

    print("=== build-diaries complete ===")
    print(f"  built         : {built}")
    print(f"  skipped       : {skipped}")
    print(f"  failed        : {failed}")
    if built or skipped:
        print(f"  total nodes   : {total_nodes:,}")
        print(f"  total edges   : {total_edges:,}")
    print(f"  elapsed       : {fmt_duration(elapsed)}")

    if failed:
        print()
        print("  Failed diaries:")
        for r in results:
            if r.status == "failed":
                print(f"    [x] {r.name}: {r.message}")
    print()

    return 1 if failed else 0
