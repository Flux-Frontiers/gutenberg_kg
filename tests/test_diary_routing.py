"""Tests for diary routing in the ingest pipeline.

Verifies that the ``diaries`` genre is diverted to the DiaryKG pipeline rather
than the standard DocKG path, and that diary registration points at ``.diarykg/``
(not ``.dockg/``).  Skipped entirely when the optional ``kg_rag`` extra is absent.
"""

from __future__ import annotations

import pytest

pytest.importorskip("kg_rag")  # diary routing/registration needs the kgdeps extra

from gutenberg_kg import ingest as ig  # noqa: E402


def test_run_ingest_routes_diaries_to_diary_pipeline(monkeypatch):
    """run_ingest with only 'diaries' delegates to ingest_diaries and short-circuits."""
    calls = {}

    def fake_ingest_diaries(registry_path, opts):
        calls["registry_path"] = registry_path
        calls["opts"] = opts
        return 0, None

    # If routing failed and it fell through to the prose path, this would raise.
    def boom(*a, **k):  # pragma: no cover - only hit on routing regression
        raise AssertionError("prose build path should not run for diaries-only ingest")

    monkeypatch.setattr(ig, "ingest_diaries", fake_ingest_diaries)
    monkeypatch.setattr(ig, "process_book", boom)

    rc = ig.run_ingest(["diaries"], ig.IngestOptions(dry_run=True))
    assert rc == 0
    assert calls, "ingest_diaries was not called for the diaries genre"


def test_register_diary_book_points_to_diarykg(tmp_path):
    """register_diary_book registers the .diarykg/ index, never .dockg/."""
    diary_dir = tmp_path / "Some Diary"
    (diary_dir / ".diarykg" / "lancedb").mkdir(parents=True)
    (diary_dir / ".diarykg" / "graph.sqlite").write_text("", encoding="utf-8")

    class _StubReg:
        def __init__(self):
            self.registered = None

        def register(self, entry):
            self.registered = entry

    reg = _StubReg()
    entry = ig.register_diary_book(reg, "gutenberg-diaries-some-diary-doc", diary_dir)

    assert entry is reg.registered
    assert entry.sqlite_path.parent == diary_dir / ".diarykg"
    assert entry.sqlite_path.name == "graph.sqlite"
    assert entry.lancedb_path.parent == diary_dir / ".diarykg"
    assert entry.lancedb_path.name == "lancedb"
    assert ".dockg" not in str(entry.sqlite_path)
