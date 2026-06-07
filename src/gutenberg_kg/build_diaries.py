"""
build_diaries.py - Build .diarykg/ DocKG indices for diary corpora.

Each diary lives under corpus/diaries/<name>/ with pre-chunked entries in
.diary/ and the DocKG index written to .diarykg/.  This is a prerequisite for
bundle_diaries() in build_corpus.py - it copies the indices but does not build
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


def _strip_frontmatter(text: str) -> str:
    """Return diary chunk text with YAML frontmatter and [Topics:] tag removed.

    DiaryTransformer writes chunk files with a YAML header (---...---) and an
    optional [Topics: ...] tag.  DocKG stores the full file text verbatim, so
    chunk nodes in SQLite contain this header noise before the actual prose.

    Handles both closing-delimiter variants seen in the wild:
      format A  ---\\n\\n[Topics: ...]\\n\\nProse   (topics on own line)
      format B  --- [Topics: ...] Prose              (topics inline on closing ---)
    """
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    after = text[end + 4 :].lstrip()
    if after.startswith("[Topics:"):
        close = after.find("]")
        after = (
            after[close + 1 :].lstrip() if close != -1 else after[after.find("\n") + 1 :].lstrip()
        )
    return after


def _clean_chunk_texts(sqlite_path: Path) -> int:
    """Strip YAML frontmatter from chunk node texts in a diary graph.sqlite.

    :param sqlite_path: Path to the .diarykg/graph.sqlite file.
    :return: Number of chunk rows updated.
    """
    if not sqlite_path.exists():
        return 0
    updated = 0
    try:
        with sqlite3.connect(sqlite_path) as con:
            rows = con.execute(
                "SELECT id, text FROM nodes WHERE kind='chunk' AND text LIKE '---%'"
            ).fetchall()
            changes = [
                (_strip_frontmatter(text), node_id)
                for node_id, text in rows
                if _strip_frontmatter(text) != text
            ]
            if changes:
                con.executemany("UPDATE nodes SET text=? WHERE id=?", changes)
                con.commit()
            updated = len(changes)
    except Exception:  # noqa: BLE001
        pass
    return updated


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
) -> DiaryBuildResult:
    """Build (or rebuild) the .diarykg/ DiaryKG index for one diary.

    Creates a symlink ``.diarykg/corpus -> ../.diary`` so DiaryKG finds its
    pre-chunked corpus, then calls ``DiaryKG.rebuild_index()`` which runs Steps
    2 (DocKG build), 3 (_inject_topic_edges), and 4 (_enrich_metadata).

    :param diary_dir: Root directory of the diary (e.g. corpus/diaries/Pepys/).
    :param opts: Build option flags.
    :return: DiaryBuildResult with timing and graph stats.
    """
    import shutil

    name = diary_dir.name
    diary_chunks_dir = diary_dir / ".diary"
    diarykg_dir = diary_dir / ".diarykg"
    sqlite_path = diarykg_dir / "graph.sqlite"

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

    # Symlink .diarykg/corpus → ../.diary so DiaryKG finds its pre-chunked corpus.
    corpus_link = diarykg_dir / "corpus"
    if not corpus_link.exists():
        corpus_link.symlink_to(diary_chunks_dir.resolve())

    try:
        from diary_kg.kg import DiaryKG
    except ImportError as exc:
        return DiaryBuildResult(
            name=name,
            status="failed",
            elapsed=time.perf_counter() - t0,
            message=f"diary-kg not installed: {exc}",
        )

    try:
        kg = DiaryKG(root=diary_dir, model=DIARY_EMBED_MODEL)
        kg.rebuild_index()
        _clean_chunk_texts(sqlite_path)
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
    if opts.dry_run:
        print("  mode          : DRY RUN")
    print()

    results: list[DiaryBuildResult] = []
    t_total = time.perf_counter()

    for diary_dir in diary_dirs:
        name = diary_dir.name
        chunk_count = sum(1 for _ in (diary_dir / ".diary").glob("entry_*.md"))
        print(f"[{name}]  ({chunk_count:,} chunk files)")

        result = build_diary_index(diary_dir, opts)
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
