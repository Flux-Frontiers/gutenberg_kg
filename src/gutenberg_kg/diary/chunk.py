"""chunk.py — Stages ①② of the diary pipeline: ``.md`` → PSV → ``.diary/`` chunks.

Reconstructs the temporally-grounded ``.diary/`` chunk corpus that
``gutenkg build-diaries`` indexes into ``.diarykg/``.  Both ``.diary/`` and
``.diary_source.psv`` are git-ignored, so this step lets a clean clone rebuild
them from the committed ``<book>.md``.

Pipeline
--------
① ``.md`` → ``.diary_source.psv`` — the Gutenberg-specific date parsing in
  :mod:`gutenberg_kg.diary.parser` (format selected per book via ``.diary_format``).
② ``.diary_source.psv`` → ``.diary/`` — native ``diary_transformer`` chunking.

Stage ③ (``.diary/`` → ``.diarykg/``) is handled separately by
``gutenkg build-diaries`` (see :mod:`gutenberg_kg.build_diaries`).

Chunking parameters are pinned to the values that produced the shipped
``.diarykg/`` indices; changing them would alter chunk boundaries and retrieval
behaviour.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from gutenberg_kg.build_diaries import fmt_duration, list_diary_dirs
from gutenberg_kg.diary.parser import get_parser, write_psv

DIARY_DIR_NAME = ".diary"
PSV_FILE_NAME = ".diary_source.psv"
FORMAT_FILE_NAME = ".diary_format"
DEFAULT_FORMAT = "pepys"

# Chunking config — must match what produced the shipped .diarykg/ indices.
CHUNKING_STRATEGY = "sentence_group"
SENTENCES_PER_CHUNK = 3
MAX_CHUNK_LENGTH = 512


@dataclass
class ChunkResult:
    """Outcome for one diary chunking run."""

    name: str
    status: str  # 'chunked' | 'skipped' | 'failed'
    elapsed: float = 0.0
    entries: int = 0
    chunks: int = 0
    fmt: str = ""
    message: str = ""


@dataclass
class ChunkDiariesOptions:
    """Flags controlling a diary chunking run."""

    force: bool = False
    dry_run: bool = False


def _read_format(diary_dir: Path) -> str:
    """Return the parser format for *diary_dir* from ``.diary_format``.

    :param diary_dir: Root directory of the diary.
    :return: Format name (``pepys`` | ``evelyn`` | ``boswell``); ``pepys`` default.
    """
    fmt_file = diary_dir / FORMAT_FILE_NAME
    if fmt_file.exists():
        return fmt_file.read_text(encoding="utf-8").strip() or DEFAULT_FORMAT
    return DEFAULT_FORMAT


def _find_book_md(diary_dir: Path) -> Path | None:
    """Return the book's full-text ``.md`` (not ``reference.md``), or ``None``."""
    candidates = [p for p in diary_dir.glob("*.md") if p.name != "reference.md"]
    return candidates[0] if candidates else None


