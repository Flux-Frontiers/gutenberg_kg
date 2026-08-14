"""Tests for seasonal foliage and crown orientation."""

import numpy as np
import pytest

# The modules under test import pyvista at module scope, which CI does not
# install (the viz3d extra is optional).  Skip at collection time rather than
# letting the import blow up the whole run.
pytest.importorskip("pyvista")

from gutenberg_kg.scene import (  # noqa: E402
    DEFAULT_SEASON,
    SEASONS,
    _crown_halo,
    _leaf_facing,
    _nearest_neighbour_gap,
    _oriented_cluster,
)

from _render import can_render  # noqa: E402

# An importable pyvista is not the same as a usable one: without a working GL
# context a Plotter aborts the interpreter rather than raising. Only
# TestSeasonalScene renders; the rest of this file is foliage maths and stays
# useful on a machine that cannot render.
requires_render = pytest.mark.skipif(
    not can_render(), reason="pyvista off-screen rendering unavailable"
)


class TestSeasons:
    def test_the_four_seasons_are_defined(self):
        assert set(SEASONS) == {"spring", "summer", "autumn", "winter"}

    def test_summer_is_the_default(self):
        assert DEFAULT_SEASON == "summer"

    def test_every_season_offers_several_foliage_colours(self):
        # One flat colour per season is what the varied palette exists to avoid.
        assert all(len(s.foliage) >= 3 for s in SEASONS.values())

    def test_colours_are_hex(self):
        for season in SEASONS.values():
            assert all(c.startswith("#") and len(c) == 7 for c in season.foliage)
            assert season.wood.startswith("#")
            assert all(c.startswith("#") for c in season.sky)

    def test_only_winter_thins_the_canopy(self):
        assert SEASONS["winter"].density < 0.25
        assert all(SEASONS[s].density == 1.0 for s in ("spring", "summer", "autumn"))


class TestLeafFacing:
    def test_a_vertical_limb_faces_straight_up(self):
        assert np.allclose(_leaf_facing(np.array([0.0, 0.0, 5.0])), [0, 0, 1])

    def test_facing_follows_the_limb_outward(self):
        east = _leaf_facing(np.array([3.0, 0.0, 0.0]))
        west = _leaf_facing(np.array([-3.0, 0.0, 0.0]))
        assert east[0] > 0 and west[0] < 0
        assert east[2] > 0 and west[2] > 0  # both still reach for light

    def test_facing_is_a_unit_vector(self):
        for outward in ([1.0, 2.0, 0.0], [-4.0, 0.5, 0.0], [0.0, -3.0, 0.0]):
            assert np.linalg.norm(_leaf_facing(np.array(outward))) == pytest.approx(1.0)

    def test_up_bias_controls_how_far_the_cluster_leans(self):
        outward = np.array([3.0, 0.0, 0.0])
        assert _leaf_facing(outward, up_bias=0.1)[2] < _leaf_facing(outward, up_bias=2.0)[2]


class TestOrientedCluster:
    def test_all_points_lie_on_the_facing_side(self):
        centre = np.array([5.0, 0.0, 10.0])
        facing = _leaf_facing(np.array([5.0, 0.0, 0.0]))
        pts = np.asarray(_oriented_cluster(60, centre, facing, radius=2.0))
        assert ((pts - centre) @ facing >= -1e-9).all()

    def test_cluster_follows_the_limb_not_world_up(self):
        # Regression: chunks were filtered on p[2] >= tip[2], so every
        # sub-canopy domed straight up regardless of its branch direction.
        centre = np.array([5.0, 0.0, 10.0])
        pts = np.asarray(
            _oriented_cluster(60, centre, _leaf_facing(np.array([5.0, 0.0, 0.0])), radius=2.0)
        )
        assert pts[:, 0].mean() > centre[0]

    def test_requested_count_is_honoured(self):
        centre = np.zeros(3)
        facing = np.array([0.0, 0.0, 1.0])
        assert len(_oriented_cluster(7, centre, facing, radius=1.0)) == 7

    def test_points_stay_within_the_radius(self):
        centre = np.array([1.0, 2.0, 3.0])
        facing = _leaf_facing(np.array([0.0, 4.0, 0.0]))
        pts = np.asarray(_oriented_cluster(40, centre, facing, radius=2.5))
        assert np.linalg.norm(pts - centre, axis=1).max() <= 2.5 + 1e-9


