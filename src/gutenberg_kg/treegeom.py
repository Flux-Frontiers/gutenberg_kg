"""
treegeom.py — where a book's tree goes, with nothing drawn yet.

The PyVista-free half of the scene layer.  Corpus geometry is pure NumPy: the
schematic :class:`ForestLayout` that places a crown, the space-colonization
growth that reaches it, the foliage seasons, and the halo scatter.  None of it
needs VTK, and hoisting it out of :mod:`gutenberg_kg.scene` is what lets a
second renderer exist — :mod:`gutenberg_kg.povscene` composes the same tree as
analytic POV-Ray primitives without a plotter, an OpenGL context, or an
installed PyVista.

:mod:`gutenberg_kg.scene` re-exports every public name here, so
``from gutenberg_kg.scene import ForestLayout`` keeps working; new code should
import from whichever module matches what it needs, geometry or rendering.

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from kg_utils.viz3d import (
    Layout3D,
    LayoutEdge,
    LayoutNode,
    Skeleton,
    fibonacci_annulus,
    fibonacci_sphere,
    grow_tree,
    leaf_facing,
    oriented_cluster,
    seed_from_key,
)

__author__ = "Eric G. Suchanek, PhD"

# ---------------------------------------------------------------------------
# Shared appearance constants
# ---------------------------------------------------------------------------

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
# Crown orientation helpers
#
# ``leaf_facing`` and ``oriented_cluster`` used to live here, duplicated
# verbatim in ``pycode_kg/scene3d.py``.  They are pure geometry with no book
# knowledge, so they belong in the engine; kgmodule-utils now owns them and
# both consumers import the one copy.  The promotion also fixed a latent crash
# in the version this module carried — see the note on ``oriented_cluster``
# below.
# ---------------------------------------------------------------------------


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
                        spread = oriented_cluster(
                            len(members),
                            tip,
                            leaf_facing(tip - np.array([bx, by, z])),
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
                    facing = leaf_facing(sec_pos - np.array([bx, by, float(sec_pos[2])]))
                    for cid, cpos in zip(chunk_ids, oriented_cluster(n_c, sec_pos, facing, leaf_r)):
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
# Scene description
# ---------------------------------------------------------------------------


@dataclass
class SceneFilters:
    """Which node kinds and edge relations the scene should draw.

    :param show_sections: Draw ``section`` (branch) nodes.
    :param show_chunks: Draw ``chunk`` (leaf) nodes.
    :param show_entities: Draw ``entity`` / ``keyword`` nodes — the gold spores.
    :param show_topics: Draw ``topic`` nodes — the blue pollen cloud.  Separate
        from *show_entities* because the two answer different questions: what
        the book names, versus what it is about.
    :param show_contains: Draw ``CONTAINS`` structural edges.
    :param show_similar: Draw ``SIMILAR_TO`` semantic arcs.
    :param show_next: Draw ``NEXT`` sequential arcs.
    """

    show_sections: bool = True
    show_chunks: bool = True
    show_entities: bool = False
    show_topics: bool = False
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
            kinds.update(("entity", "keyword"))
        if self.show_topics:
            kinds.add("topic")
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

#: Most spores drawn per halo.  A halo reads as a cloud rather than a count, so
#: past a couple of hundred glyphs more ink buys nothing and costs the tree.
#: Measured on Hamlet against a spore-free render: an uncapped halo leaves 38%
#: of the foliage legible, 350 leaves 64%, and 200 leaves ~68%.
SPORE_CAP: int = 200

#: Spore radius as a fraction of the (already density-scaled) leaf radius.
#: Below 1.0 so the halo always reads as finer than the foliage.
SPORE_LEAF_RATIO: float = 0.45

#: Spore alpha.  Not a free dial: below about 0.2 the spores stop being visible
#: while still veiling the crown, which is strictly worse than not drawing them
#: — so this stays high enough to earn the foliage it costs.  Depth peeling was
#: tried and changes nothing here; the cost is coverage, not draw order.
SPORE_OPACITY: float = 0.38


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


# ---------------------------------------------------------------------------
# Tree geometry — one placement, two renderers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TreeGeometry:
    """
    Where a book's wood, leaves and spores go, with nothing drawn yet.

    The placement half of :func:`build_tree_scene`, separated out so a second
    renderer can reach it.  Everything here is plain NumPy and hex colour
    strings: no ``pv.Plotter``, no meshes, no tessellation.  PyVista turns it
    into actors; :mod:`gutenberg_kg.povscene` turns the same numbers into
    POV-Ray primitives, and because both start here the two backends cannot
    quietly grow different trees.

    :param skeleton: Grown skeleton, radii already assigned.
    :param layout: The :class:`ForestLayout` that placed the crown.
    :param positions: Node ID → position, shifted so the tree stands at the
        origin.
    :param crown: ``(M, 3)`` chunk positions the skeleton grew toward.
    :param palette: The :class:`Season` in force.
    :param leaf_points: ``(L, 3)`` chunks that kept a leaf — the whole crown
        except in winter, which thins it.
    :param leaf_tint: ``(L,)`` index into ``palette.foliage``, one per leaf.
    :param leaf_radius: Leaf radius after density scaling, in scene units.
    :param spores: ``{kind: (points (S, 3), radius)}`` for the halo kinds
        actually enabled.
    :param title: One-line stats banner.
    :param counts: Node count per kind.
    :param trunk_height: Schematic trunk height, a useful focal-plane height.
    """

    skeleton: Skeleton
    layout: ForestLayout
    positions: dict[str, np.ndarray]
    crown: np.ndarray
    palette: Season
    leaf_points: np.ndarray
    leaf_tint: np.ndarray
    leaf_radius: float
    spores: dict[str, tuple[np.ndarray, float]]
    title: str
    counts: Counter
    trunk_height: float

    @property
    def leaf_colors(self) -> list[str]:
        """:return: One hex colour per leaf, resolved through the palette."""
        return [self.palette.foliage[int(i)] for i in self.leaf_tint]


def grow_tree_geometry(
    nodes: list[LayoutNode],
    edges: list[LayoutEdge],
    *,
    slug: str,
    genre: str = "unknown",
    entry_times: dict[str, str] | None = None,
    filters: SceneFilters | None = None,
    season: str = DEFAULT_SEASON,
    tip_radius: float = 0.05,
    leaf_size: float = 0.32,
    progress: Callable[[str], None] | None = None,
) -> TreeGeometry:
    """
    Lay out one book and grow a skeleton to reach it, without drawing anything.

    The schematic layout places the crown; space colonization then grows a
    skeleton *to reach it*, so every limb is a real structural path and the
    canopy's shape is the book's shape.

    :param nodes: Nodes of one book (IDs namespaced by *slug*).
    :param edges: Edges of the same book.
    :param slug: Book slug; seeds growth so the tree is reproducible.
    :param genre: Genre name, which selects the tropism silhouette.
    :param entry_times: ``{document id: ISO timestamp}`` from
        :func:`load_entry_times`; grows a dated book's limbs as calendar years.
    :param filters: Only ``show_entities`` and ``show_topics`` are consulted;
        they decide which spore halos are placed at all.
    :param season: Key into :data:`SEASONS`.
    :param tip_radius: Radius of leaf-bearing twigs, in scene units.
    :param leaf_size: Leaf radius before density scaling.
    :param progress: Optional ``fn(message)`` progress callback.
    :return: The placed :class:`TreeGeometry`.
    :raises ValueError: If *season* is unknown, or the book has no chunks to
        grow toward.
    """
    filters = filters or SceneFilters()
    report = progress or (lambda _msg: None)
    if season not in SEASONS:
        raise ValueError(f"Unknown season {season!r}; choose from {', '.join(SEASONS)}")
    palette = SEASONS[season]

    report("Laying out crown...")
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
        key=slug,
        tip_radius=tip_radius,
        tropism=GENRE_TROPISM.get(genre, DEFAULT_TROPISM),
    )
    if skeleton.attractors_used < skeleton.attractors_total:
        report(
            f"Grew toward {skeleton.attractors_used:,} of {skeleton.attractors_total:,} "
            f"chunks (crown subsampled); every chunk still gets a leaf."
        )

    # A fixed leaf size tiles a dense crown into an opaque shell that hides the
    # wood entirely.  Shrink with count so a 19,000-chunk diary reads as foliage
    # with branches visible through it, the way a canopy actually does.
    leaf_scale = min(1.0, (LEAF_REFERENCE_COUNT / max(len(crown), 1)) ** (1.0 / 3.0))
    leaf_rng = np.random.default_rng(seed_from_key(f"{slug}:{season}"))
    kept = crown
    if palette.density < 1.0:
        n_kept = max(1, int(round(len(crown) * palette.density)))
        kept = crown[leaf_rng.choice(len(crown), size=n_kept, replace=False)]
    tint = leaf_rng.integers(0, len(palette.foliage), len(kept)).astype(float)
    leaf_radius = leaf_size * leaf_scale

    # Spores: bright off-plane points, the best depth cue in the scene and the
    # hook for query illumination later.  The schematic layout parks them in a
    # tight ball above the canopy, which at tree scale reads as a golf ball on
    # a stick; here they surround the crown as a halo.
    #
    # Entities and topics get their own halo, since one gold cloud conflated
    # what a book *names* with what it is *about* and wasted the blue the topic
    # kind already carried.  Topics sit further out so the two stay separable.
    #
    # Both are capped at SPORE_CAP.  Drawing one glyph per node cannot work at
    # corpus scale — Pepys has 7,065 entities and 7,287 topics against 18,757
    # leaves, so the halo simply buries the tree it is meant to annotate.  A
    # halo reads as a cloud, not as a count, so a deterministic sample carries
    # the same meaning at a fraction of the ink.
    spores: dict[str, tuple[np.ndarray, float]] = {}
    for kind, enabled, spread in (
        ("entity", filters.show_entities, 1.0),
        ("topic", filters.show_topics, 1.3),
    ):
        if not enabled:
            continue
        n_spores = sum(1 for n in nodes if n.kind == kind)
        if not n_spores:
            continue
        n_drawn = min(n_spores, SPORE_CAP)
        spore_pts = _crown_halo(
            n_drawn, crown * spread, seed=seed_from_key(f"{slug}:{kind}-spores")
        )
        # Sized against the leaves rather than against their own count, so the
        # halo always reads as finer than the foliage it surrounds.
        spore_size = leaf_radius * SPORE_LEAF_RATIO * (KIND_SIZE[kind] / KIND_SIZE["entity"])
        spores[kind] = (spore_pts, spore_size)

    counts = Counter(n.kind for n in nodes)
    trunk_r = float(skeleton.radii[0]) if skeleton.radii is not None else 0.0
    title = (
        f"{slug} | {genre} | chunks={counts.get('chunk', 0)}  "
        f"limbs={skeleton.n_nodes}  trunk r={trunk_r:.2f}"
    )
    return TreeGeometry(
        skeleton=skeleton,
        layout=layout,
        positions=positions,
        crown=crown,
        palette=palette,
        leaf_points=kept,
        leaf_tint=tint,
        leaf_radius=leaf_radius,
        spores=spores,
        title=title,
        counts=counts,
        trunk_height=float(trunk_height),
    )
