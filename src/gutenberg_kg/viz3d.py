"""
viz3d.py — 3-D Knowledge Tree Forest visualiser for GutenbergKG.

Each book is rendered as a tree:
  - Trunk   → document node (brown cylinder, height ∝ log(chunk_count))
  - Branches → section nodes (forest-green spheres radiating from trunk apex)
  - Leaves   → chunk nodes (light-green spheres clustered around each section)
  - Spores   → entity / topic nodes (gold dots floating above the canopy)

Books are grouped by genre into groves, with genres arranged in a large
Fibonacci annulus so the whole corpus forms a navigable 3-D forest.

Requires: pyvista, pyvistaqt, PyQt5, param, numpy
(all available in the pycode_kg environment).

Author: Eric G. Suchanek, PhD
"""

# pylint: disable=C0301,C0116,C0115,W0613,E0611,C0415

from __future__ import annotations

import atexit
import gc
import logging
import re
import sqlite3
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import param
import pyvista as pv
from markdown import markdown  # type: ignore[import-untyped]
from pycode_kg.layout3d import Layout3D, LayoutEdge, LayoutNode, fibonacci_annulus, fibonacci_sphere
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor
from rich.logging import RichHandler

from gutenberg_kg import __version__

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.WARNING, handlers=[RichHandler()])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

__author__ = "Eric G. Suchanek, PhD"

DEFAULT_CORPUS = "corpus"
DEFAULT_SAVE = "gutenberg_forest_3d"

CONTROL_PANEL_WIDTH: int = 260
BUTTON_WIDTH: int = 120
ZOOM_FACTOR: float = 8.0

# Node colours — tree metaphor
KIND_COLOR: dict[str, str] = {
    "document": "#8B4513",  # saddle brown  — trunk root marker
    "section": "#2E8B57",  # sea green     — branch
    "chunk": "#90EE90",  # light green   — leaf
    "entity": "#FFD700",  # gold          — spore
    "topic": "#4169E1",  # royal blue    — pollen cloud
    "keyword": "#A0A0A0",  # gray          — background noise
}

# Node sizes (sphere radius in scene units)
KIND_SIZE: dict[str, float] = {
    "document": 1.8,
    "section": 0.9,
    "chunk": 0.28,
    "entity": 0.18,
    "topic": 0.22,
    "keyword": 0.12,
}

# Trunk colour (visual cylinder, not a node mesh)
TRUNK_COLOR = "#8B4513"  # saddle brown
BRANCH_COLOR = "#556B2F"  # dark olive green

# 10-color genre palette — dark-bg friendly, colour-blind safe
GENRE_PALETTE: list[str] = [
    "#E74C3C",  # crimson
    "#3498DB",  # azure
    "#2ECC71",  # emerald
    "#F39C12",  # amber
    "#9B59B6",  # purple
    "#1ABC9C",  # teal
    "#E67E22",  # orange
    "#E91E63",  # rose
    "#00BCD4",  # cyan
    "#CDDC39",  # lime
]

# Edge colours
REL_COLOR: dict[str, str] = {
    "CONTAINS": "#555555",
    "NEXT": "#3498DB",
    "SIMILAR_TO": "#E74C3C",
    "CO_OCCURS_WITH": "#9B59B6",
}

# LOD thresholds (total visible nodes)
LOD_HIGH: int = 3000
LOD_LOW: int = 8000

# ---------------------------------------------------------------------------
# Book-domain data types
# ---------------------------------------------------------------------------


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
    def db_path(self) -> Path:
        return self.book_dir / ".dockg" / "graph.sqlite"

    @property
    def has_kg(self) -> bool:
        return self.db_path.exists() and self.db_path.stat().st_size > 100


def _load_book_graph(
    meta: BookMeta,
) -> tuple[list[LayoutNode], list[LayoutEdge]]:
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


# ---------------------------------------------------------------------------
# Corpus scanner
# ---------------------------------------------------------------------------


