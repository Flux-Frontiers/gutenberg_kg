"""
scene.py — Qt-free scene builder for the GutenbergKG 3-D knowledge tree forest.

Everything here composes a forest into a plain ``pv.Plotter``: corpus scanning,
glyph/edge geometry, :func:`build_forest_scene` and :func:`build_tree_scene`.
No PyQt, no ``QApplication.processEvents`` — the interactive viewer
(:mod:`gutenberg_kg.viz3d`) is one caller of this module and the off-screen
light-field renderer (``gutenkg quilt``) is another.

The *placement* half — :class:`ForestLayout`, the seasons, and
:func:`grow_tree_geometry` — lives in :mod:`gutenberg_kg.treegeom`, which
imports no PyVista.  That is what lets :mod:`gutenberg_kg.povscene` emit the
same tree as analytic POV-Ray primitives without a VTK stack.  Every public
name from there is re-exported below, so importing it from this module keeps
working.

Progress reporting is a plain ``Callable[[str], None]`` so a Qt caller can pump
its event loop and a headless caller can print or ignore.

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pyvista as pv
from kg_utils.viz3d import (
    LayoutEdge,
    LayoutNode,
    Skeleton,
    leaf_glyphs,
    seed_from_key,
    tree_mesh,
)

from gutenberg_kg.bookgraph import (
    DEFAULT_CORPUS,
    KG_DIRS,
    BookMeta,
    load_book_graph,
    load_entry_times,
    scan_corpus,
)
from gutenberg_kg.treegeom import (
    BRANCH_COLOR,
    DEFAULT_SEASON,
    DEFAULT_TROPISM,
    GENRE_PALETTE,
    GENRE_TROPISM,
    GROUND_COLOR,
    KIND_COLOR,
    KIND_SIZE,
    LEAF_REFERENCE_COUNT,
    LOD_HIGH,
    LOD_LOW,
    MAX_EDGES,
    REL_COLOR,
    SEASONS,
    SKY_BOTTOM,
    SKY_TOP,
    SPORE_CAP,
    SPORE_LEAF_RATIO,
    SPORE_OPACITY,
    TRUNK_COLOR,
    WOOD_COLOR,
    ForestLayout,
    SceneFilters,
    Season,
    TreeGeometry,
    grow_tree_geometry,
)

logger = logging.getLogger(__name__)

__author__ = "Eric G. Suchanek, PhD"

# Re-exported for the many callers (and tests) that import geometry names from
# this module.  Listed explicitly so the linter does not strip them.
__all__ = [
    "BRANCH_COLOR",
    "DEFAULT_CORPUS",
    "DEFAULT_SEASON",
    "DEFAULT_TROPISM",
    "GENRE_PALETTE",
    "GENRE_TROPISM",
    "GROUND_COLOR",
    "KG_DIRS",
    "KIND_COLOR",
    "KIND_SIZE",
    "LEAF_REFERENCE_COUNT",
    "LOD_HIGH",
    "LOD_LOW",
    "MAX_EDGES",
    "REL_COLOR",
    "SEASONS",
    "SKY_BOTTOM",
    "SKY_TOP",
    "SPORE_CAP",
    "SPORE_LEAF_RATIO",
    "SPORE_OPACITY",
    "TRUNK_COLOR",
    "WOOD_COLOR",
    "BookMeta",
    "ForestLayout",
    "Season",
    "SceneFilters",
    "SceneInfo",
    "TreeGeometry",
    "arc_points",
    "build_forest_scene",
    "build_tree_scene",
    "glyph_proto",
    "grow_tree_geometry",
    "load_book_graph",
    "load_entry_times",
    "make_node_mesh",
    "scan_corpus",
]


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
    :param filters: Only ``show_entities`` (gold spores) and ``show_topics``
        (blue pollen) are consulted.  Wood and leaves are the point of this
        scene.
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
    report = progress or (lambda _msg: None)
    tree = grow_tree_geometry(
        nodes,
        edges,
        slug=slug,
        genre=genre,
        entry_times=entry_times,
        filters=filters,
        season=season,
        tip_radius=tip_radius,
        leaf_size=leaf_size,
        progress=progress,
    )
    palette, skeleton = tree.palette, tree.skeleton

    plotter.clear_actors()
    plotter.enable_anti_aliasing("msaa")
    plotter.set_background(palette.sky[0], top=palette.sky[1])  # ty: ignore[invalid-argument-type]

    report(f"Sweeping {skeleton.n_nodes:,} skeleton nodes into wood...")
    wood = tree_mesh(skeleton)
    if wood.n_points:
        plotter.add_mesh(wood, color=palette.wood, smooth_shading=True, name="wood")

    report(f"Placing leaves ({season})...")
    leaves = leaf_glyphs(
        tree.leaf_points,
        skeleton,
        size=tree.leaf_radius,
        tint=tree.leaf_tint,
        seed=seed_from_key(slug + ":leaves"),
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

    for kind, (spore_pts, spore_size) in tree.spores.items():
        spores = pv.PolyData(spore_pts).glyph(
            geom=pv.Tetrahedron(radius=spore_size), orient=False, scale=False
        )
        plotter.add_mesh(
            spores, color=KIND_COLOR[kind], opacity=SPORE_OPACITY, name=f"{kind}-spores"
        )

    if ground_size > 0:
        ground = pv.Plane(
            center=(0, 0, -0.2), direction=(0, 0, 1), i_size=ground_size, j_size=ground_size
        )
        plotter.add_mesh(ground, color=GROUND_COLOR, name="ground")

    report("Tree grown.")
    return SceneInfo(
        title=tree.title,
        positions=tree.positions,
        layout=tree.layout,
        counts=tree.counts,
        n_books=1,
        skeleton=skeleton,
        trunk_height=tree.trunk_height,
    )