def chunk_diary(diary_dir: Path, opts: ChunkDiariesOptions) -> ChunkResult:
    """Parse + chunk one diary into ``.diary/`` (and ``.diary_source.psv``).

    :param diary_dir: Root directory of the diary (e.g. corpus/diaries/Pepys/).
    :param opts: Chunking option flags.
    :return: :class:`ChunkResult` with timing and entry/chunk counts.
    """
    name = diary_dir.name
    t0 = time.perf_counter()

    md_file = _find_book_md(diary_dir)
    if md_file is None:
        return ChunkResult(
            name=name,
            status="failed",
            elapsed=time.perf_counter() - t0,
            message=f"no book .md found in {diary_dir}",
        )

    diary_chunks_dir = diary_dir / DIARY_DIR_NAME
    already = diary_chunks_dir.exists() and any(diary_chunks_dir.iterdir())
    if already and not opts.force:
        return ChunkResult(
            name=name,
            status="skipped",
            elapsed=time.perf_counter() - t0,
            message="already chunked (use --force to rebuild)",
        )

    fmt = _read_format(diary_dir)

    if opts.dry_run:
        return ChunkResult(
            name=name,
            status="skipped",
            fmt=fmt,
            elapsed=time.perf_counter() - t0,
            message=f"[dry-run] would parse {md_file.name} (format={fmt}) → .diary/",
        )

    # ── ① parse → PSV ──────────────────────────────────────────────────────
    psv_path = diary_dir / PSV_FILE_NAME
    try:
        n_entries = write_psv(get_parser(fmt).parse(md_file), psv_path)
    except Exception as exc:  # noqa: BLE001
        return ChunkResult(
            name=name,
            status="failed",
            fmt=fmt,
            elapsed=time.perf_counter() - t0,
            message=f"parse failed: {exc}",
        )
    # The PSV was just regenerated from .md, so any DiaryTransformer chunk cache
    # (keyed by filename, not content) is stale — drop it to force a fresh chunk.
    for ext in ("_chunks.pkl", "_chunks.json"):
        (diary_dir / f"{psv_path.stem}{ext}").unlink(missing_ok=True)
    if n_entries == 0:
        return ChunkResult(
            name=name,
            status="failed",
            fmt=fmt,
            elapsed=time.perf_counter() - t0,
            message=f"no dated entries parsed from {md_file.name} (format={fmt})",
        )

    # ── ② PSV → .diary/ chunks via native diary_transformer ────────────────
    try:
        from diary_transformer.transformer import DiaryTransformer
    except ImportError as exc:
        return ChunkResult(
            name=name,
            status="failed",
            fmt=fmt,
            elapsed=time.perf_counter() - t0,
            entries=n_entries,
            message=f"diary-transformer not installed: {exc}",
        )

    if already and opts.force:
        import shutil

        shutil.rmtree(diary_chunks_dir)
    diary_chunks_dir.mkdir(parents=True, exist_ok=True)

    try:
        dt = DiaryTransformer(
            max_chunk_length=MAX_CHUNK_LENGTH,
            num_workers=1,
            chunking_strategy=CHUNKING_STRATEGY,
            sentences_per_chunk=SENTENCES_PER_CHUNK,
        )
        n_chunks = dt.ingest_to_corpus(
            input_path=str(psv_path),
            corpus_dir=str(diary_chunks_dir),
            batch_size=0,  # all entries — no diversity sub-sampling
            max_chunks_per_entry=0,  # unlimited — long entries (Pepys) keep all chunks
            source_file=md_file.name,
        )
    except SystemExit as exc:
        # diary_transformer calls sys.exit(1) when the spaCy model is missing.
        return ChunkResult(
            name=name,
            status="failed",
            fmt=fmt,
            elapsed=time.perf_counter() - t0,
            entries=n_entries,
            message=(
                "chunking failed: diary_transformer aborted "
                f"(exit {exc.code}) — is the spaCy model installed? "
                "run: python -m spacy download en_core_web_sm"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return ChunkResult(
            name=name,
            status="failed",
            fmt=fmt,
            elapsed=time.perf_counter() - t0,
            entries=n_entries,
            message=f"chunking failed: {exc}",
        )

    if n_chunks == 0:
        return ChunkResult(
            name=name,
            status="failed",
            fmt=fmt,
            elapsed=time.perf_counter() - t0,
            entries=n_entries,
            message="diary_transformer produced no chunk files",
        )

    return ChunkResult(
        name=name,
        status="chunked",
        elapsed=time.perf_counter() - t0,
        entries=n_entries,
        chunks=n_chunks,
        fmt=fmt,
    )


def run_chunk_diaries(diary_names: list[str], opts: ChunkDiariesOptions) -> int:
    """Chunk all (or selected) diaries from ``.md`` into ``.diary/``.

    :param diary_names: Diary directory names to process (empty = all).
    :param opts: Chunking option flags.
    :return: 0 on full success, 1 if any diary failed.
    """
    diary_dirs = list_diary_dirs(diary_names if diary_names else None)
    if not diary_dirs:
        print("[!] No diary directories found under corpus/diaries/")
        if diary_names:
            print(f"    Requested: {diary_names}")
        return 1

    print("=== gutenkg chunk-diaries ===")
    print(f"  diaries       : {len(diary_dirs)}")
    print(f"  strategy      : {CHUNKING_STRATEGY} (sentences_per_chunk={SENTENCES_PER_CHUNK})")
    print(f"  force rebuild : {opts.force}")
    if opts.dry_run:
        print("  mode          : DRY RUN")
    print()

    results: list[ChunkResult] = []
    t_total = time.perf_counter()
    for diary_dir in diary_dirs:
        print(f"[{diary_dir.name}]")
        result = chunk_diary(diary_dir, opts)
        results.append(result)
        icon = {"chunked": "[+]", "skipped": "[=]", "failed": "[x]"}.get(result.status, "[ ]")
        if result.status == "chunked":
            detail = (
                f"format={result.fmt}  entries={result.entries:,}  "
                f"chunks={result.chunks:,}  {fmt_duration(result.elapsed)}"
            )
        else:
            detail = result.message
        print(f"  {icon} {result.status}  {detail}")
        print()

    elapsed = time.perf_counter() - t_total
    chunked = sum(1 for r in results if r.status == "chunked")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")

    print("=== chunk-diaries complete ===")
    print(f"  chunked       : {chunked}")
    print(f"  skipped       : {skipped}")
    print(f"  failed        : {failed}")
    print(f"  elapsed       : {fmt_duration(elapsed)}")
    if failed:
        print()
        print("  Failed diaries:")
        for r in results:
            if r.status == "failed":
                print(f"    [x] {r.name}: {r.message}")
    print()
    return 1 if failed else 0
