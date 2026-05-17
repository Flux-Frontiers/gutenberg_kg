"""pipeline.py — Diary-aware DocKG pipeline for Gutenberg diary texts.

Replaces the standard three-step ``build_dockg()`` for genres marked with
``"pipeline": "diary"`` in ``corpus/genres.json``.

Pipeline
--------
1. **Parse** — :func:`parser.parse` extracts dated entries from the raw
   Gutenberg markdown and :func:`parser.write_psv` writes a pipe-delimited
   source file compatible with ``DiaryTransformer``.
2. **Transform** — ``DiaryTransformer.ingest_to_corpus`` chunks, classifies,
   and writes per-chunk ``.md`` files with temporal YAML frontmatter into
   a hidden ``.diary/`` corpus directory inside the book directory.
3. **Index** — ``DocKG`` builds the SQLite graph + LanceDB vector index with
   ``.diary/`` as the corpus root, placing the index at ``.diarykg/`` (book
   root), reusing the shared embedder from the ingest loop.

Layout::

    <book_dir>/
    ├── <book>.md            ← raw Gutenberg markdown
    ├── .diary_source.psv    ← parse artifact (git-ignored)
    ├── .diary/              ← chunk corpus (git-ignored)
    │   ├── chunk-0001.md
    │   └── …
    └── .diarykg/            ← KG index (same level as .dockg for standard books)
        ├── graph.sqlite
        └── lancedb/
"""

from __future__ import annotations

from pathlib import Path

DIARY_DIR_NAME = ".diary"
DIARY_KG_DIR_NAME = ".diarykg"
PSV_FILE_NAME = ".diary_source.psv"
FORMAT_FILE_NAME = ".diary_format"


def _read_format(book_dir: Path) -> str:
    """Read the diary format from ``.diary_format`` in book_dir (default: pepys)."""
    fmt_file = book_dir / FORMAT_FILE_NAME
    if fmt_file.exists():
        return fmt_file.read_text(encoding="utf-8").strip()
    return "pepys"


def run_diary_pipeline(
    book_dir: Path,
    dry_run: bool = False,
    embedder=None,
) -> bool:
    """Parse a Gutenberg diary markdown and build a temporally-grounded DocKG.

    :param book_dir: Root directory of the downloaded book (contains the
        ``.md`` and ``reference.md`` files).
    :param dry_run: If *True*, print actions without executing them.
    :param embedder: Shared ``SentenceTransformerEmbedder`` instance; ``None``
        causes DocKG to create its own (slower for multi-book runs).
    :return: ``True`` on success, ``False`` on any error.
    """
    if dry_run:
        print(f"    [dry] diary pipeline: {book_dir.name}")
        return True

    try:
        return _run(book_dir, embedder)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"    [x] diary pipeline failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


def _run(book_dir: Path, embedder) -> bool:
    from diary_transformer.transformer import (  # pylint: disable=import-outside-toplevel
        DiaryTransformer,
    )
    from doc_kg.kg import DocKG  # pylint: disable=import-outside-toplevel

    from .parser import get_parser, write_psv  # pylint: disable=import-outside-toplevel

    # ── 1. Find the main diary markdown ────────────────────────────────────
    md_files = [f for f in book_dir.iterdir() if f.suffix == ".md" and f.name != "reference.md"]
    if not md_files:
        raise FileNotFoundError(f"No diary markdown found in {book_dir}")
    md_file = md_files[0]

    # ── 2. Parse → PSV ─────────────────────────────────────────────────────
    psv_path = book_dir / PSV_FILE_NAME
    print(f"    [diary] parsing {md_file.name}...")
    fmt = _read_format(book_dir)
    count = write_psv(get_parser(fmt).parse(md_file), psv_path)
    if count == 0:
        raise ValueError(f"No dated entries parsed from {md_file}")
    print(f"    [diary] {count:,} entries → {psv_path.name}")

    # ── 3. DiaryTransformer → per-chunk .md files in .diary/ ───────────────
    diary_dir = book_dir / DIARY_DIR_NAME
    diary_dir.mkdir(exist_ok=True)

    # Each chunk file gets a YAML frontmatter timestamp (from the source entry)
    # so DocKG can index them with full temporal grounding.
    print("    [diary] transforming entries (chunk + classify)...")
    dt = DiaryTransformer(
        chunking_strategy="sentence_group",
        sentences_per_chunk=3,
        num_workers=1,
    )
    written = dt.ingest_to_corpus(
        input_path=str(psv_path),
        corpus_dir=str(diary_dir),
        batch_size=0,  # all entries — no diversity sub-sampling
        max_chunks_per_entry=0,  # unlimited — Pepys has very long entries
        source_file=md_file.name,
    )
    print(f"    [diary] {written:,} chunk files written to .diary/")

    if written == 0:
        raise ValueError("DiaryTransformer produced no chunk files")

    # ── 4. DocKG: corpus=.diary/, index at .diarykg/ (book root) ──────────
    # Index lives alongside .dockg/ for standard books — single-level hidden
    # dir, auto-discovered by kgrag scan without special-casing.
    diarykg_dir = book_dir / DIARY_KG_DIR_NAME
    diarykg_dir.mkdir(exist_ok=True)
    print("    [diary] building DocKG (.diary/ → .diarykg/)...")
    kg = DocKG(
        diary_dir,
        db_path=str(diarykg_dir / "graph.sqlite"),
        lancedb_dir=str(diarykg_dir / "lancedb"),
        embedder=embedder,
    )
    kg.build_graph(wipe=True)
    cache_path = diarykg_dir / "embeddings.json"
    kg.build_embeddings(out=cache_path, n_workers=4)
    kg.build_index_from_cache(cache_path, wipe=True)
    kg.close()
    cache_path.unlink(missing_ok=True)

    return True
