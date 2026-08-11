"""
scene.py — Qt-free scene builder for the GutenbergKG 3-D knowledge tree forest.

Everything here composes a forest into a plain ``pv.Plotter``: corpus scanning,
the schematic :class:`ForestLayout`, glyph/edge geometry, and
:func:`build_forest_scene`.  No PyQt, no ``QApplication.processEvents`` — the
interactive viewer (:mod:`gutenberg_kg.viz3d`) is one caller of this module and
the off-screen light-field renderer (``gutenkg quilt``) is another.

Progress reporting is a plain ``Callable[[str], None]`` so a Qt caller can pump
its event loop and a headless caller can print or ignore.

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyvista as pv
from pycode_kg.layout3d import Layout3D, LayoutEdge, LayoutNode, fibonacci_annulus, fibonacci_sphere

from gutenberg_kg.layout_organic import Skeleton, grow_tree, leaf_glyphs, seed_from_slug, tree_mesh

logger = logging.getLogger(__name__)

__author__ = "Eric G. Suchanek, PhD"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CORPUS = "corpus"

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

# Background gradient — night forest sky
SKY_BOTTOM = "#1a1a2e"
SKY_TOP = "#16213e"
GROUND_COLOR = "#2d4a1e"

# LOD thresholds (total visible nodes)
LOD_HIGH: int = 3000
LOD_LOW: int = 8000

# Cap on rendered edges per relation
MAX_EDGES: int = 4000


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


# ---------------------------------------------------------------------------
# Crown orientation helpers
# ---------------------------------------------------------------------------


def _unit(v: np.ndarray) -> np.ndarray:
    """Unit vector, falling back to +Z for a degenerate input."""
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else np.array([0.0, 0.0, 1.0])


def _leaf_facing(outward: np.ndarray, up_bias: float = 0.6) -> np.ndarray:
    """
    Direction a limb's foliage cluster should face.

    Foliage runs out along the branch and then reaches for light, so the
    cluster axis is the limb's outward direction tilted upward — not world +Z.
    A cluster that always points straight up is the single clearest tell that
    a tree was assembled rather than grown, and it is far more obvious in
    parallax on a light-field panel than in a flat projection.

    :param outward: Vector from the trunk axis to the branch tip.
    :param up_bias: How strongly foliage reaches upward relative to running
        outward; 0 follows the limb exactly, large values return to vertical.
    :return: Unit facing vector.
    """
    horizontal = np.asarray(outward, dtype=float).copy()
    horizontal[2] = 0.0
    if float(np.linalg.norm(horizontal)) < 1e-9:
        return np.array([0.0, 0.0, 1.0])
    return _unit(_unit(horizontal) + np.array([0.0, 0.0, up_bias]))


def _nearest_neighbour_gap(points: np.ndarray) -> np.ndarray:
    """
    Distance from each point to its closest neighbour in the set.

    Used to size foliage clusters to the room a limb actually has, rather than
    to a fixed fraction of the crown.

    :param points: ``(N, 3)`` positions.
    :return: ``(N,)`` nearest-neighbour distances; all ones for a single point.
    """
    pts = np.atleast_2d(np.asarray(points, dtype=float))
    if pts.shape[0] < 2:
        return np.ones(pts.shape[0])
    dist = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
    np.fill_diagonal(dist, np.inf)
    return dist.min(axis=1)


def _crown_halo(
    n_points: int,
    crown: np.ndarray,
    *,
    seed: int = 0,
    inner: float = 0.75,
    outer: float = 1.45,
) -> np.ndarray:
    """
    Scatter points through a thick ellipsoidal shell around a crown.

    Entities belong to the whole book, not to any one branch, so at tree scale
    they read best drifting around the canopy — fireflies — rather than as the
    tight ball the schematic layout parks above the trunk.  The shell follows
    the crown's own proportions, so a columnar diary gets a tall halo and a
    spreading novel a broad one.

    The radial distribution is uniform *by volume* (cube-rooted), not by
    radius: a shell thin enough to place every point at nearly the same
    distance is exactly how a few thousand entities turn into an opaque egg
    around the tree.

    :param n_points: Number of positions to place.
    :param crown: ``(M, 3)`` crown points the halo should enclose.
    :param seed: RNG seed, for a reproducible scatter.
    :param inner: Inner shell radius as a multiple of the crown's half-extent;
        below 1 some spores drift down among the branches.
    :param outer: Outer shell radius, same units.
    :return: ``(n_points, 3)`` positions.
    """
    pts = np.atleast_2d(np.asarray(crown, dtype=float))
    centre = (pts.max(axis=0) + pts.min(axis=0)) / 2.0
    half = np.maximum((pts.max(axis=0) - pts.min(axis=0)) / 2.0, 1e-6)

    rng = np.random.default_rng(seed)
    unit = np.asarray(fibonacci_sphere(n_points, radius=1.0, center=np.zeros(3)), dtype=float)
    volume_uniform = rng.uniform(inner**3, outer**3, (n_points, 1)) ** (1.0 / 3.0)
    return centre + unit * half * volume_uniform


def _oriented_cluster(
    n_points: int, center: np.ndarray, facing: np.ndarray, radius: float
) -> list[np.ndarray]:
    """
    A hemispherical cluster of *n_points* around *center*, opening along *facing*.

    Points on the far side are reflected across the facing plane rather than
    discarded, so a cluster of any size fills the hemisphere evenly.

    :param n_points: Number of positions to return.
    :param center: Cluster centre (the branch tip).
    :param facing: Unit direction the cluster opens toward.
    :param radius: Cluster radius in scene units.
    :return: List of ``(3,)`` positions.
    """
    raw = np.asarray(fibonacci_sphere(n_points, radius=radius, center=center), dtype=float)
    relative = raw - center
    behind = np.minimum(relative @ facing, 0.0)
    return list(center + relative - 2.0 * behind[:, None] * facing)


# ---------------------------------------------------------------------------
# ForestLayout — books as trees, genres as groves
# ---------------------------------------------------------------------------


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
    :param book_genre_map: ``{book_slug: genre}``; books not listed fall into
        the ``"unknown"`` grove.
    :param entry_times: ``{document id: ISO timestamp}`` from
        :func:`load_entry_times`, which turns an entry-structured book's limbs
        into calendar years.
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
        book_genre_map: dict[str, str] | None = None,
        entry_times: dict[str, str] | None = None,
    ) -> None:
        """Store layout radii/scale parameters; see class docstring for their roles."""
        self.grove_inner_radius = grove_inner_radius
        self.grove_outer_radius = grove_outer_radius
        self.book_inner_radius = book_inner_radius
        self.book_outer_radius = book_outer_radius
        self.trunk_scale = trunk_scale
        self.max_trunk_height = max_trunk_height
        self.branch_radius = branch_radius
        self.leaf_radius = leaf_radius
        self.canopy_lift = canopy_lift
        self._book_genre_map: dict[str, str] = book_genre_map or {}
        self.entry_times: dict[str, str] = entry_times or {}

        # Set during compute() so render helpers can read them
        self.trunk_positions: dict[str, np.ndarray] = {}  # doc_node_id → XYZ base
        self.trunk_heights: dict[str, float] = {}  # doc_node_id → height
        self.trunk_genres: dict[str, str] = {}  # doc_node_id → genre
        self.genre_color_map: dict[str, str] = {}  # genre → hex color
        # (trunk_axis_pt, section_tip_pt) for every section — drawn as branch lines
        self.branch_lines: list[tuple[np.ndarray, np.ndarray]] = []
        # book slug → ordered section positions, for the organic layout
        self.book_sections: dict[str, list[np.ndarray]] = {}
        # book slug → chunk positions (crown attractors for the organic layout)
        self.book_chunks: dict[str, list[np.ndarray]] = {}
        # book slug → (base XYZ, trunk height)
        self.book_trunks: dict[str, tuple[np.ndarray, float]] = {}
        # ``document`` node IDs promoted to branch stations (DiaryKG books)
        self.branch_documents: set[str] = set()
        # book slug → [(period label, entry count)] for entry-structured books
        self.book_periods: dict[str, list[tuple[str, int]]] = {}

    def _period_groups(self, branch_nodes: list[LayoutNode]) -> list[tuple[str, list[LayoutNode]]]:
        """
        Split entry documents into the chronological periods that become limbs.

        Uses real dates when :attr:`entry_times` covers the entries — one limb
        per calendar year, which is what a reader means by "the 1665 branch".
        Without dates it falls back to equal runs of the file order, which for
        a diary is still chronological, just unlabelled.

        :param branch_nodes: Entry documents, in file order.
        :return: ``[(label, members)]`` ordered earliest first.
        """
        dated = [(self.entry_times.get(n.id), n) for n in branch_nodes]
        if all(ts for ts, _ in dated):
            by_year: dict[str, list[LayoutNode]] = defaultdict(list)
            for ts, node in dated:
                by_year[str(ts)[:4]].append(node)
            if len(by_year) >= 2:
                return sorted(by_year.items())

        n = len(branch_nodes)
        n_limbs = max(3, int(round(np.sqrt(n) / 2.0)))
        runs: dict[int, list[LayoutNode]] = defaultdict(list)
        for i, node in enumerate(branch_nodes):
            runs[min(i * n_limbs // n, n_limbs - 1)].append(node)
        return [(f"part {k + 1}", v) for k, v in sorted(runs.items())]

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
        self.book_sections = {}
        self.book_chunks = {}
        self.book_trunks = {}
        self.branch_documents = set()

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

        # Group books by genre; books the caller did not map fall into "unknown"
        book_genre_map = self._book_genre_map

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
                self.book_trunks[slug] = (np.array([bx, by, 0.0]), float(trunk_height))

                doc_nodes = [n for n in book_nodes if n.kind == "document"]
                section_nodes = [n for n in book_nodes if n.kind == "section"]

                # A DiaryKG graph has no sections and one ``document`` per dated
                # entry, so the entries are what branch: the book gets a single
                # synthetic trunk instead of one trunk per document stacked at
                # the same XY, and the entry documents take the branch stations.
                entry_structured = not section_nodes and len(doc_nodes) > 1
                branch_nodes = doc_nodes if entry_structured else section_nodes

                if entry_structured:
                    trunk_id = f"{slug}:__trunk__"
                    self.trunk_positions[trunk_id] = np.array([bx, by, 0.0])
                    self.trunk_heights[trunk_id] = trunk_height
                    self.trunk_genres[trunk_id] = genre
                    self.branch_documents.update(n.id for n in doc_nodes)
                else:
                    # Document nodes mark the trunk base
                    for doc in doc_nodes:
                        positions[doc.id] = np.array([bx, by, 0.0])
                        self.trunk_positions[doc.id] = np.array([bx, by, 0.0])
                        self.trunk_heights[doc.id] = trunk_height
                        self.trunk_genres[doc.id] = genre

                # Branch nodes — spiral up the trunk (B: real tree branching)
                n_branches = len(branch_nodes)
                golden_angle = np.pi * (3.0 - np.sqrt(5.0))  # ≈ 137.5°
                branch_length = 0.0  # reused by canopy cloud below
                if n_branches and entry_structured:
                    # A diary has no chapters — just thousands of dated entries
                    # hanging off one trunk, which grows a lollipop however the
                    # crown volume is shaped.  Its real hierarchy is time, so the
                    # limbs are periods: trunk → period limb → entry cluster →
                    # chunk leaves.  Each limb is a span of the diarist's life,
                    # and because the pipe model sizes a limb by what it carries,
                    # a prolific year grows visibly heavier wood than a quiet one.
                    groups = self._period_groups(branch_nodes)
                    n_limbs = len(groups)
                    branch_length = self.branch_radius + np.sqrt(n_limbs) * 0.5
                    mean_members = n_branches / n_limbs

                    limb_z = [
                        trunk_height * (0.35 + 0.60 * limb / max(n_limbs - 1, 1))
                        for limb in range(n_limbs)
                    ]
                    limb_tips = np.array(
                        [
                            [
                                bx
                                + branch_length
                                * (1.0 - (z / trunk_height) * 0.35)
                                * np.cos(limb * golden_angle),
                                by
                                + branch_length
                                * (1.0 - (z / trunk_height) * 0.35)
                                * np.sin(limb * golden_angle),
                                z,
                            ]
                            for limb, z in enumerate(limb_z)
                        ]
                    )
                    # Size clusters to the room each limb actually has.  A fixed
                    # fraction of the crown radius works for ten limbs and fails
                    # for thirty: consecutive years end up closer together than
                    # their clusters are wide, so the foliage interpenetrates and
                    # leaves take their orientation from a neighbouring limb.
                    room = _nearest_neighbour_gap(limb_tips)

                    for limb, (label, members) in enumerate(groups):
                        tip = limb_tips[limb]
                        z = float(tip[2])
                        self.branch_lines.append((np.array([bx, by, z]), tip))
                        self.book_periods.setdefault(slug, []).append((label, len(members)))
                        # Within that room, a busy year still fills more of it.
                        weight = min(np.sqrt(len(members) / mean_members), 1.6)
                        cluster_r = min(0.45 * room[limb] * weight, branch_length * 0.4 * weight)
                        spread = _oriented_cluster(
                            len(members),
                            tip,
                            _leaf_facing(tip - np.array([bx, by, z])),
                            cluster_r,
                        )
                        for sec, pos in zip(members, spread):
                            positions[sec.id] = pos
                    self.book_sections[slug] = [positions[s.id] for s in branch_nodes]

                elif n_branches:
                    branch_length = self.branch_radius + np.sqrt(n_branches) * 0.5
                    for i, sec in enumerate(branch_nodes):
                        t = i / max(n_branches - 1, 1)
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
                    self.book_sections[slug] = [positions[s.id] for s in branch_nodes]

                # Chunk nodes — upper-hemisphere cone above each branch tip
                sec_chunks: dict[str, list[str]] = {
                    n.id: children.get(n.id, []) for n in branch_nodes
                }
                book_chunk_pts: list[np.ndarray] = []
                for sec in branch_nodes:
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
                    # The cluster faces the way its limb points, not straight up:
                    # a hemisphere filtered on world +Z gives every sub-canopy the
                    # same vertical dome no matter which way its branch runs, which
                    # is the giveaway that reads as wrong in parallax.
                    facing = _leaf_facing(sec_pos - np.array([bx, by, float(sec_pos[2])]))
                    for cid, cpos in zip(
                        chunk_ids, _oriented_cluster(n_c, sec_pos, facing, leaf_r)
                    ):
                        positions[cid] = cpos
                        book_chunk_pts.append(cpos)

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
                        book_chunk_pts.append(positions[cid])

                if book_chunk_pts:
                    self.book_chunks[slug] = book_chunk_pts

                # Entity / topic / keyword → loose cloud above canopy
                canopy_z = trunk_height + self.canopy_lift
                canopy_center = np.array([bx, by, canopy_z])
                floaters = [
                    n
                    for n in book_nodes
                    if n.kind in ("entity", "topic", "keyword") and n.id not in positions
                ]
                if floaters:
                    cloud_r = branch_length * 1.1 if n_branches else self.branch_radius
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


def arc_points(p1: np.ndarray, p2: np.ndarray, n_pts: int = 24, lift: float = 0.35) -> np.ndarray:
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


def make_node_mesh(kind: str, center: np.ndarray, size: float, lod: str) -> pv.DataSet:
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


def glyph_proto(kind: str, size: float, lod: str) -> pv.PolyData:
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


# ---------------------------------------------------------------------------
# Scene description
# ---------------------------------------------------------------------------


@dataclass
class SceneFilters:
    """Which node kinds and edge relations the scene should draw.

    :param show_sections: Draw ``section`` (branch) nodes.
    :param show_chunks: Draw ``chunk`` (leaf) nodes.
    :param show_entities: Draw ``entity`` / ``topic`` / ``keyword`` nodes.
    :param show_contains: Draw ``CONTAINS`` structural edges.
    :param show_similar: Draw ``SIMILAR_TO`` semantic arcs.
    :param show_next: Draw ``NEXT`` sequential arcs.
    """

    show_sections: bool = True
    show_chunks: bool = True
    show_entities: bool = False
    show_contains: bool = False
    show_similar: bool = False
    show_next: bool = False

    def visible_kinds(self) -> set[str]:
        """Node kinds this filter set admits (``document`` is always drawn)."""
        kinds: set[str] = {"document"}
        if self.show_sections:
            kinds.add("section")
        if self.show_chunks:
            kinds.add("chunk")
        if self.show_entities:
            kinds.update(("entity", "topic", "keyword"))
        return kinds

    def visible_rels(self) -> set[str]:
        """Edge relations this filter set admits."""
        rels: set[str] = set()
        if self.show_contains:
            rels.add("CONTAINS")
        if self.show_similar:
            rels.add("SIMILAR_TO")
        if self.show_next:
            rels.add("NEXT")
        return rels


@dataclass
class SceneInfo:
    """What a built scene contains, for callers that need to interrogate it.

    :param title: One-line stats banner (window title / CLI report).
    :param actor_to_node: ``{"<kind>_<index>": node metadata}`` for picking.
    :param positions: Node ID → ``[x, y, z]``.
    :param layout: The :class:`ForestLayout` that produced *positions*.
    :param lod: LOD tier actually used — ``"high"``, ``"low"``, ``"points"``.
    :param counts: Rendered node count per kind.
    :param n_books: Number of distinct book slugs in the scene.
    :param skeleton: Grown tree skeleton, set only by :func:`build_tree_scene`.
    :param trunk_height: Schematic trunk height of the hero tree, in scene
        units — a useful focal-plane height for framing.
    """

    title: str
    actor_to_node: dict[str, dict] = field(default_factory=dict)
    positions: dict[str, np.ndarray] = field(default_factory=dict)
    layout: ForestLayout | None = None
    lod: str = "high"
    counts: Counter = field(default_factory=Counter)
    n_books: int = 0
    skeleton: Skeleton | None = None
    trunk_height: float = 0.0


def build_forest_scene(
    nodes: list[LayoutNode],
    edges: list[LayoutEdge],
    plotter: pv.Plotter,
    *,
    book_genre_map: dict[str, str] | None = None,
    entry_times: dict[str, str] | None = None,
    layout: ForestLayout | None = None,
    filters: SceneFilters | None = None,
    lod: str | None = None,
    ground_size: float = 1000.0,
    frame_camera: bool = True,
    progress: Callable[[str], None] | None = None,
) -> SceneInfo:
    """
    Compose the knowledge tree forest into *plotter*.

    Draws the forest floor, per-book trunk cylinders, branch lines, node
    glyphs (LOD-aware, one draw call per kind), and the selected structural
    edges.  Positions come from *layout*, computed over **all** *nodes* so the
    geometry is stable regardless of which kinds *filters* admits.

    :param nodes: All loaded nodes (IDs namespaced by book slug).
    :param edges: All loaded edges.
    :param plotter: Any ``pv.Plotter`` — interactive ``QtInteractor`` or
        ``pv.Plotter(off_screen=True)``.
    :param book_genre_map: ``{book_slug: genre}`` for grove placement.
    :param entry_times: ``{document id: ISO timestamp}`` from
        :func:`load_entry_times`, merged across books.
    :param layout: Layout instance to reuse; a default
        :class:`ForestLayout` is built when omitted.
    :param filters: Node/edge visibility; defaults to sections + chunks.
    :param lod: Force an LOD tier; derived from visible node count when
        omitted.
    :param ground_size: Edge length of the ground plane in scene units;
        ``0`` omits the ground entirely (the light-field path wants this —
        an effectively infinite plane guarantees off-budget disparity at the
        horizon).
    :param frame_camera: Reset the camera to the isometric framing the
        interactive viewer expects.  Pass ``False`` when the caller frames
        the shot itself, as the quilt renderer does.
    :param progress: Optional ``fn(message)`` progress callback.
    :return: A :class:`SceneInfo` describing what was drawn.
    """
    filters = filters or SceneFilters()
    report = progress or (lambda _msg: None)

    report("Building forest scene...")
    plotter.clear_actors()
    plotter.enable_anti_aliasing("msaa")
    plotter.set_background(SKY_BOTTOM, top=SKY_TOP)  # ty: ignore[invalid-argument-type]

    if ground_size > 0:
        ground = pv.Plane(
            center=(0, 0, -0.2), direction=(0, 0, 1), i_size=ground_size, j_size=ground_size
        )
        plotter.add_mesh(ground, color=GROUND_COLOR, opacity=1.0, name="ground")

    # -- Compute layout over the full node set
    if layout is None:
        layout = ForestLayout(book_genre_map=book_genre_map, entry_times=entry_times)
    else:
        if book_genre_map is not None:
            layout._book_genre_map = book_genre_map
        if entry_times is not None:
            layout.entry_times = entry_times
    all_positions = layout.compute(nodes, edges)

    # -- Draw trunk cylinders — single merged mesh with genre_idx scalar
    # One add_mesh call regardless of genre count keeps actor/texture count low.
    report("Drawing trunks...")
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

    # -- Visible node set and LOD tier
    # DiaryKG entry documents occupy branch stations, so they filter and draw
    # as sections rather than as one trunk marker per dated entry.
    promoted = layout.branch_documents

    def effective_kind(node: LayoutNode) -> str:
        return "section" if node.id in promoted else node.kind

    visible_kinds = filters.visible_kinds()
    visible = [n for n in nodes if effective_kind(n) in visible_kinds]
    n_visible = len(visible)
    if lod is None:
        lod = "high" if n_visible <= LOD_HIGH else "low" if n_visible <= LOD_LOW else "points"

    # -- Glyph rendering: O(kinds) Python work, not O(nodes)
    # Bucket positions and metadata by kind in one pass, then glyph each kind.
    kind_pts: dict[str, list[np.ndarray]] = {k: [] for k in KIND_SIZE}
    kind_meta: dict[str, list] = {k: [] for k in KIND_SIZE}
    node_id_set: set[str] = set()

    for node in visible:
        pos = all_positions.get(node.id)
        if pos is None:
            continue
        ekind = effective_kind(node)
        kind = ekind if ekind in KIND_SIZE else "chunk"
        kind_pts[kind].append(pos)
        kind_meta[kind].append(node)
        node_id_set.add(node.id)

    actor_to_node: dict[str, dict] = {}
    report("Rendering nodes...")

    for kind in KIND_SIZE:
        pts = kind_pts[kind]
        if not pts:
            continue
        arr = np.array(pts, dtype=float)
        cloud = pv.PolyData(arr)
        proto = glyph_proto(kind, KIND_SIZE[kind], lod)
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
    report("Rendering edges...")

    rel_to_show = filters.visible_rels()
    rel_blocks: dict[str, pv.MultiBlock] = {r: pv.MultiBlock() for r in rel_to_show}
    edge_counts: dict[str, int] = {r: 0 for r in rel_to_show}

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
            rel_blocks[edge.rel].append(pv.Spline(arc_points(p1, p2), n_points=24))
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
    counts = Counter(effective_kind(n) for n in visible)
    n_books = len({n.id.split(":")[0] for n in nodes})
    title = (
        f"Gutenberg KG Forest | {n_books} books | "
        f"docs={counts.get('document', 0)}  "
        f"sections={counts.get('section', 0)}  "
        f"chunks={counts.get('chunk', 0)}  "
        f"entities={counts.get('entity', 0)}"
    )

    if frame_camera:
        plotter.reset_camera()  # ty: ignore[missing-argument]
        plotter.view_isometric()  # ty: ignore[missing-argument]
        plotter.render()
        plotter.camera.zoom(2)

    report("Forest rendered.")
    return SceneInfo(
        title=title,
        actor_to_node=actor_to_node,
        positions=all_positions,
        layout=layout,
        lod=lod,
        counts=counts,
        n_books=n_books,
    )


# ---------------------------------------------------------------------------
# Organic hero tree — the light-field subject
# ---------------------------------------------------------------------------

#: Growth bias per genre.  Positive Z reaches for light (conifer-like), negative
#: droops (willow-like).  Genre already carries a colour; a silhouette doubles
#: what it says at forest distance.
GENRE_TROPISM: dict[str, tuple[float, float, float]] = {
    "poetry": (0.0, 0.0, -0.10),
    "philosophy": (0.0, 0.0, 0.30),
    "sacred-texts": (0.0, 0.0, 0.28),
    "diaries": (0.0, 0.0, 0.05),
    "letters": (0.0, 0.0, 0.05),
}
DEFAULT_TROPISM: tuple[float, float, float] = (0.0, 0.0, 0.18)

WOOD_COLOR = "#6B4A2E"

#: Chunk count at which leaves render at full size; denser crowns scale down.
LEAF_REFERENCE_COUNT: int = 600


@dataclass(frozen=True)
class Season:
    """A seasonal look for the foliage, wood, and sky.

    :param foliage: Leaf colours, sampled per leaf so a canopy varies the way
        a real one does rather than reading as one flat green.
    :param density: Fraction of chunks that keep a leaf.  Winter drops most of
        them, which is the point — bare wood is where the pipe model shows.
    :param wood: Branch colour.
    :param sky: Background gradient, ``(bottom, top)``.
    """

    foliage: tuple[str, ...]
    density: float = 1.0
    wood: str = WOOD_COLOR
    sky: tuple[str, str] = (SKY_BOTTOM, SKY_TOP)


#: Foliage seasons.  Summer is the default and matches the original palette.
SEASONS: dict[str, Season] = {
    "spring": Season(
        foliage=("#A8E063", "#7FD14B", "#C6F08A", "#F7C8DD", "#FFF3B0"),
        wood="#6B4A2E",
        sky=("#16213e", "#1f3a5f"),
    ),
    "summer": Season(
        foliage=("#90EE90", "#5FBF5F", "#77DD77", "#3E9B4F"),
    ),
    "autumn": Season(
        foliage=("#E8A33D", "#D95F30", "#B3341F", "#F0C75E", "#8C6A3F", "#6B8F3A"),
        wood="#5C3D24",
        sky=("#2a1a2e", "#3a2440"),
    ),
    "winter": Season(
        foliage=("#8C7A5E", "#A89880", "#D7E3EA"),
        density=0.10,
        wood="#7A6A58",
        sky=("#101725", "#1b2a3d"),
    ),
}
DEFAULT_SEASON = "summer"


def build_tree_scene(
    nodes: list[LayoutNode],
    edges: list[LayoutEdge],
    plotter: pv.Plotter,
    *,
    slug: str,
    genre: str = "unknown",
    entry_times: dict[str, str] | None = None,
    filters: SceneFilters | None = None,
    season: str = DEFAULT_SEASON,
    tip_radius: float = 0.05,
    leaf_size: float = 0.32,
    ground_size: float = 0.0,
    progress: Callable[[str], None] | None = None,
) -> SceneInfo:
    """
    Compose a single book as an organically grown tree.

    The schematic layout places the crown; space colonization then grows a
    skeleton *to reach it*, so every limb is a real structural path and the
    canopy's shape is the book's shape.  This is the Tier-1 light-field
    subject: one tree, standing at the origin, framed by the caller.

    :param nodes: Nodes of one book (IDs namespaced by *slug*).
    :param edges: Edges of the same book.
    :param plotter: Off-screen or interactive plotter.
    :param slug: Book slug; seeds growth so the tree is reproducible.
    :param genre: Genre name, which selects the tropism silhouette.
    :param entry_times: ``{document id: ISO timestamp}`` from
        :func:`load_entry_times`; grows a dated book's limbs as calendar years.
    :param filters: Only ``show_entities`` is consulted — the gold spores.
        Wood and leaves are the point of this scene.
    :param season: Key into :data:`SEASONS` — foliage palette, leaf density,
        wood tone, and sky.
    :param tip_radius: Radius of leaf-bearing twigs, in scene units.
    :param leaf_size: Leaf glyph radius.
    :param ground_size: Ground plane edge length; ``0`` (the default here)
        omits it, since an effectively infinite plane guarantees off-budget
        disparity at the horizon.
    :param progress: Optional ``fn(message)`` progress callback.
    :return: :class:`SceneInfo`, with ``layout`` set and the grown skeleton
        reachable through :attr:`SceneInfo.skeleton`.
    """
    filters = filters or SceneFilters()
    report = progress or (lambda _msg: None)
    if season not in SEASONS:
        raise ValueError(f"Unknown season {season!r}; choose from {', '.join(SEASONS)}")
    palette = SEASONS[season]

    report("Laying out crown...")
    plotter.clear_actors()
    plotter.enable_anti_aliasing("msaa")
    plotter.set_background(palette.sky[0], top=palette.sky[1])  # ty: ignore[invalid-argument-type]

    layout = ForestLayout(book_genre_map={slug: genre}, entry_times=entry_times)
    positions = layout.compute(nodes, edges)
    for label, count in layout.book_periods.get(slug, [])[:1]:
        report(f"{len(layout.book_periods[slug])} period limbs (first: {label}, {count} entries)")

    base, trunk_height = layout.book_trunks.get(slug, (np.zeros(3), 10.0))
    # Stand the tree at the origin: a hero shot frames one subject, and the
    # grove annulus would otherwise park it hundreds of units off-axis.
    shift = np.array([base[0], base[1], 0.0])
    positions = {nid: p - shift for nid, p in positions.items()}
    root = np.zeros(3)

    crown = np.asarray([positions[n.id] for n in nodes if n.kind == "chunk" and n.id in positions])
    if crown.size == 0:
        raise ValueError(f"{slug}: no chunk positions to grow toward")

    report(f"Growing skeleton toward {len(crown):,} chunks...")
    skeleton = grow_tree(
        crown,
        root,
        slug=slug,
        tip_radius=tip_radius,
        tropism=GENRE_TROPISM.get(genre, DEFAULT_TROPISM),
    )
    if skeleton.attractors_used < skeleton.attractors_total:
        report(
            f"Grew toward {skeleton.attractors_used:,} of {skeleton.attractors_total:,} "
            f"chunks (crown subsampled); every chunk still gets a leaf."
        )

    report(f"Sweeping {skeleton.n_nodes:,} skeleton nodes into wood...")
    wood = tree_mesh(skeleton)
    if wood.n_points:
        plotter.add_mesh(wood, color=palette.wood, smooth_shading=True, name="wood")

    report(f"Placing leaves ({season})...")
    # A fixed leaf size tiles a dense crown into an opaque shell that hides the
    # wood entirely.  Shrink with count so a 19,000-chunk diary reads as foliage
    # with branches visible through it, the way a canopy actually does.
    leaf_scale = min(1.0, (LEAF_REFERENCE_COUNT / max(len(crown), 1)) ** (1.0 / 3.0))
    leaf_rng = np.random.default_rng(seed_from_slug(f"{slug}:{season}"))
    kept = crown
    if palette.density < 1.0:
        n_kept = max(1, int(round(len(crown) * palette.density)))
        kept = crown[leaf_rng.choice(len(crown), size=n_kept, replace=False)]
    tint = leaf_rng.integers(0, len(palette.foliage), len(kept)).astype(float)
    leaves = leaf_glyphs(
        kept,
        skeleton,
        size=leaf_size * leaf_scale,
        tint=tint,
        seed=seed_from_slug(slug + ":leaves"),
    )
    if leaves.n_points:
        from matplotlib.colors import ListedColormap  # pyvista dependency, always present

        plotter.add_mesh(
            leaves,
            scalars="tint",
            cmap=ListedColormap(list(palette.foliage)),
            clim=[-0.5, len(palette.foliage) - 0.5],
            show_scalar_bar=False,
            name="leaves",
        )

    # Gold spores: small bright off-plane points, the best depth cue in the
    # scene and the hook for query illumination later.  The schematic layout
    # parks them in a tight ball above the canopy, which at tree scale reads as
    # a golf ball on a stick; here they surround the whole crown as a halo.
    if filters.show_entities:
        n_spores = sum(1 for n in nodes if n.kind in ("entity", "topic"))
        if n_spores:
            spore_pts = _crown_halo(n_spores, crown, seed=seed_from_slug(slug + ":spores"))
            spore_size = KIND_SIZE["entity"] * min(
                1.0, (LEAF_REFERENCE_COUNT / n_spores) ** (1.0 / 3.0)
            )
            spores = pv.PolyData(spore_pts).glyph(
                geom=pv.Tetrahedron(radius=spore_size), orient=False, scale=False
            )
            plotter.add_mesh(spores, color=KIND_COLOR["entity"], opacity=0.55, name="spores")

    if ground_size > 0:
        ground = pv.Plane(
            center=(0, 0, -0.2), direction=(0, 0, 1), i_size=ground_size, j_size=ground_size
        )
        plotter.add_mesh(ground, color=GROUND_COLOR, name="ground")

    counts = Counter(n.kind for n in nodes)
    trunk_r = float(skeleton.radii[0]) if skeleton.radii is not None else 0.0
    title = (
        f"{slug} | {genre} | chunks={counts.get('chunk', 0)}  "
        f"limbs={skeleton.n_nodes}  trunk r={trunk_r:.2f}"
    )
    report("Tree grown.")
    return SceneInfo(
        title=title,
        positions=positions,
        layout=layout,
        counts=counts,
        n_books=1,
        skeleton=skeleton,
        trunk_height=float(trunk_height),
    )