def scan_corpus(corpus_root: Path) -> dict[str, list[BookMeta]]:
    """
    Walk ``corpus_root`` and return ``{genre: [BookMeta, ...]}`` for every
    book directory that contains a ``.dockg/graph.sqlite``.

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


# ---------------------------------------------------------------------------
# ForestLayout — books as trees, genres as groves
# ---------------------------------------------------------------------------

# How far above the trunk apex sections branch out
_BRANCH_LIFT: float = 0.5  # fraction of trunk height


class ForestLayout(Layout3D):
    """
    3-D forest layout for a multi-book corpus.

    Spatial structure
    -----------------
    - **Genres** are placed in a large Fibonacci annulus in the XY plane
      (each genre → a grove at a fixed XY centre).
    - **Books** within a genre are placed in a medium Fibonacci annulus around
      the genre centre.
    - **Per book (tree)**:
        - ``document`` node sits at the book's XY position, ``Z = 0``
          (trunk base marker).
        - ``section`` nodes are distributed on a Fibonacci upper hemisphere
          centred at the trunk apex ``(bx, by, trunk_height)``.
          Trunk height scales as ``log2(1 + n_chunks)``.
        - ``chunk`` nodes cluster around their parent section node in a small
          Fibonacci sphere.
        - ``entity``/``topic`` nodes float in a loose cloud above the canopy
          at ``Z = trunk_height + canopy_lift``.

    :param grove_inner_radius: Inner radius for genre placement ring.
    :param grove_outer_radius: Minimum outer radius for genre ring.
    :param book_inner_radius: Inner radius for books within a genre grove.
    :param book_outer_radius: Minimum outer radius within a genre grove.
    :param trunk_scale: Multiplier for trunk height (``trunk_height = trunk_scale * log2(1 + n_chunks)``).
    :param branch_radius: Base radius of the Fibonacci hemisphere for sections.
    :param leaf_radius: Base radius of the leaf sphere per section.
    :param canopy_lift: Z offset above trunk apex for entity / topic nodes.
    """

    def __init__(
        self,
        grove_inner_radius: float = 80.0,
        grove_outer_radius: float = 240.0,
        book_inner_radius: float = 5.0,
        book_outer_radius: float = 18.0,
        trunk_scale: float = 4.0,
        max_trunk_height: float = 45.0,
        branch_radius: float = 5.0,
        leaf_radius: float = 1.5,
        canopy_lift: float = 4.0,
    ) -> None:
        self.grove_inner_radius = grove_inner_radius
        self.grove_outer_radius = grove_outer_radius
        self.book_inner_radius = book_inner_radius
        self.book_outer_radius = book_outer_radius
        self.trunk_scale = trunk_scale
        self.max_trunk_height = max_trunk_height
        self.branch_radius = branch_radius
        self.leaf_radius = leaf_radius
        self.canopy_lift = canopy_lift

        # Set during compute() so render helpers can read them
        self.trunk_positions: dict[str, np.ndarray] = {}  # doc_node_id → XYZ base
        self.trunk_heights: dict[str, float] = {}  # doc_node_id → height
        self.trunk_genres: dict[str, str] = {}  # doc_node_id → genre
        self.genre_color_map: dict[str, str] = {}  # genre → hex color
        # (trunk_axis_pt, section_tip_pt) for every section — drawn as branch lines
        self.branch_lines: list[tuple[np.ndarray, np.ndarray]] = []

    def compute(
        self,
        nodes: list[LayoutNode],
        edges: list[LayoutEdge],
    ) -> dict[str, np.ndarray]:
        """
        Compute 3-D positions for every node in the combined forest.

        :param nodes: All nodes across all loaded books (IDs already namespaced).
        :param edges: All edges across all loaded books.
        :return: Mapping from node ID to ``[x, y, z]`` position.
        """
        # Reset per-compute state
        self.branch_lines = []

        # Build containment hierarchy
        children: dict[str, list[str]] = defaultdict(list)
        for e in edges:
            if e.rel == "CONTAINS":
                children[e.src].append(e.dst)

        node_by_id = {n.id: n for n in nodes}
        positions: dict[str, np.ndarray] = {}

        # Group nodes by book slug (= first token before first ":")
        books_nodes: dict[str, list[LayoutNode]] = defaultdict(list)
        for n in nodes:
            slug = n.id.split(":")[0]
            books_nodes[slug].append(n)

        # Group books by genre (slug → genre extracted from module_path / id)
        # We infer genre from document nodes: their module_path is the filename;
        # the genre was embedded by the caller into a special metadata node.
        # Simpler: group by traversal order — caller sets book_genre_map.
        # Use self._book_genre_map if set, else treat all books as one genre.
        book_genre_map: dict[str, str] = getattr(self, "_book_genre_map", {})

        genres_books: dict[str, list[str]] = defaultdict(list)
        for slug in books_nodes:
            genre = book_genre_map.get(slug, "unknown")
            genres_books[genre].append(slug)

        # Place genres in a large Fibonacci annulus
        genre_list = sorted(genres_books.keys())
        n_genres = max(len(genre_list), 1)
        genre_outer = max(self.grove_outer_radius, self.grove_inner_radius + n_genres * 12.0)
        grove_centers = fibonacci_annulus(
            n_genres,
            inner_radius=self.grove_inner_radius,
            outer_radius=genre_outer,
            center=np.zeros(3),
            z_thickness=0.0,
        )
        genre_center_map: dict[str, np.ndarray] = {
            g: np.array(p) for g, p in zip(genre_list, grove_centers)
        }
        self.genre_color_map = {
            g: GENRE_PALETTE[i % len(GENRE_PALETTE)] for i, g in enumerate(genre_list)
        }

        # For each genre, place books in a medium annulus around the grove centre
        for genre, grove_center in genre_center_map.items():
            slugs = genres_books[genre]
            n_books = max(len(slugs), 1)
            book_outer = max(self.book_outer_radius, self.book_inner_radius + n_books * 3.0)
            book_positions = fibonacci_annulus(
                n_books,
                inner_radius=self.book_inner_radius,
                outer_radius=book_outer,
                center=grove_center,
                z_thickness=0.0,
            )

            for slug, book_xy in zip(slugs, book_positions):
                bx, by = float(book_xy[0]), float(book_xy[1])
                book_nodes = books_nodes[slug]

                # Count chunks to determine trunk height; cap so no book dominates
                n_chunks = sum(1 for n in book_nodes if n.kind == "chunk")
                trunk_height = min(
                    self.trunk_scale * max(1.0, np.log2(1 + n_chunks)),
                    self.max_trunk_height,
                )
                trunk_apex = np.array([bx, by, trunk_height])

                # Find document nodes (trunk base)
                doc_nodes = [n for n in book_nodes if n.kind == "document"]
                for doc in doc_nodes:
                    positions[doc.id] = np.array([bx, by, 0.0])
                    self.trunk_positions[doc.id] = np.array([bx, by, 0.0])
                    self.trunk_heights[doc.id] = trunk_height
                    self.trunk_genres[doc.id] = genre

                # Section nodes — spiral up the trunk (B: real tree branching)
                section_nodes = [n for n in book_nodes if n.kind == "section"]
                n_sections = len(section_nodes)
                golden_angle = np.pi * (3.0 - np.sqrt(5.0))  # ≈ 137.5°
                branch_length = 0.0  # reused by canopy cloud below
                if n_sections:
                    branch_length = self.branch_radius + np.sqrt(n_sections) * 0.5
                    for i, sec in enumerate(section_nodes):
                        t = i / max(n_sections - 1, 1)
                        z = trunk_height * (0.30 + 0.65 * t)
                        angle = i * golden_angle
                        radius = branch_length * (1.0 - (z / trunk_height) * 0.4)
                        sec_pos = np.array(
                            [
                                bx + radius * np.cos(angle),
                                by + radius * np.sin(angle),
                                z,
                            ]
                        )
                        positions[sec.id] = sec_pos
                        # Branch line: point on trunk axis at section's Z → section tip
                        self.branch_lines.append((np.array([bx, by, z]), sec_pos))

                # Chunk nodes — upper-hemisphere cone above each branch tip
                sec_chunks: dict[str, list[str]] = {
                    n.id: children.get(n.id, []) for n in section_nodes
                }
                for sec in section_nodes:
                    _pos = positions.get(sec.id)
                    if _pos is None:
                        continue
                    sec_pos = _pos
                    chunk_ids = [
                        cid
                        for cid in sec_chunks.get(sec.id, [])
                        if node_by_id.get(cid) and node_by_id[cid].kind == "chunk"
                    ]
                    n_c = len(chunk_ids)
                    if not n_c:
                        continue
                    leaf_r = self.leaf_radius + np.sqrt(n_c) * 0.12
                    raw_pts = fibonacci_sphere(n_c * 3, radius=leaf_r, center=sec_pos)
                    upper_pts = [p for p in raw_pts if p[2] >= float(sec_pos[2])]
                    if len(upper_pts) < n_c:
                        # Reflect insufficient points above branch Z
                        upper_pts = [
                            np.array(
                                [p[0], p[1], float(sec_pos[2]) + abs(p[2] - float(sec_pos[2]))]
                            )
                            for p in raw_pts[:n_c]
                        ]
                    for cid, cpos in zip(chunk_ids, upper_pts[:n_c]):
                        positions[cid] = np.array(cpos)

                # Chunks without a section parent (connected directly to document)
                doc_chunk_ids: list[str] = []
                for doc in doc_nodes:
                    doc_chunk_ids.extend(
                        cid
                        for cid in children.get(doc.id, [])
                        if node_by_id.get(cid)
                        and node_by_id[cid].kind == "chunk"
                        and cid not in positions
                    )
                if doc_chunk_ids:
                    raw_pts = fibonacci_sphere(
                        len(doc_chunk_ids) * 2, radius=self.leaf_radius, center=trunk_apex
                    )
                    upper_pts = [p for p in raw_pts if p[2] >= float(trunk_apex[2])]
                    if len(upper_pts) < len(doc_chunk_ids):
                        upper_pts = raw_pts[: len(doc_chunk_ids)]
                    for cid, cpos in zip(doc_chunk_ids, upper_pts[: len(doc_chunk_ids)]):
                        positions[cid] = np.array(cpos)

                # Entity / topic / keyword → loose cloud above canopy
                canopy_z = trunk_height + self.canopy_lift
                canopy_center = np.array([bx, by, canopy_z])
                floaters = [
                    n
                    for n in book_nodes
                    if n.kind in ("entity", "topic", "keyword") and n.id not in positions
                ]
                if floaters:
                    cloud_r = branch_length * 1.1 if n_sections else self.branch_radius
                    cloud_pts = fibonacci_sphere(
                        len(floaters), radius=cloud_r, center=canopy_center
                    )
                    for n, pos in zip(floaters, cloud_pts):
                        positions[n.id] = np.array(pos)

        # Orphans (anything still unplaced)
        orphans = [n for n in nodes if n.id not in positions]
        if orphans:
            orphan_pts = fibonacci_sphere(len(orphans), radius=5.0, center=np.zeros(3))
            for n, pos in zip(orphans, orphan_pts):
                positions[n.id] = np.array(pos)

        return positions


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _arc_points(p1: np.ndarray, p2: np.ndarray, n_pts: int = 24, lift: float = 0.35) -> np.ndarray:
    """
    Quadratic Bézier arc from *p1* to *p2*, apex lifted in Z.

    :param p1: Start point.
    :param p2: End point.
    :param n_pts: Sample count.
    :param lift: Z lift as fraction of chord length.
    :return: ``(n_pts, 3)`` array.
    """
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    mid = (p1 + p2) / 2.0
    mid[2] += lift * np.linalg.norm(p2 - p1)
    t = np.linspace(0.0, 1.0, n_pts)[:, None]
    return (1 - t) ** 2 * p1 + 2 * t * (1 - t) * mid + t**2 * p2


def _make_node_mesh(kind: str, center: np.ndarray, size: float, lod: str) -> pv.DataSet:
    """
    Return a PyVista mesh for a single node, shape-coded by kind.

    All tiers use icosahedra — fast to build, good shading, no sphere overhead.
    LOD only varies the radius scale:
    - high  → full size
    - low   → 80 % size (octahedron for chunks to save faces)
    - points → tetrahedron (4 faces, minimal cost)

    :param kind: Node kind string.
    :param center: 3-D centre position.
    :param size: Node radius.
    :param lod: LOD tier — ``"high"``, ``"low"``, or ``"points"``.
    :return: PyVista PolyData mesh.
    """
    if lod == "points":
        return pv.Tetrahedron(radius=size * 0.5, center=center)
    if lod == "low":
        if kind in ("chunk", "entity", "keyword", "topic"):
            return pv.Octahedron(radius=size * 0.8, center=center)
        return pv.Icosahedron(radius=size * 0.8, center=center)
    # high — full icosahedra for everything
    return pv.Icosahedron(radius=size, center=center)


def _glyph_proto(kind: str, size: float, lod: str) -> pv.PolyData:
    """Return a glyph prototype mesh centred at the origin for *kind* nodes.

    Used with ``pv.PolyData.glyph()`` so all nodes of one kind are rendered
    in a single VTK draw call instead of one mesh per node.

    :param kind: Node kind string.
    :param size: Node radius.
    :param lod: LOD tier — ``"high"``, ``"low"``, or ``"points"``.
    :return: PyVista PolyData centred at origin.
    """
    if lod == "points":
        return pv.Tetrahedron(radius=size * 0.5)
    if lod == "low":
        if kind in ("chunk", "entity", "keyword", "topic"):
            return pv.Octahedron(radius=size * 0.8)
        return pv.Icosahedron(radius=size * 0.8)
    return pv.Icosahedron(radius=size)


def _text_to_markdown(text: str | None) -> str:
    """Format a raw text excerpt as Markdown for the popup.

    :param text: Raw node text (chunk content, entity name, etc.).
    :return: Markdown string.
    """
    if not text:
        return "No text available."
    return text.strip()


# ---------------------------------------------------------------------------
# DocstringPopup — reused from pycode_kg pattern
# ---------------------------------------------------------------------------


class TextPopup(QDialog):
    """
    Modeless popup that renders node text as Markdown HTML.

    :param title: Window title.
    :param text: Raw text content.
    :param parent: Parent widget.
    :param on_close_callback: Called when the window closes.
    """

    def __init__(self, title: str, text: str, parent=None, on_close_callback=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 420)
        self.on_close_callback = on_close_callback
        self.setWindowModality(Qt.NonModal)  # type: ignore[attr-defined]

        if parent:
            geo = parent.screen().geometry()
            self.move(geo.x() + 60, geo.y() + 60)

        layout = QVBoxLayout(self)
        html = markdown(text or "No text available.")
        browser = QTextBrowser(self)
        browser.setHtml(html)
        layout.addWidget(browser)

        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.close)  # type: ignore[arg-type]
        layout.addWidget(close_btn)

    def closeEvent(self, event):
        if self.on_close_callback:
            self.on_close_callback()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# create_forest_visualization
# ---------------------------------------------------------------------------


def create_forest_visualization(
    viz: GutenbergForestVisualizer,
    nodes: list[LayoutNode],
    edges: list[LayoutEdge],
    plotter: pv.Plotter,
) -> tuple[pv.Plotter, str, dict[str, dict]]:
    """
    Render the knowledge tree forest into *plotter*.

    Draws:
    - Forest floor (ground plane)
    - Per-book trunk cylinders (visual, not node meshes)
    - Node meshes grouped by kind (LOD-aware)
    - Structural edges (CONTAINS gray lines; SIMILAR_TO arcs)

    :param viz: :class:`GutenbergForestVisualizer` instance.
    :param nodes: Filtered node list to render.
    :param edges: Full edge list (used for layout and edge rendering).
    :param plotter: The ``QtInteractor`` to render into.
    :return: ``(plotter, title_text, actor_to_node)``
    """
    viz.status = "Building forest scene..."
    QApplication.processEvents()

    plotter.clear_actors()
    plotter.enable_anti_aliasing("msaa")
    plotter.set_background("#1a1a2e", top="#16213e")  # type: ignore[arg-type]  # night forest sky

    # Ground plane — sized for 2× grove spacing
    ground = pv.Plane(center=(0, 0, -0.2), direction=(0, 0, 1), i_size=1000, j_size=1000)
    plotter.add_mesh(ground, color="#2d4a1e", opacity=1.0, name="ground")

    # -- Compute layout
    layout = ForestLayout()
    layout._book_genre_map = viz._book_genre_map  # type: ignore[attr-defined]
    all_positions = layout.compute(viz.all_nodes, viz.all_edges)

    # -- Draw trunk cylinders — single merged mesh with genre_idx scalar (A)
    # One add_mesh call regardless of genre count keeps actor/texture count low.
    viz.status = "Drawing trunks..."
    QApplication.processEvents()
    _trunk_meshes: list[pv.PolyData] = []
    _genre_list_ord = sorted(layout.genre_color_map.keys())
    _genre_to_idx: dict[str, float] = {g: float(i) for i, g in enumerate(_genre_list_ord)}
    for doc_id, base in layout.trunk_positions.items():
        height = layout.trunk_heights.get(doc_id, 8.0)
        genre = layout.trunk_genres.get(doc_id, "unknown")
        cyl = pv.Cylinder(
            center=(base[0], base[1], height / 2),
            direction=(0, 0, 1),
            radius=0.4,
            height=height,
            resolution=12,
        )
        cyl.cell_data["genre_idx"] = np.full(cyl.n_cells, _genre_to_idx.get(genre, 0.0))
        _trunk_meshes.append(cyl)
    if _trunk_meshes:
        from matplotlib.colors import ListedColormap  # pyvista dependency, always present

        _combined_trunks = pv.merge(_trunk_meshes)
        _genre_colors = [layout.genre_color_map.get(g, TRUNK_COLOR) for g in _genre_list_ord]
        _trunk_cmap = ListedColormap(_genre_colors)
        _n_genres = max(1, len(_genre_list_ord))
        plotter.add_mesh(
            _combined_trunks,
            scalars="genre_idx",
            cmap=_trunk_cmap,
            clim=[-0.5, _n_genres - 0.5],
            show_scalar_bar=False,
            name="trunks",
        )

    # -- Branch lines: trunk-axis point → section tip (flat numpy, zero per-line objects)
    if layout.branch_lines:
        _n_bl = len(layout.branch_lines)
        _bl_pts = np.empty((_n_bl * 2, 3), dtype=float)
        _bl_pts[0::2] = [bl[0] for bl in layout.branch_lines]
        _bl_pts[1::2] = [bl[1] for bl in layout.branch_lines]
        _bl_cells = np.empty(_n_bl * 3, dtype=np.intp)
        _bl_cells[0::3] = 2
        _bl_cells[1::3] = np.arange(0, _n_bl * 2, 2)
        _bl_cells[2::3] = np.arange(1, _n_bl * 2 + 1, 2)
        _branch_mesh = pv.PolyData()
        _branch_mesh.points = _bl_pts
        _branch_mesh.lines = _bl_cells
        plotter.add_mesh(
            _branch_mesh, color=BRANCH_COLOR, line_width=2.0, opacity=0.85, name="branches"
        )

    # -- LOD tier
    n_visible = len(nodes)
    lod = "high" if n_visible <= LOD_HIGH else "low" if n_visible <= LOD_LOW else "points"

    # -- Glyph rendering: O(kinds) Python work, not O(nodes)
    # Bucket positions and metadata by kind in one pass, then glyph each kind.
    kind_pts: dict[str, list[np.ndarray]] = {k: [] for k in KIND_SIZE}
    kind_meta: dict[str, list] = {k: [] for k in KIND_SIZE}
    node_id_set: set[str] = set()

    for node in nodes:
        pos = all_positions.get(node.id)
        if pos is None:
            continue
        kind = node.kind if node.kind in KIND_SIZE else "chunk"
        kind_pts[kind].append(pos)
        kind_meta[kind].append(node)
        node_id_set.add(node.id)

    actor_to_node: dict[str, dict] = {}
    viz.status = "Rendering nodes..."
    QApplication.processEvents()

    for kind in KIND_SIZE:
        pts = kind_pts[kind]
        if not pts:
            continue
        arr = np.array(pts, dtype=float)
        cloud = pv.PolyData(arr)
        proto = _glyph_proto(kind, KIND_SIZE[kind], lod)
        glyphed = cloud.glyph(geom=proto, orient=False, scale=False)
        plotter.add_mesh(glyphed, color=KIND_COLOR[kind], show_edges=False, name=f"{kind}_nodes")
        for i, (node, pos) in enumerate(zip(kind_meta[kind], pts)):
            actor_to_node[f"{kind}_{i}"] = {
                "kind": kind,
                "id": node.id,
                "name": node.name,
                "docstring": node.docstring,
                "position": np.asarray(pos, float),
            }

    # -- Edge rendering (CONTAINS structural lines + optional SIMILAR_TO arcs)
    viz.status = "Rendering edges..."
    QApplication.processEvents()

    rel_to_show: set[str] = set()
    if viz.show_contains:
        rel_to_show.add("CONTAINS")
    if viz.show_similar:
        rel_to_show.add("SIMILAR_TO")
    if viz.show_next:
        rel_to_show.add("NEXT")

    rel_blocks: dict[str, pv.MultiBlock] = {r: pv.MultiBlock() for r in rel_to_show}
    edge_counts: dict[str, int] = {r: 0 for r in rel_to_show}
    MAX_EDGES = 4000

    for edge in edges:
        if edge.rel not in rel_to_show:
            continue
        if edge.src not in node_id_set or edge.dst not in node_id_set:
            continue
        if edge_counts[edge.rel] >= MAX_EDGES:
            continue
        p1, p2 = all_positions.get(edge.src), all_positions.get(edge.dst)
        if p1 is None or p2 is None:
            continue
        if edge.rel == "CONTAINS":
            rel_blocks["CONTAINS"].append(pv.Line(p1, p2))
        else:
            arc_pts = _arc_points(p1, p2)
            rel_blocks[edge.rel].append(pv.Spline(arc_pts, n_points=24))
        edge_counts[edge.rel] += 1

    for rel, block in rel_blocks.items():
        if block.n_blocks > 0:
            is_contains = rel == "CONTAINS"
            plotter.add_mesh(
                block,
                color=REL_COLOR[rel],
                line_width=3.0 if is_contains else 2.0,
                opacity=0.45 if is_contains else 0.8,
                name=f"{rel.lower()}_edges",
            )

    # -- Stats
    counts = Counter(n.kind for n in nodes)
    title = (
        f"Gutenberg KG Forest | {len({n.id.split(':')[0] for n in viz.all_nodes})} books | "
        f"docs={counts.get('document', 0)}  "
        f"sections={counts.get('section', 0)}  "
        f"chunks={counts.get('chunk', 0)}  "
        f"entities={counts.get('entity', 0)}"
    )

    plotter.reset_camera()  # type: ignore[call-arg]
    plotter.view_isometric()  # type: ignore[call-arg]
    plotter.render()
    plotter.camera.zoom(2)

    viz.status = "Forest rendered."
    QApplication.processEvents()
    return plotter, title, actor_to_node


# ---------------------------------------------------------------------------
# GutenbergForestVisualizer — data and state model
# ---------------------------------------------------------------------------


class GutenbergForestVisualizer(param.Parameterized):
    """
    Data and state model for the Gutenberg 3-D forest visualiser.

    Reactive attributes (via ``param``) drive the Qt control panel.

    :param corpus_root: Path to the corpus directory.
    :param plotter: The ``QtInteractor`` to render into.
    """

    corpus_root: str = param.String(default=DEFAULT_CORPUS, doc="Corpus root path")
    save_path: str = param.String(default=DEFAULT_SAVE, doc="Save path stem")
    save_format: str = param.Selector(
        objects=["html", "png", "jpg"], default="html", doc="Export format"
    )

    # Visibility toggles by node kind
    show_sections: bool = param.Boolean(default=True, doc="Render section (branch) nodes")
    show_chunks: bool = param.Boolean(default=True, doc="Render chunk (leaf) nodes")
    show_entities: bool = param.Boolean(default=False, doc="Render entity / topic nodes")

    # Edge visibility
    show_contains: bool = param.Boolean(default=False, doc="CONTAINS structural edges")
    show_similar: bool = param.Boolean(default=False, doc="SIMILAR_TO semantic edges")
    show_next: bool = param.Boolean(default=False, doc="NEXT sequential edges")

    # Status / title
    status: str = param.String(default="Ready", doc="Status bar text")
    window_title: str = param.String(
        default=f"Gutenberg KG Forest v{__version__}", doc="Window title"
    )

    # Stats
    num_books: int = param.Integer(default=0)
    num_genres: int = param.Integer(default=0)

    # Genre / book selectors
    available_genres: list[str] = param.List(default=[], doc="Available genre names")
    selected_genres: list[str] = param.ListSelector(default=[], objects=[], doc="Selected genres")
    available_books: list[str] = param.List(default=[], doc="Books in selected genres")
    selected_books: list[str] = param.ListSelector(
        default=[], objects=[], doc="Selected books (empty = all in genre)"
    )

    def __init__(self, plotter: pv.Plotter | None = None, **params) -> None:
        """
        Initialise the visualiser data model.

        :param plotter: The ``QtInteractor`` to render into.
        :param params: Additional ``param`` keyword arguments.
        """
        super().__init__(**params)
        self.plotter: pv.Plotter | None = plotter

        # Book catalogue: {genre: [BookMeta]}
        self._catalogue: dict[str, list[BookMeta]] = {}
        # Loaded graph data (all books currently selected)
        self.all_nodes: list[LayoutNode] = []
        self.all_edges: list[LayoutEdge] = []
        # slug → genre mapping for ForestLayout
        self._book_genre_map: dict[str, str] = {}

        self.actor_to_node: dict[str, dict] = {}
        self._load_catalogue()

    @param.depends("corpus_root", watch=True)
    def _load_catalogue(self) -> None:
        """Scan corpus_root and populate the genre/book selectors."""
        root = Path(self.corpus_root)
        if not root.exists():
            self.status = f"Corpus not found: {root}"
            return

        self.status = "Scanning corpus..."
        QApplication.processEvents()

        self._catalogue = scan_corpus(root)
        genres = sorted(self._catalogue.keys())
        self.available_genres = genres
        self.param.selected_genres.objects = genres
        self.selected_genres = []

        n_books = sum(len(v) for v in self._catalogue.values())
        self.num_genres = len(genres)
        self.num_books = n_books
        self.status = f"Corpus: {len(genres)} genres, {n_books} ingested books"

    @param.depends("selected_genres", watch=True)
    def _on_genre_change(self) -> None:
        """Refresh available books when genre selection changes."""
        books: list[str] = []
        for genre in self.selected_genres:
            for meta in self._catalogue.get(genre, []):
                books.append(meta.title)
        books.sort()
        self.available_books = books
        self.param.selected_books.objects = books
        self.selected_books = []

    def load_selected(self) -> None:
        """
        Load nodes and edges for the currently selected genres/books.
        Populates :attr:`all_nodes`, :attr:`all_edges`, :attr:`_book_genre_map`.
        """
        self.status = "Loading book graphs..."
        QApplication.processEvents()

        genres_to_load = self.selected_genres or list(self._catalogue.keys())
        books_filter = set(self.selected_books)

        self.all_nodes = []
        self.all_edges = []
        self._book_genre_map = {}

        loaded = 0
        for genre in genres_to_load:
            for meta in self._catalogue.get(genre, []):
                if books_filter and meta.title not in books_filter:
                    continue
                self.status = f"Loading: {meta.title}"
                QApplication.processEvents()
                try:
                    nodes, edges = _load_book_graph(meta)
                    self.all_nodes.extend(nodes)
                    self.all_edges.extend(edges)
                    self._book_genre_map[meta.slug] = genre
                    loaded += 1
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.warning("Failed to load %s: %s", meta.title, exc)

        self.status = (
            f"Loaded {loaded} book(s): {len(self.all_nodes):,} nodes, {len(self.all_edges):,} edges"
        )

    def _visible_nodes(self) -> list[LayoutNode]:
        """Apply kind visibility filters and return renderable node list."""
        visible_kinds: set[str] = {"document"}
        if self.show_sections:
            visible_kinds.add("section")
        if self.show_chunks:
            visible_kinds.add("chunk")
        if self.show_entities:
            visible_kinds.update(("entity", "topic", "keyword"))
        return [n for n in self.all_nodes if n.kind in visible_kinds]

    def visualize(self) -> None:
        """Load selected books and render the 3-D forest."""
        if not self.plotter:
            return
        self.load_selected()
        if not self.all_nodes:
            self.status = "No books loaded — select a genre and render."
            return

        visible = self._visible_nodes()
        try:
            _, title, actor_to_node = create_forest_visualization(
                self, visible, self.all_edges, self.plotter
            )
            self.actor_to_node = actor_to_node
            self.window_title = title
        except (ValueError, RuntimeError) as exc:
            self.status = f"Error: {exc}"
            logger.exception("Render error")


# ---------------------------------------------------------------------------
# ForestMainWindow
# ---------------------------------------------------------------------------


class ForestMainWindow(QMainWindow):
    """
    Qt main window for the Gutenberg 3-D forest visualiser.

    Left panel  — corpus path, genre selector, book selector, render options.
    Right panel — PyVista QtInteractor + button row.

    :param corpus_root: Path to the corpus directory.
    :param save_path: Default output file stem for exports.
    :param width: Initial window width in pixels.
    :param height: Initial window height in pixels.
    """

    status_changed: pyqtSignal = pyqtSignal(str)

    def __init__(
        self,
        corpus_root: str = DEFAULT_CORPUS,
        save_path: str = DEFAULT_SAVE,
        width: int = 1500,
        height: int = 950,
    ) -> None:
        super().__init__()
        self.timer = None
        self._current_picked_actor = None
        self._current_popup: TextPopup | None = None

        self.setGeometry(100, 100, width, height)

        self.vtk_plotter: QtInteractor = QtInteractor(self)
        self.visualizer: GutenbergForestVisualizer = GutenbergForestVisualizer(
            plotter=self.vtk_plotter,
            corpus_root=corpus_root,
            save_path=save_path,
        )
        self.plotter = self.vtk_plotter

        self.setWindowTitle(self.visualizer.window_title)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        self.setStyleSheet("""
            QPushButton {
                background-color: #2E8B57; color: white;
                border: none; border-radius: 3px; padding: 6px; margin: 2px;
            }
            QPushButton#reset-view  { background-color: #FFEB3B; color: black; }
            QPushButton#reset-all   { background-color: #8B0000; color: white; }
            QPushButton { font-size: 12px; }
            QWidget { background-color: #1a1a2e; color: #e0e0e0; }
            QLabel  { background: transparent; border: none; }
        """)

        ctrl_widget = self._build_control_panel()
        vis_widget = self._build_viewport_panel()

        main_layout.addWidget(ctrl_widget)
        main_layout.addWidget(vis_widget, stretch=1)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        ctrl_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)

        self._setup_mesh_picking()
        self._connect_signals()

        self.setFont(QFont("Arial", 12))
        self.resize(width, height)

    # -- UI builder helpers --------------------------------------------------

    @staticmethod
    def _h2(text: str) -> QLabel:
        lbl = QLabel(f"<b style='font-size:13px;color:#90EE90'>{text}</b>")
        lbl.setStyleSheet("background:transparent; border:none;")
        return lbl

    @staticmethod
    def _lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("background:transparent; border:none; color:#c0c0c0;")
        return lbl

    def _build_control_panel(self) -> QWidget:
        ctrl = QVBoxLayout()
        ctrl.setSpacing(10)
        ctrl.setContentsMargins(6, 6, 6, 6)

        # Corpus path
        ctrl.addWidget(self._h2("Corpus"))
        self.corpus_input = QLineEdit(self.visualizer.corpus_root)
        self.corpus_input.setPlaceholderText("corpus/")
        ctrl.addWidget(self.corpus_input)

        # Genre selector
        ctrl.addWidget(self._h2("Genres"))
        ctrl.addWidget(self._lbl("Select genres (empty = all):"))
        self.genre_selector = QListWidget()
        self.genre_selector.setSelectionMode(QListWidget.MultiSelection)
        self.genre_selector.setMaximumHeight(100)
        for g in self.visualizer.available_genres:
            self.genre_selector.addItem(g)
        ctrl.addWidget(self.genre_selector)

        # Book selector
        ctrl.addWidget(self._h2("Books"))
        ctrl.addWidget(self._lbl("Select books (empty = all in genre):"))
        self.book_selector = QListWidget()
        self.book_selector.setSelectionMode(QListWidget.MultiSelection)
        self.book_selector.setMaximumHeight(100)
        ctrl.addWidget(self.book_selector)

        # Render options
        ctrl.addWidget(self._h2("Node Visibility"))
        self.cb_sections = QCheckBox("Sections (branches)")
        self.cb_sections.setChecked(self.visualizer.show_sections)
        self.cb_chunks = QCheckBox("Chunks (leaves)")
        self.cb_chunks.setChecked(self.visualizer.show_chunks)
        self.cb_entities = QCheckBox("Entities / Topics")
        self.cb_entities.setChecked(self.visualizer.show_entities)
        for cb in (self.cb_sections, self.cb_chunks, self.cb_entities):
            ctrl.addWidget(cb)

        ctrl.addWidget(self._h2("Edge Visibility"))
        self.cb_contains = QCheckBox("CONTAINS (structure)")
        self.cb_contains.setChecked(False)
        self.cb_similar = QCheckBox("SIMILAR_TO (semantic)")
        self.cb_similar.setChecked(self.visualizer.show_similar)
        self.cb_next = QCheckBox("NEXT (sequence)")
        self.cb_next.setChecked(self.visualizer.show_next)
        for cb in (self.cb_contains, self.cb_similar, self.cb_next):
            ctrl.addWidget(cb)

        # Stats label
        ctrl.addWidget(self._h2("Corpus Stats"))
        self.stats_label = QLabel(self._stats_text())
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet(
            "background:#0d1b2a; color:#90EE90; padding:5px; border-radius:3px;"
        )
        ctrl.addWidget(self.stats_label)

        # Action buttons
        ctrl.addStretch()
        self.render_btn = QPushButton("Render Forest")
        self.render_btn.setMinimumHeight(44)
        self.render_btn.setStyleSheet(
            "QPushButton { font-size: 15px; font-weight: bold; background-color: #2E8B57; }"
        )
        ctrl.addWidget(self.render_btn)

        btn_row = QHBoxLayout()
        self.show_text_btn = QPushButton("Show Text")
        self.save_btn = QPushButton("Save View")
        btn_row.addWidget(self.show_text_btn)
        btn_row.addWidget(self.save_btn)
        ctrl.addLayout(btn_row)

        widget = QWidget()
        widget.setLayout(ctrl)
        widget.setFixedWidth(CONTROL_PANEL_WIDTH)
        return widget

    def _build_viewport_panel(self) -> QWidget:
        vis = QVBoxLayout()
        vis.setSpacing(8)
        vis.setContentsMargins(8, 8, 8, 8)
        vis.addWidget(self.vtk_plotter, stretch=1)

        btn_row = QHBoxLayout()
        self.reset_view_btn = QPushButton("Reset View")
        self.reset_view_btn.setObjectName("reset-view")
        self.reset_view_btn.setFixedWidth(BUTTON_WIDTH)
        self.reset_settings_btn = QPushButton("Reset Settings")
        self.reset_settings_btn.setObjectName("reset-all")
        self.reset_settings_btn.setFixedWidth(BUTTON_WIDTH)
        self.status_display = QLabel("Ready")
        self.status_display.setStyleSheet(
            "font-weight:bold; font-size:13px; background:#0d1b2a; color:#90EE90; padding:3px;"
        )
        btn_row.addWidget(self.reset_view_btn)
        btn_row.addWidget(self.reset_settings_btn)
        btn_row.addWidget(self.status_display, stretch=1)
        vis.addLayout(btn_row)

        widget = QWidget()
        widget.setLayout(vis)
        return widget

    def _stats_text(self) -> str:
        v = self.visualizer
        return (
            f"Genres: {v.num_genres}\n"
            f"Books (with KG): {v.num_books}\n"
            f"Nodes loaded: {len(v.all_nodes):,}\n"
            f"Edges loaded: {len(v.all_edges):,}"
        )

    # -- Signals / slots -----------------------------------------------------

    def _setup_mesh_picking(self) -> None:
        self.vtk_plotter.enable_mesh_picking(
            callback=self.on_pick,
            show=False,
            show_actors=False,
            show_message=False,
            font_size=14,
            left_clicking=False,
            use_actor=True,
            through=True,
        )
        if hasattr(self.vtk_plotter, "picker"):
            self.vtk_plotter.picker.SetTolerance(0.005)
            self.vtk_plotter.picker.SetPickFromList(0)

    def _connect_signals(self) -> None:
        self.corpus_input.editingFinished.connect(self._on_corpus_path_edited)
        self.genre_selector.itemSelectionChanged.connect(self._on_genre_selection_changed)
        self.book_selector.itemSelectionChanged.connect(self._on_book_selection_changed)

        self.cb_sections.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_sections", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_chunks.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_chunks", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_entities.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_entities", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_contains.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_contains", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_similar.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_similar", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_next.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_next", s == Qt.Checked)  # type: ignore[attr-defined]
        )

        self.render_btn.clicked.connect(self.on_render_clicked)
        self.show_text_btn.clicked.connect(self.show_selected_text)
        self.save_btn.clicked.connect(self.save_current_view)
        self.reset_view_btn.clicked.connect(self.reset_camera)
        self.reset_settings_btn.clicked.connect(self.reset_settings)

        self.status_changed.connect(self.update_status_display)
        self.visualizer.param.watch(self.on_status_change, "status")
        self.visualizer.param.watch(self.update_window_title, "window_title")
        self.visualizer.param.watch(
            lambda _: self.stats_label.setText(self._stats_text()), "status"
        )
        self.visualizer.param.watch(self._on_genres_loaded, "available_genres")
        self.visualizer.param.watch(self._on_books_updated, "available_books")

    # -- Corpus / genre / book updates ---------------------------------------

    def _on_corpus_path_edited(self) -> None:
        self.visualizer.corpus_root = self.corpus_input.text().strip()

    def _on_genre_selection_changed(self) -> None:
        self.visualizer.selected_genres = [
            item.text() for item in self.genre_selector.selectedItems()
        ]

    def _on_book_selection_changed(self) -> None:
        self.visualizer.selected_books = [
            item.text() for item in self.book_selector.selectedItems()
        ]

    def _on_genres_loaded(self, event: param.Event) -> None:
        self.genre_selector.clear()
        for g in event.new:
            self.genre_selector.addItem(g)

    def _on_books_updated(self, event: param.Event) -> None:
        self.book_selector.clear()
        for b in event.new:
            self.book_selector.addItem(b)

    # -- Render / pick -------------------------------------------------------

    def on_render_clicked(self) -> None:
        self.visualizer.visualize()

    def on_pick(self, actor) -> None:
        """Right-click callback: find nearest node and show text popup."""
        if not self.visualizer.plotter:
            return
        self._clear_highlight()
        if self._current_popup and self._current_popup.isVisible():
            self._current_popup.close()
            self._current_popup = None
        if actor is None:
            self.update_status_display("Right-click a node sphere or trunk to inspect.")
            return
        if not hasattr(self.vtk_plotter, "picked_point") or self.vtk_plotter.picked_point is None:
            self.update_status_display("No pick point — zoom in and right-click closer to a node.")
            return

        picked_point = np.asarray(self.vtk_plotter.picked_point, float)

        # Identify actor name and map to a node kind
        picked_kind: str | None = None
        for name, act in self.plotter.actors.items():
            if act != actor:
                continue
            if name == "trunks":
                # Trunk click → find nearest document node (shows book info)
                picked_kind = "document"
            else:
                for kind in KIND_SIZE:
                    if name == f"{kind}_nodes":
                        picked_kind = kind
                        break
            break

        if picked_kind is None:
            self.update_status_display("Click on a node sphere or trunk cylinder.")
            return

        # Find closest node of that kind
        best_id, best_dist = None, float("inf")
        for mesh_id, elem in self.visualizer.actor_to_node.items():
            if elem["kind"] != picked_kind:
                continue
            d = float(np.linalg.norm(np.asarray(elem["position"], float) - picked_point))
            if d < best_dist:
                best_dist = d
                best_id = mesh_id

        if best_id is None:
            self.update_status_display(f"No {picked_kind} node near pick point.")
            return

        elem = self.visualizer.actor_to_node[best_id]
        # Build highlight mesh at the picked node position (no per-node mesh stored)
        pos = np.asarray(elem["position"], float)
        highlight = _make_node_mesh(elem["kind"], pos, KIND_SIZE[elem["kind"]] * 1.5, "high")
        self._highlight_mesh(highlight)

        kind_label = elem["kind"].capitalize()
        raw_name = elem["name"]
        title = f"{kind_label}: {raw_name}"
        text = elem.get("docstring") or f"**{raw_name}**\n\n_{kind_label} node._"
        self._current_popup = TextPopup(title, text, self, on_close_callback=self._on_popup_close)
        self._current_popup.show()
        self.update_status_display(f"Picked: {title} (dist {best_dist:.1f})")

    def _highlight_mesh(self, mesh) -> None:
        self._clear_highlight()
        self.plotter.add_mesh(
            mesh,
            color="white",
            show_edges=True,
            edge_color="yellow",
            line_width=3,
            pickable=False,
            show_scalar_bar=False,
            reset_camera=False,
            name="_forest_highlight",
        )
        self._current_picked_actor = self.plotter.actors.get("_forest_highlight")

    def _clear_highlight(self) -> None:
        if self._current_picked_actor:
            try:
                self.plotter.remove_actor(self._current_picked_actor, reset_camera=False)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            self._current_picked_actor = None

    def _on_popup_close(self) -> None:
        self._clear_highlight()
        self.plotter.render()

    def show_selected_text(self) -> None:
        """Show text for the first selected book in the book selector."""
        items = self.book_selector.selectedItems()
        if not items:
            self.update_status_display("Select a book first.")
            return
        book_title = items[0].text()
        self._current_popup = TextPopup(
            book_title,
            f"**{book_title}**\n\nSelect a node in the scene to view its text.",
            self,
            on_close_callback=self._on_popup_close,
        )
        self._current_popup.show()

    # -- Camera --------------------------------------------------------------

    def reset_camera(self) -> None:
        if not self.plotter:
            return
        self.plotter.reset_camera()  # type: ignore[call-arg]
        self.plotter.view_isometric()  # type: ignore[call-arg]
        self.plotter.render()
        self.plotter.camera.zoom(2)

    # -- Save ----------------------------------------------------------------

    def save_current_view(self) -> None:
        save_path = Path(self.visualizer.save_path)
        fmt = self.visualizer.save_format
        if save_path.suffix.lstrip(".") != fmt:
            save_path = save_path.with_suffix(f".{fmt}")
        self.visualizer.status = f"Saving → {save_path}…"
        QApplication.processEvents()
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "html":
                self.plotter.export_html(str(save_path))
            else:
                self.plotter.screenshot(str(save_path))
            self.visualizer.status = f"Saved → {save_path}"
        except (OSError, RuntimeError, ImportError) as exc:
            self.visualizer.status = f"Error saving: {exc}"

    # -- Reset ---------------------------------------------------------------

    def reset_settings(self) -> None:
        self.genre_selector.clearSelection()
        self.book_selector.clearSelection()
        self.cb_sections.setChecked(True)
        self.cb_chunks.setChecked(True)
        self.cb_entities.setChecked(False)
        self.cb_contains.setChecked(True)
        self.cb_similar.setChecked(False)
        self.cb_next.setChecked(False)
        self.reset_camera()
        self.visualizer.status = "Ready"

    # -- Status --------------------------------------------------------------

    def on_status_change(self, event: param.Event) -> None:
        self.status_changed.emit(event.new)
        QApplication.processEvents()

    def update_status_display(self, status: str) -> None:
        if status.startswith("Error"):
            html = f"<span style='color:#FF6B6B;font-size:13px;'><b>{status}</b></span>"
        elif any(kw in status for kw in ("Rendering", "Loading", "Building", "Drawing")):
            html = f"<span style='color:#87CEEB;font-size:13px;'><b>⏳ {status}</b></span>"
        elif any(kw in status for kw in ("rendered", "Saved", "Loaded", "Corpus")):
            html = f"<span style='color:#90EE90;font-size:13px;'><b>✓ {status}</b></span>"
        else:
            html = f"<span style='color:#c0c0c0;font-size:13px;'>{status}</span>"
        self.status_display.setText(html)

    def update_window_title(self, event: param.Event) -> None:
        self.setWindowTitle(event.new)

    # -- Cleanup -------------------------------------------------------------

    def cleanup(self) -> None:
        if self._current_popup and hasattr(self._current_popup, "isVisible"):
            try:
                self._current_popup.close()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        if self.plotter:
            try:
                self.plotter.clear_actors()
                self.plotter.close()
                self.visualizer.plotter = None
                self.plotter = None
                self.vtk_plotter = None
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        gc.collect()

    def closeEvent(self, event) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self.cleanup()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        event.accept()


# ---------------------------------------------------------------------------
# launch() — entry point
# ---------------------------------------------------------------------------


def launch(
    corpus_root: str = DEFAULT_CORPUS,
    width: int = 1500,
    height: int = 950,
    **_kwargs,
) -> None:
    """
    Open the Gutenberg KG Forest window and run the Qt event loop.

    :param corpus_root: Path to the corpus directory (``corpus/`` by default).
    :param width: Initial window width in pixels.
    :param height: Initial window height in pixels.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("gutenberg-kg-forest")

    win = ForestMainWindow(
        corpus_root=corpus_root,
        save_path=str(Path(corpus_root).parent / DEFAULT_SAVE),
        width=width,
        height=height,
    )
    win.show()
    sys.exit(app.exec())


atexit.register(gc.collect)
