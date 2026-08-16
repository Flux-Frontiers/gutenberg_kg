"""
bookgraph.py — reading one book's knowledge graph off disk.

Corpus discovery and per-book graph loading, with no rendering stack attached:
plain ``sqlite3`` and the layout node/edge records the geometry layer consumes.
Kept apart from :mod:`gutenberg_kg.scene` so the whole POV-Ray pipeline — find
a book, grow it, write the ``.pov`` — runs without an installed PyVista.

:mod:`gutenberg_kg.scene` re-exports every name here, so existing imports keep
working.

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from kg_utils.viz3d import LayoutEdge, LayoutNode

__author__ = "Eric G. Suchanek, PhD"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CORPUS = "corpus"


# ---------------------------------------------------------------------------
# Book-domain data types
# ---------------------------------------------------------------------------


#: KG directories probed per book, in priority order. Prose books carry a
#: DocKG index in ``.dockg``; books routed through the diary pipeline carry a
#: DiaryKG index in ``.diarykg`` instead (same ``nodes``/``edges`` schema, one
#: ``document`` per dated entry rather than one per book).
KG_DIRS: tuple[str, ...] = (".dockg", ".diarykg")


@dataclass
class BookMeta:
    """Lightweight metadata for one corpus book."""

    title: str
    genre: str
    book_dir: Path

    @property
    def slug(self) -> str:
        """URL-safe identifier, used as a namespace prefix."""
        s = self.title.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        return re.sub(r"[\s-]+", "_", s)[:60]

    @property
    def kg_dir(self) -> Path | None:
        """First of :data:`KG_DIRS` holding a non-trivial graph, else ``None``."""
        for name in KG_DIRS:
            db = self.book_dir / name / "graph.sqlite"
            if db.exists() and db.stat().st_size > 100:
                return self.book_dir / name
        return None

    @property
    def db_path(self) -> Path:
        """Path to this book's KG SQLite graph file (DocKG or DiaryKG)."""
        found = self.kg_dir
        return (found / "graph.sqlite") if found else self.book_dir / KG_DIRS[0] / "graph.sqlite"

    @property
    def has_kg(self) -> bool:
        """Whether any of :data:`KG_DIRS` holds a non-trivial graph."""
        return self.kg_dir is not None


def load_book_graph(meta: BookMeta) -> tuple[list[LayoutNode], list[LayoutEdge]]:
    """
    Load nodes and edges from a book's DocKG SQLite, prefixing all IDs with
    the book slug to prevent collisions when merging multiple books.

    :param meta: Book metadata including slug and db_path.
    :return: ``(nodes, edges)`` with namespaced IDs.
    """
    prefix = f"{meta.slug}:"
    nodes: list[LayoutNode] = []
    edges: list[LayoutEdge] = []

    with sqlite3.connect(meta.db_path) as con:
        for row in con.execute("SELECT id, kind, name, title, file_path, text FROM nodes"):
            nid, kind, name, title, file_path, text = row
            display_name = title or name or nid
            docstring = text[:500] if text else None
            nodes.append(
                LayoutNode(
                    id=prefix + nid,
                    kind=kind,
                    name=display_name,
                    module_path=file_path,
                    docstring=docstring,
                )
            )
        for row in con.execute("SELECT src, rel, dst FROM edges"):
            src, rel, dst = row
            edges.append(LayoutEdge(src=prefix + src, rel=rel, dst=prefix + dst))

    return nodes, edges


def load_entry_times(meta: BookMeta) -> dict[str, str]:
    """
    Earliest chunk timestamp per document, for books that carry dates.

    DiaryKG stamps every chunk with the entry's date but leaves the document
    row's ``timestamp`` null, so the entry's date has to come up through its
    chunks.  The result lets :class:`ForestLayout` grow a diary's limbs from
    its chronology — one limb per year — rather than from position in the file.

    :param meta: Book metadata.
    :return: ``{namespaced document id: ISO timestamp}``; empty for books
        whose graph carries no timestamps at all.
    """
    prefix = f"{meta.slug}:"
    with sqlite3.connect(meta.db_path) as con:
        try:
            rows = con.execute(
                "SELECT e.src, MIN(n.timestamp) FROM edges e "
                "JOIN nodes n ON n.id = e.dst "
                "WHERE e.rel = 'CONTAINS' AND n.kind = 'chunk' AND n.timestamp IS NOT NULL "
                "GROUP BY e.src"
            ).fetchall()
        except sqlite3.OperationalError:
            # DocKG graphs predate the timestamp column; they simply have no dates.
            return {}
    return {prefix + src: ts for src, ts in rows if ts}


# ---------------------------------------------------------------------------
# Corpus scanner
# ---------------------------------------------------------------------------


def scan_corpus(corpus_root: Path) -> dict[str, list[BookMeta]]:
    """
    Walk ``corpus_root`` and return ``{genre: [BookMeta, ...]}`` for every
    book directory that carries a graph in one of :data:`KG_DIRS`.

    :param corpus_root: Root of the corpus directory tree.
    :return: Dict mapping genre name to list of book metadata objects.
    """
    result: dict[str, list[BookMeta]] = defaultdict(list)
    for genre_dir in sorted(corpus_root.iterdir()):
        if not genre_dir.is_dir() or genre_dir.name.startswith("."):
            continue
        genre = genre_dir.name
        for book_dir in sorted(genre_dir.iterdir()):
            if not book_dir.is_dir() or book_dir.name.startswith("."):
                continue
            meta = BookMeta(
                title=book_dir.name,
                genre=genre,
                book_dir=book_dir,
            )
            if meta.has_kg:
                result[genre].append(meta)
    return dict(result)