class TestCrownHalo:
    @staticmethod
    def _crown(n=300, seed=0):
        rng = np.random.default_rng(seed)
        return rng.normal(0, 1, (n, 3)) * np.array([3.0, 3.0, 9.0]) + np.array([0.0, 0.0, 25.0])

    def test_halo_encloses_the_crown(self):
        crown = self._crown()
        halo = _crown_halo(400, crown, seed=1)
        assert halo[:, 2].max() > crown[:, 2].max()
        assert halo[:, 2].min() < crown[:, 2].min()

    def test_halo_follows_crown_proportions(self):
        # A columnar crown should get a tall halo, not a round one.
        halo = _crown_halo(400, self._crown(), seed=2)
        spread = halo.max(axis=0) - halo.min(axis=0)
        assert spread[2] > 2 * spread[0]

    def test_halo_has_depth_rather_than_being_a_shell(self):
        # Regression: a thin shell put thousands of spores at nearly one
        # radius, which rendered as an opaque egg around the tree.
        crown = self._crown()
        centre = (crown.max(axis=0) + crown.min(axis=0)) / 2
        half = (crown.max(axis=0) - crown.min(axis=0)) / 2
        radial = np.linalg.norm((_crown_halo(600, crown, seed=3) - centre) / half, axis=1)
        assert radial.max() - radial.min() > 0.5

    def test_halo_is_deterministic(self):
        crown = self._crown()
        assert np.array_equal(_crown_halo(200, crown, seed=7), _crown_halo(200, crown, seed=7))

    def test_requested_count_is_honoured(self):
        assert _crown_halo(137, self._crown(), seed=4).shape == (137, 3)


class TestNearestNeighbourGap:
    def test_gap_of_a_single_point_is_unit(self):
        assert _nearest_neighbour_gap(np.zeros((1, 3))).tolist() == [1.0]

    def test_gap_is_the_closest_distance(self):
        pts = np.array([[0.0, 0, 0], [3.0, 0, 0], [3.5, 0, 0]])
        assert _nearest_neighbour_gap(pts).tolist() == pytest.approx([3.0, 0.5, 0.5])

    def test_denser_sets_report_smaller_gaps(self):
        rng = np.random.default_rng(0)
        sparse = _nearest_neighbour_gap(rng.normal(0, 10, (20, 3)))
        dense = _nearest_neighbour_gap(rng.normal(0, 10, (200, 3)))
        assert np.median(dense) < np.median(sparse)


class TestLeafCling:
    @staticmethod
    def _tree():
        from kg_utils.viz3d import grow_tree

        rng = np.random.default_rng(5)
        crown = rng.normal(0, 1, (300, 3)) * np.array([4.0, 4.0, 5.0]) + np.array([0, 0, 30.0])
        return crown, grow_tree(crown, np.zeros(3), key="cling")

    def test_clinging_draws_leaves_toward_the_wood(self):
        from kg_utils.viz3d import leaf_glyphs

        crown, sk = self._tree()
        loose = leaf_glyphs(crown, sk, cling=0.0, seed=1)
        tight = leaf_glyphs(crown, sk, cling=0.9, seed=1)

        def mean_gap(glyphed):
            pts = np.asarray(glyphed.points)
            return np.linalg.norm(pts[:, None, :] - sk.points[None, :, :], axis=2).min(1).mean()

        assert mean_gap(tight) < mean_gap(loose)

    def test_leaves_never_sink_into_the_wood(self):
        from kg_utils.viz3d import leaf_glyphs

        crown, sk = self._tree()
        glyphed = leaf_glyphs(crown, sk, size=0.3, cling=1.0, seed=1)
        pts = np.asarray(glyphed.points)
        dist = np.linalg.norm(pts[:, None, :] - sk.points[None, :, :], axis=2)
        nearest = dist.argmin(axis=1)
        assert sk.radii is not None
        # Every leaf stays outside its branch's radius (glyph extent aside).
        assert (dist[np.arange(len(pts)), nearest] >= sk.radii[nearest] * 0.5).all()


@requires_render
class TestSeasonalScene:
    def test_unknown_season_is_refused_clearly(self, tmp_path):
        pv = pytest.importorskip("pyvista")
        from test_scene import _prose_book

        from gutenberg_kg.scene import BookMeta, build_tree_scene, load_book_graph

        _prose_book(tmp_path / "g" / "b")
        meta = BookMeta("b", "g", tmp_path / "g" / "b")
        nodes, edges = load_book_graph(meta)
        plotter = pv.Plotter(off_screen=True)
        with pytest.raises(ValueError, match="Unknown season"):
            build_tree_scene(nodes, edges, plotter, slug=meta.slug, season="monsoon")
        plotter.close()

    def test_winter_drops_most_of_the_leaves(self, tmp_path):
        pv = pytest.importorskip("pyvista")
        from test_scene import _prose_book

        from gutenberg_kg.scene import BookMeta, build_tree_scene, load_book_graph

        _prose_book(tmp_path / "g" / "b", n_sections=8, chunks_per_section=20)
        meta = BookMeta("b", "g", tmp_path / "g" / "b")
        nodes, edges = load_book_graph(meta)

        counts = {}
        for season in ("summer", "winter"):
            plotter = pv.Plotter(off_screen=True)
            build_tree_scene(nodes, edges, plotter, slug=meta.slug, season=season)
            counts[season] = plotter.renderer.actors["leaves"].mapper.dataset.n_points
            plotter.close()
        assert counts["winter"] < counts["summer"] * 0.3
