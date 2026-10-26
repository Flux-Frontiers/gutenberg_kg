"""vector_store.py — locate a KG's sqlite-vec store.

GutenbergKG orchestrates other KGs' stores — DocKG under ``.dockg/`` and
DiaryKG under ``.diarykg/`` — and registers or reads each one's vector store.
The store is a single ``vectors.sqlite`` file. A ``lancedb/`` directory left by
a pre-migration build is not a store: LanceDB support was removed fleet-wide
with kgmodule-utils and doc-kg 0.29.0, so such a store is rebuilt, not read.

:seealso: ``kg_rag.primitives.KGEntry.vectors_path``.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["resolve_vectors_path"]


def resolve_vectors_path(store_dir: Path) -> Path | None:
    """Return the sqlite-vec store in a KG store directory, if it exists.

    :param store_dir: The ``.dockg`` / ``.diarykg`` directory holding the store.
    :return: ``<store_dir>/vectors.sqlite``, or ``None`` when it is not built.
    """
    vectors = store_dir / "vectors.sqlite"
    return vectors if vectors.exists() else None
