"""Integration tests for the diary chunking stage (gutenberg_kg.diary.chunk).

Stage ① (``.md`` → ``.diary_source.psv``) is deterministic and dependency-free,
so it is always exercised.  Stage ② (PSV → ``.diary/`` chunks) needs the optional
``diary_transformer`` package plus a spaCy model, so it is guarded and skipped
when those are unavailable (e.g. CI).
"""

from __future__ import annotations

import pytest

from gutenberg_kg.diary.chunk import ChunkDiariesOptions, chunk_diary

PEPYS_MD = (
    "JANUARY 1659-1660\n\n"
    "Jan. 1st (Lord's day). This morning I rose early and went to the office.\n\n"
    "2nd. Much business today, then home and to bed after a good supper.\n"
)


def _make_diary(tmp_path, fmt="pepys", text=PEPYS_MD):
    book = tmp_path / "Pepys"
    book.mkdir()
    (book / "pepys.md").write_text(text, encoding="utf-8")
    (book / ".diary_format").write_text(fmt, encoding="utf-8")
    return book


def test_chunk_diary_writes_psv_from_md(tmp_path):
    """Stage ①: parsing the .md always produces the dated PSV (no heavy deps)."""
    book = _make_diary(tmp_path)
    res = chunk_diary(book, ChunkDiariesOptions(force=True))

    psv = book / ".diary_source.psv"
    assert psv.exists()
    lines = psv.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("1660-01-01T00:00:00 | diary | prose | ")
    # entries is recorded even if stage ② can't run (transformer absent)
    assert res.entries == 2


def test_chunk_diary_produces_chunks_when_deps_present(tmp_path):
    """Stage ②: with diary_transformer + spaCy model, .diary/ chunks are written."""
    pytest.importorskip("diary_transformer")
    spacy = pytest.importorskip("spacy")
    try:
        spacy.load("en_core_web_sm")
    except Exception:  # noqa: BLE001
        pytest.skip("spaCy model en_core_web_sm not installed")

    book = _make_diary(tmp_path)
    res = chunk_diary(book, ChunkDiariesOptions(force=True))

    assert res.status == "chunked", res.message
    assert res.chunks > 0
    chunk_files = list((book / ".diary").glob("entry_*.md"))
    assert len(chunk_files) == res.chunks
