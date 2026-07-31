"""vector_store.py — locate a KG's vector store during the sqlite-vec migration.

The fleet is mid-migration from LanceDB (a ``lancedb/`` directory) to sqlite-vec
(a single ``vectors.sqlite`` file), so any given store on disk may be either.
GutenbergKG orchestrates other KGs' stores — DocKG under ``.dockg/`` and DiaryKG
under ``.diarykg/`` — and therefore has to cope with both shapes at once.

The precedence here deliberately matches
:func:`gutenberg_kg.serve.handler._open_vector_source`, which already prefers
sqlite-vec and falls back to LanceDB when *reading*.  Keeping the registration
path on the same rule is the point: when the two disagree, a store is read from
one backend and registered as the other.

:seealso: ``kg_rag.primitives.KGEntry`` — ``vectors_path`` supersedes
    ``lancedb_path``, which stays readable for kinds that still ship LanceDB.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["resolve_vector_paths"]


def resolve_vector_paths(store_dir: Path) -> tuple[Path | None, Path | None]:
    """Return ``(vectors_path, lancedb_path)`` for a KG store directory.

    Exactly one of the two is non-``None`` (or both are, when nothing is built),
    so a migrated store never carries a stale LanceDB pointer alongside its
    sqlite-vec one:

    * ``vectors.sqlite`` present  → ``(<file>, None)`` — the migrated shape.
    * otherwise ``lancedb/`` present → ``(None, <dir>)`` — not yet migrated.
    * neither                    → ``(None, None)``.

    :param store_dir: The ``.dockg`` / ``.diarykg`` directory holding the store.
    :return: ``(vectors_path, lancedb_path)``, suitable for splatting straight
        into :class:`kg_rag.primitives.KGEntry`.
    """
    vectors = store_dir / "vectors.sqlite"
    if vectors.exists():
        return vectors, None
    lancedb = store_dir / "lancedb"
    if lancedb.exists():
        return None, lancedb
    return None, None
