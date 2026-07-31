"""Unit tests for gutenberg_kg.vector_store — vector store path resolution.

Deliberately free of any ``kg_rag`` dependency so these run in CI, unlike
``test_ingest.py`` which skips wholesale when kg_rag is absent.  The regression
these guard for is silent: registering ``None`` for both vector columns is
legal, so a store that resolves wrongly produces no error anywhere.
"""

from __future__ import annotations

from gutenberg_kg.vector_store import resolve_vector_paths


def _store(tmp_path, name=".dockg"):
    d = tmp_path / name
    d.mkdir()
    return d


class TestResolveVectorPaths:
    def test_migrated_store_returns_vectors_only(self, tmp_path):
        """A diary-kg >=0.94.0 / fresh DocKG store: vectors.sqlite, no lancedb."""
        d = _store(tmp_path)
        (d / "vectors.sqlite").touch()
        vectors, lancedb = resolve_vector_paths(d)
        assert vectors == d / "vectors.sqlite"
        assert lancedb is None

    def test_unmigrated_store_returns_lancedb_only(self, tmp_path):
        d = _store(tmp_path)
        (d / "lancedb").mkdir()
        vectors, lancedb = resolve_vector_paths(d)
        assert vectors is None
        assert lancedb == d / "lancedb"

    def test_vectors_wins_when_both_present(self, tmp_path):
        """Mid-migration: a stale lancedb/ must not be recorded alongside."""
        d = _store(tmp_path)
        (d / "vectors.sqlite").touch()
        (d / "lancedb").mkdir()
        vectors, lancedb = resolve_vector_paths(d)
        assert vectors == d / "vectors.sqlite"
        assert lancedb is None, "a migrated store must not carry a stale LanceDB pointer"

    def test_nothing_built_returns_none_pair(self, tmp_path):
        assert resolve_vector_paths(_store(tmp_path)) == (None, None)

    def test_missing_store_dir_returns_none_pair(self, tmp_path):
        assert resolve_vector_paths(tmp_path / "absent") == (None, None)

    def test_precedence_matches_the_read_path(self, tmp_path):
        """Mirrors handler._open_vector_source: sqlite-vec first, LanceDB second.

        The registration bug this module fixes was precisely the read path and
        the register path disagreeing, so pin the shared rule.
        """
        d = _store(tmp_path)
        (d / "lancedb").mkdir()
        assert resolve_vector_paths(d)[1] is not None
        (d / "vectors.sqlite").touch()
        assert resolve_vector_paths(d)[0] is not None
        assert resolve_vector_paths(d)[1] is None

    def test_diarykg_layout(self, tmp_path):
        """DiaryKG stores live under .diarykg/, not .dockg/."""
        d = _store(tmp_path, ".diarykg")
        (d / "vectors.sqlite").touch()
        assert resolve_vector_paths(d)[0] == d / "vectors.sqlite"
