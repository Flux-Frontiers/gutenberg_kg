"""
Tests for the species look: textured bark and species leaf outlines.

Sweep item 64: the PyVista tree now wears its species' bark (a continuous
sweep with texture coordinates, from kgmodule-utils 0.25.0) and leaves in its
species' outline, both from the same tables the Knowledge Press web forest
uses.  ``species_look=False`` keeps the plain tree exactly as it was.
"""

import numpy as np
import pytest

pytest.importorskip("pyvista")

from _render import can_render  # noqa: E402
from kg_utils.viz3d import SPECIES, LayoutEdge, LayoutNode  # noqa: E402

from gutenberg_kg.leafshapes import (  # noqa: E402
    ELLIPSOID_LEAF_AREA,
    LEAF_SHAPES,
    MAX_LEAF_SCALE,
    leaf_outline,
    leaf_prototype,
    leaf_scale,
    outline_area,
)
from gutenberg_kg.scene import build_tree_scene, species_leaf_glyphs  # noqa: E402
from gutenberg_kg.treegeom import GENRE_SPECIES, bark_texture_path, grow_tree_geometry  # noqa: E402

requires_render = pytest.mark.skipif(
    not can_render(), reason="pyvista off-screen rendering unavailable"
)


def _book(slug: str = "a_book") -> tuple[list[LayoutNode], list[LayoutEdge]]:
    nodes = [LayoutNode(id=f"{slug}:doc", kind="document", name=slug)]
    edges: list[LayoutEdge] = []
    for s in range(10):
        sid = f"{slug}:sec{s}"
        nodes.append(LayoutNode(id=sid, kind="section", name=sid))
        edges.append(LayoutEdge(src=f"{slug}:doc", rel="CONTAINS", dst=sid))
        for c in range(12):
            cid = f"{sid}:c{c}"
            nodes.append(LayoutNode(id=cid, kind="chunk", name=cid))
            edges.append(LayoutEdge(src=sid, rel="CONTAINS", dst=cid))
    return nodes, edges


class TestLeafShapes:
    def test_every_species_has_a_leaf_and_a_bark(self):
        assert set(LEAF_SHAPES) == set(SPECIES)
        for species in SPECIES:
            path = bark_texture_path(species)
            assert path is not None and path.stat().st_size > 1000, species
        assert bark_texture_path("no-such-species") is None

    @pytest.mark.parametrize("species", sorted(LEAF_SHAPES))
    def test_outline_is_a_symmetric_leaf_on_a_stalk(self, species):
        outline = leaf_outline(LEAF_SHAPES[species])
        assert outline.shape[1] == 2 and len(outline) >= 8
        assert outline[:, 1].max() == pytest.approx(1.0) and outline[:, 1].min() == pytest.approx(
            -1.0
        )
        assert abs(outline[:, 0].max() + outline[:, 0].min()) < 1e-9
        assert np.abs(outline[:, 0]).max() <= 1.0

    @pytest.mark.parametrize("species", sorted(LEAF_SHAPES))
    def test_prototype_triangulates_the_whole_outline(self, species):
        proto = leaf_prototype(species, 0.3)
        # An ear-clipped simple polygon has exactly K - 2 triangles.
        assert proto.n_cells == len(leaf_outline(LEAF_SHAPES[species])) - 2
        area = float(proto.compute_cell_sizes()["Area"].sum())
        scale = leaf_scale(species)
        expected = outline_area(leaf_outline(LEAF_SHAPES[species])) * (0.3 * scale) ** 2
        assert area == pytest.approx(expected, rel=1e-6)
        # Blade along +x, flat in xy.
        assert np.ptp(proto.points[:, 0]) > np.ptp(proto.points[:, 1])
        assert np.ptp(proto.points[:, 2]) == 0.0

    def test_leaves_cover_the_ellipsoid_area_the_canopy_had(self):
        for species in LEAF_SHAPES:
            scale = leaf_scale(species)
            assert 1.0 <= scale <= MAX_LEAF_SCALE
            area = outline_area(leaf_outline(LEAF_SHAPES[species])) * scale**2
            if scale < MAX_LEAF_SCALE:
                assert area == pytest.approx(ELLIPSOID_LEAF_AREA)
            else:  # the capped, narrow willow leaf
                assert area < ELLIPSOID_LEAF_AREA


def test_species_leaf_glyphs_stamp_one_leaf_per_point_with_tint():
    nodes, edges = _book()
    tree = grow_tree_geometry(nodes, edges, slug="a_book", genre="philosophy")
    leaves = species_leaf_glyphs(
        tree.leaf_points,
        tree.skeleton,
        species=tree.species,
        size=tree.leaf_radius,
        tint=tree.leaf_tint,
    )
    per_leaf = leaf_prototype(tree.species, tree.leaf_radius).n_points
    assert leaves.n_points == per_leaf * len(tree.leaf_points)
    assert set(np.unique(leaves["tint"])) <= set(np.unique(tree.leaf_tint))


def test_genre_species_all_have_bark():
    for genre, species in GENRE_SPECIES.items():
        assert bark_texture_path(species) is not None, genre


@requires_render
def test_species_look_textures_the_wood():
    import pyvista as pv

    nodes, edges = _book()
    plotter = pv.Plotter(off_screen=True)
    try:
        build_tree_scene(nodes, edges, plotter, slug="a_book", genre="shakespeare")
        wood = plotter.actors["wood"]
        assert wood.texture is not None
        assert wood.mapper.dataset.active_texture_coordinates is not None
        assert "leaves" in plotter.actors
    finally:
        plotter.close()


@requires_render
def test_plain_look_keeps_the_untextured_tree():
    import pyvista as pv

    nodes, edges = _book()
    plotter = pv.Plotter(off_screen=True)
    try:
        build_tree_scene(
            nodes, edges, plotter, slug="a_book", genre="shakespeare", species_look=False
        )
        wood = plotter.actors["wood"]
        assert wood.texture is None
        assert wood.mapper.dataset.active_texture_coordinates is None
    finally:
        plotter.close()
