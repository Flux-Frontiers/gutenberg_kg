"""Unit tests for gutenberg_kg.vector_store — vector store path resolution.

Deliberately free of any ``kg_rag`` dependency so these run in CI, unlike
``test_ingest.py`` which skips wholesale when kg_rag is absent.  The regression
these guard for is silent: registering ``None`` for the vector column is legal,
so a store that resolves wrongly produces no error anywhere.
"""

from __future__ import annotations

from gutenberg_kg.vector_store import resolve_vectors_path


def _store(tmp_path, name=".dockg"):
    d = tmp_path / name
    d.mkdir()
    return d


class TestResolveVectorsPath:
    def test_built_store_returns_its_vectors_file(self, tmp_path):
        d = _store(tmp_path)
        (d / "vectors.sqlite").touch()
        assert resolve_vectors_path(d) == d / "vectors.sqlite"

    def test_a_lancedb_store_is_not_a_store(self, tmp_path):
        """LanceDB support went with doc-kg/kgmodule-utils 0.29.0: never resolved."""
        d = _store(tmp_path)
        (d / "lancedb").mkdir()
        assert resolve_vectors_path(d) is None

    def test_a_stale_lancedb_beside_vectors_changes_nothing(self, tmp_path):
        d = _store(tmp_path)
        (d / "vectors.sqlite").touch()
        (d / "lancedb").mkdir()
        assert resolve_vectors_path(d) == d / "vectors.sqlite"

    def test_nothing_built_returns_none(self, tmp_path):
        assert resolve_vectors_path(_store(tmp_path)) is None

    def test_missing_store_dir_returns_none(self, tmp_path):
        assert resolve_vectors_path(tmp_path / "absent") is None

    def test_diarykg_layout(self, tmp_path):
        """DiaryKG stores live under .diarykg/, not .dockg/."""
        d = _store(tmp_path, ".diarykg")
        (d / "vectors.sqlite").touch()
        assert resolve_vectors_path(d) == d / "vectors.sqlite"
