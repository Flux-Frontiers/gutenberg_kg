"""Unit tests for gutenberg_kg.ingest — pure helpers and data classes.

Requires kg_rag (not available in CI) — skipped automatically when absent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("kg_rag", reason="kg_rag not installed — integration test skipped")

from gutenberg_kg.ingest import (
    BookResult,
    GenreSummary,
    IngestOptions,
    build_dockg,
    fmt_duration,
    is_sqlite_valid,
    slugify,
)

# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


def test_slugify_basic():
    assert slugify("Moby Dick") == "moby-dick"


def test_slugify_lowercases():
    assert slugify("HAMLET") == "hamlet"


def test_slugify_replaces_non_alphanum_with_hyphens():
    assert slugify("Pride & Prejudice") == "pride-prejudice"


def test_slugify_collapses_multiple_hyphens():
    assert slugify("War  and  Peace") == "war-and-peace"


def test_slugify_strips_leading_trailing_hyphens():
    result = slugify("My Title")
    assert not result.startswith("-")
    assert not result.endswith("-")


def test_slugify_numbers_preserved():
    assert slugify("Book 3") == "book-3"


def test_slugify_empty():
    assert slugify("") == ""


# ---------------------------------------------------------------------------
# fmt_duration
# ---------------------------------------------------------------------------


def test_fmt_duration_seconds_only():
    assert fmt_duration(45.0) == "45.0s"


def test_fmt_duration_under_minute():
    assert fmt_duration(0.5) == "0.5s"


def test_fmt_duration_exact_minute():
    assert fmt_duration(60.0) == "1m 00s"


def test_fmt_duration_minutes_and_seconds():
    assert fmt_duration(90.0) == "1m 30s"


def test_fmt_duration_exact_hour():
    assert fmt_duration(3600.0) == "1h 00m 00s"


def test_fmt_duration_hours_minutes_seconds():
    assert fmt_duration(3723.0) == "1h 02m 03s"


def test_fmt_duration_long_job():
    assert fmt_duration(7265.0) == "2h 01m 05s"


# ---------------------------------------------------------------------------
# IngestOptions defaults
# ---------------------------------------------------------------------------


def test_ingest_options_defaults():
    opts = IngestOptions()
    assert opts.force_build is False
    assert opts.force_register is False
    assert opts.dry_run is False
    assert opts.push is False


def test_ingest_options_can_be_set():
    opts = IngestOptions(force_build=True, dry_run=True)
    assert opts.force_build is True
    assert opts.dry_run is True
    assert opts.force_register is False


# ---------------------------------------------------------------------------
# BookResult
# ---------------------------------------------------------------------------


def test_book_result_fields():
    r = BookResult(
        name="Hamlet", genre="shakespeare", status="built", elapsed=1.5, nodes=100, edges=200
    )
    assert r.name == "Hamlet"
    assert r.genre == "shakespeare"
    assert r.status == "built"
    assert r.elapsed == 1.5
    assert r.nodes == 100
    assert r.edges == 200


def test_book_result_defaults():
    r = BookResult(name="Hamlet", genre="shakespeare", status="skipped")
    assert r.elapsed == 0.0
    assert r.nodes == 0
    assert r.edges == 0


# ---------------------------------------------------------------------------
# GenreSummary computed properties
# ---------------------------------------------------------------------------


def _make_summary(statuses: list[str], **kwargs) -> GenreSummary:
    results = [
        BookResult(name=f"Book{i}", genre="test", status=s, **kwargs)
        for i, s in enumerate(statuses)
    ]
    gs = GenreSummary(genre="test")
    gs.results = results
    return gs


def test_genre_summary_built_count():
    gs = _make_summary(["built", "built", "skipped", "failed"])
    assert gs.built == 2


def test_genre_summary_skipped_count():
    gs = _make_summary(["built", "skipped", "skipped"])
    assert gs.skipped == 2


def test_genre_summary_failed_count():
    gs = _make_summary(["built", "failed"])
    assert gs.failed == 1


def test_genre_summary_total():
    gs = _make_summary(["built", "skipped", "failed"])
    assert gs.total == 3


def test_genre_summary_elapsed_sum():
    gs = GenreSummary(genre="test")
    gs.results = [
        BookResult(name="A", genre="test", status="built", elapsed=1.5),
        BookResult(name="B", genre="test", status="built", elapsed=2.5),
    ]
    assert gs.elapsed == pytest.approx(4.0)


def test_genre_summary_nodes_sum():
    gs = GenreSummary(genre="test")
    gs.results = [
        BookResult(name="A", genre="test", status="built", nodes=100),
        BookResult(name="B", genre="test", status="built", nodes=200),
    ]
    assert gs.nodes == 300


def test_genre_summary_edges_sum():
    gs = GenreSummary(genre="test")
    gs.results = [
        BookResult(name="A", genre="test", status="built", edges=50),
        BookResult(name="B", genre="test", status="built", edges=75),
    ]
    assert gs.edges == 125


def test_genre_summary_empty():
    gs = GenreSummary(genre="test")
    assert gs.built == 0
    assert gs.skipped == 0
    assert gs.failed == 0
    assert gs.total == 0
    assert gs.elapsed == 0.0
    assert gs.nodes == 0
    assert gs.edges == 0


# ---------------------------------------------------------------------------
# build_dockg
# ---------------------------------------------------------------------------


def test_build_dockg_dry_run_returns_true(tmp_path: Path):
    assert build_dockg(tmp_path, dry_run=True) is True


def test_build_dockg_dry_run_ignores_embedder(tmp_path: Path):
    # Embedder should be irrelevant when dry_run=True — no DocKG instantiation.
    assert build_dockg(tmp_path, dry_run=True, embedder=object()) is True


def test_build_dockg_exception_returns_false(tmp_path: Path, monkeypatch):
    import sys
    import types

    fake_mod = types.ModuleType("doc_kg.kg")

    class _FailDocKG:
        def __init__(self, *a, **kw):
            raise RuntimeError("simulated build failure")

    fake_mod.DocKG = _FailDocKG
    monkeypatch.setitem(sys.modules, "doc_kg.kg", fake_mod)
    assert build_dockg(tmp_path, dry_run=False) is False


def test_build_dockg_passes_embedder_to_dockg(tmp_path: Path, monkeypatch):
    import sys
    import types

    received: dict = {}
    fake_mod = types.ModuleType("doc_kg.kg")

    class _FakeDocKG:
        def __init__(self, path, embedder=None):
            received["embedder"] = embedder

        def build(self, wipe=False):
            pass

        def close(self):
            pass

    fake_mod.DocKG = _FakeDocKG
    monkeypatch.setitem(sys.modules, "doc_kg.kg", fake_mod)

    sentinel = object()
    assert build_dockg(tmp_path, dry_run=False, embedder=sentinel) is True
    assert received["embedder"] is sentinel


def test_build_dockg_none_embedder_accepted(tmp_path: Path, monkeypatch):
    import sys
    import types

    received: dict = {}
    fake_mod = types.ModuleType("doc_kg.kg")

    class _FakeDocKG:
        def __init__(self, path, embedder=None):
            received["embedder"] = embedder

        def build(self, wipe=False):
            pass

        def close(self):
            pass

    fake_mod.DocKG = _FakeDocKG
    monkeypatch.setitem(sys.modules, "doc_kg.kg", fake_mod)

    assert build_dockg(tmp_path, dry_run=False, embedder=None) is True
    assert received["embedder"] is None


# ---------------------------------------------------------------------------
# is_sqlite_valid
# ---------------------------------------------------------------------------


def test_is_sqlite_valid_nonexistent(tmp_path: Path):
    assert is_sqlite_valid(tmp_path / "missing.sqlite") is False


def test_is_sqlite_valid_too_small(tmp_path: Path):
    tiny = tmp_path / "tiny.sqlite"
    tiny.write_bytes(b"x" * 50)
    assert is_sqlite_valid(tiny) is False


def test_is_sqlite_valid_valid_db(tmp_path: Path):
    db_path = tmp_path / "graph.sqlite"
    with sqlite3.connect(db_path) as con:
        con.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY)")
        con.execute("INSERT INTO nodes VALUES (1)")
    assert is_sqlite_valid(db_path) is True


def test_is_sqlite_valid_missing_nodes_table(tmp_path: Path):
    db_path = tmp_path / "graph.sqlite"
    with sqlite3.connect(db_path) as con:
        con.execute("CREATE TABLE other (id INTEGER PRIMARY KEY)")
    assert is_sqlite_valid(db_path) is False
