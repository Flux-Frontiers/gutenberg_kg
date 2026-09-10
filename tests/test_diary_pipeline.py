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


def _install_fake_transformer(monkeypatch, behavior):
    """Inject a fake diary_transformer.transformer.DiaryTransformer.

    ``behavior`` is called in DiaryTransformer.__init__ to simulate the desired
    outcome (e.g. raise SystemExit for a missing spaCy model).
    """
    import sys
    import types

    mod = types.ModuleType("diary_transformer.transformer")

    class FakeDiaryTransformer:
        def __init__(self, **_kwargs):
            behavior()

        def ingest_to_corpus(self, **_kwargs):  # pragma: no cover - never reached
            return 0

    mod.DiaryTransformer = FakeDiaryTransformer
    monkeypatch.setitem(sys.modules, "diary_transformer", types.ModuleType("diary_transformer"))
    monkeypatch.setitem(sys.modules, "diary_transformer.transformer", mod)


def test_chunk_diary_writes_psv_before_stage_two(tmp_path, monkeypatch):
    """Stage ①: the dated PSV is written even if stage ② can't run (no heavy deps)."""

    def boom():
        raise RuntimeError("transformer unavailable")

    _install_fake_transformer(monkeypatch, boom)
    book = _make_diary(tmp_path)
    res = chunk_diary(book, ChunkDiariesOptions(force=True))

    psv = book / ".diary_source.psv"
    assert psv.exists()
    lines = psv.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("1660-01-01T00:00:00 | diary | prose | ")
    assert res.entries == 2  # recorded even though chunking failed


def test_chunk_diary_handles_missing_spacy_model_gracefully(tmp_path, monkeypatch):
    """diary_transformer's hard sys.exit(1) (missing spaCy model) is caught, not propagated."""

    def sys_exit():
        raise SystemExit(1)

    _install_fake_transformer(monkeypatch, sys_exit)
    book = _make_diary(tmp_path)
    res = chunk_diary(book, ChunkDiariesOptions(force=True))  # must not raise SystemExit

    assert res.status == "failed"
    assert "spacy" in res.message.lower()
    assert (book / ".diary_source.psv").exists()


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


# ---------------------------------------------------------------------------
# build_diary_index resume gate
# ---------------------------------------------------------------------------


def _make_diary_store(diary_dir, *, with_vectors: bool, rows: int = 3):
    """Create a diary dir with a chunked .diary/ and a .diarykg/ store."""
    import sqlite3

    chunks = diary_dir / ".diary"
    chunks.mkdir(parents=True, exist_ok=True)
    (chunks / "entry_0001.md").write_text("an entry", encoding="utf-8")

    store = diary_dir / ".diarykg"
    store.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store / "graph.sqlite") as con:
        con.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE edges (src TEXT)")
        con.execute("INSERT INTO nodes VALUES (1)")
    if with_vectors:
        with sqlite3.connect(store / "vectors.sqlite") as con:
            con.execute("CREATE TABLE vec_nodes (rowid INTEGER PRIMARY KEY)")
            con.execute("CREATE TABLE vec_nodes_rowids (rowid INTEGER PRIMARY KEY)")
            for i in range(rows):
                con.execute("INSERT INTO vec_nodes_rowids VALUES (?)", (i,))
    return store


def test_build_diary_index_skips_complete_store(tmp_path):
    """A complete .diarykg is left alone without --force."""
    from gutenberg_kg.build_diaries import BuildDiariesOptions, build_diary_index

    diary = tmp_path / "Pepys"
    _make_diary_store(diary, with_vectors=True)
    result = build_diary_index(diary, BuildDiariesOptions(force=False))
    assert result.status == "skipped"
    assert "already built" in result.message


def test_build_diary_index_rebuilds_store_without_vectors(tmp_path):
    """A graph with no vector store must not count as 'already built'.

    rebuild_index() writes the graph before the vectors, so an interrupted run
    leaves this shape; skipping it would register a diary with no semantic
    search. dry_run stops before the actual build, so reaching the dry-run
    branch proves the resume gate declined to skip.
    """
    from gutenberg_kg.build_diaries import BuildDiariesOptions, build_diary_index

    diary = tmp_path / "Evelyn"
    _make_diary_store(diary, with_vectors=False)
    result = build_diary_index(diary, BuildDiariesOptions(force=False, dry_run=True))
    assert result.status == "skipped"
    assert "dry-run" in result.message, (
        "expected the build path, not the already-built short-circuit"
    )


def test_build_diary_index_rebuilds_empty_vector_store(tmp_path):
    """A vector store with zero rows is defective, not complete."""
    from gutenberg_kg.build_diaries import BuildDiariesOptions, build_diary_index

    diary = tmp_path / "Hebrides"
    _make_diary_store(diary, with_vectors=True, rows=0)
    result = build_diary_index(diary, BuildDiariesOptions(force=False, dry_run=True))
    assert "dry-run" in result.message


# ---------------------------------------------------------------------------
# build_diary_index releases its DiaryKG connection
# ---------------------------------------------------------------------------


def test_build_diary_index_closes_the_diarykg(tmp_path, monkeypatch):
    """The DiaryKG is closed, not left open once rebuild_index returns.

    DiaryKG holds a lazily constructed DocKG and its SQLite connection. Before
    diary-kg 0.98.0 there was no way to release it, so a corpus build leaked one
    connection per diary. This asserts the context manager is both entered and
    exited -- a bare constructor would satisfy `rebuild_index` and leak.
    """
    import diary_kg.kg as diary_kg_module

    from gutenberg_kg.build_diaries import BuildDiariesOptions, build_diary_index

    events: list[str] = []

    class _FakeDiaryKG:
        def __init__(self, root, model=None):
            self.root = root
            events.append("init")

        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, *exc):
            events.append("exit")
            self.close()
            return False

        def close(self):
            events.append("close")

        def rebuild_index(self):
            events.append("rebuild")

    monkeypatch.setattr(diary_kg_module, "DiaryKG", _FakeDiaryKG)

    diary = tmp_path / "Hebrides"
    chunks = diary / ".diary"
    chunks.mkdir(parents=True)
    (chunks / "entry_0001.md").write_text("an entry", encoding="utf-8")

    result = build_diary_index(diary, BuildDiariesOptions(force=False))

    assert result.status == "built", result.message
    assert events == ["init", "enter", "rebuild", "exit", "close"]


def test_build_diary_index_closes_even_when_rebuild_fails(tmp_path, monkeypatch):
    """A failed rebuild still releases the connection.

    The failure path returns a DiaryBuildResult rather than raising, so without
    a context manager the connection from a broken diary would leak for the rest
    of the run -- exactly the build where it matters least to hold it.
    """
    import diary_kg.kg as diary_kg_module

    from gutenberg_kg.build_diaries import BuildDiariesOptions, build_diary_index

    closed: list[str] = []

    class _ExplodingDiaryKG:
        def __init__(self, root, model=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            closed.append("closed")
            return False

        def rebuild_index(self):
            raise RuntimeError("corrupt chunk")

    monkeypatch.setattr(diary_kg_module, "DiaryKG", _ExplodingDiaryKG)

    diary = tmp_path / "Evelyn3"
    chunks = diary / ".diary"
    chunks.mkdir(parents=True)
    (chunks / "entry_0001.md").write_text("an entry", encoding="utf-8")

    result = build_diary_index(diary, BuildDiariesOptions(force=False))

    assert result.status == "failed"
    assert "corrupt chunk" in result.message
    assert closed == ["closed"]
