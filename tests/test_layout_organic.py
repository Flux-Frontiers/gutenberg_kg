"""Tests for the organic tree layout — space colonization, pipe radii, sweeps."""

import numpy as np
import pytest

from gutenberg_kg.layout_organic import (
    colonize,
    crown_spacing,
    grow_tree,
    pipe_radii,
    root_to_tip_paths,
    seed_from_slug,
    smooth_paths,
)


def _ellipsoid_crown(n: int, seed: int = 1) -> np.ndarray:
    """A filled ellipsoidal crown of *n* points, centred above the origin."""
    rng = np.random.default_rng(seed)
    return rng.normal(0, 1, (n, 3)) * np.array([4.0, 4.0, 5.0]) + np.array([0.0, 0.0, 30.0])


def _hollow_crown(n: int, seed: int = 2) -> np.ndarray:
    """An annular crown with an empty core — the shape a diary's entries make."""
    rng = np.random.default_rng(seed)
    theta = rng.uniform(0, 2 * np.pi, n)
    radius = rng.uniform(30.0, 45.0, n)
    z = rng.uniform(13.0, 44.0, n)
    return np.column_stack([radius * np.cos(theta), radius * np.sin(theta), z])


class TestSeed:
    def test_seed_is_stable_across_calls(self):
        assert seed_from_slug("hamlet") == seed_from_slug("hamlet")

    def test_different_slugs_differ(self):
        assert seed_from_slug("hamlet") != seed_from_slug("macbeth")

    def test_seed_fits_32_bits(self):
        assert 0 <= seed_from_slug("a rather long book slug indeed") < 2**32


class TestCrownSpacing:
    def test_degenerate_clouds_return_unit_spacing(self):
        assert crown_spacing(np.zeros((1, 3))) == 1.0

    def test_spacing_shrinks_as_density_rises(self):
        sparse = crown_spacing(_ellipsoid_crown(100))
        dense = crown_spacing(_ellipsoid_crown(2000))
        assert dense < sparse


class TestColonize:
    def test_empty_attractors_yield_bare_root(self):
        sk = colonize(np.empty((0, 3)), np.zeros(3))
        assert sk.n_nodes == 1
        assert sk.parents[0] == -1

    def test_growth_branches_rather_than_chaining(self):
        sk = colonize(_ellipsoid_crown(400), np.zeros(3), seed=3)
        assert sk.n_nodes > 100
        # A chain has exactly one tip; a tree has many.
        assert len(sk.tips) > 10

    def test_hollow_crown_still_branches(self):
        # Regression: a step derived from inter-chunk spacing is far too fine to
        # span an empty core, so the leader marched up the hole as one chain.
        sk = colonize(_hollow_crown(3000), np.zeros(3), seed=4)
        assert len(sk.tips) > 5

    def test_every_node_but_the_root_has_a_parent(self):
        sk = colonize(_ellipsoid_crown(200), np.zeros(3), seed=5)
        assert sk.parents[0] == -1
        assert (sk.parents[1:] >= 0).all()
        # colonize only ever appends children, which pipe_radii relies on.
        assert (sk.parents[1:] < np.arange(1, sk.n_nodes)).all()

    def test_growth_is_deterministic_for_a_seed(self):
        crown = _ellipsoid_crown(300)
        a = colonize(crown, np.zeros(3), seed=7)
        b = colonize(crown, np.zeros(3), seed=7)
        assert np.array_equal(a.points, b.points)

    def test_attractor_cap_is_reported_not_silent(self):
        sk = colonize(_ellipsoid_crown(5000), np.zeros(3), max_attractors=1000, seed=8)
        assert sk.attractors_used == 1000
        assert sk.attractors_total == 5000

    def test_uncapped_growth_uses_every_attractor(self):
        sk = colonize(_ellipsoid_crown(200), np.zeros(3), max_attractors=None, seed=9)
        assert sk.attractors_used == sk.attractors_total == 200

    def test_upward_tropism_lifts_the_crown(self):
        crown = _ellipsoid_crown(300)
        up = colonize(crown, np.zeros(3), tropism=(0, 0, 0.6), seed=11)
        down = colonize(crown, np.zeros(3), tropism=(0, 0, -0.3), seed=11)
        assert up.points[:, 2].max() > down.points[:, 2].max()


class TestPipeRadii:
    def test_tips_get_the_tip_radius(self):
        sk = colonize(_ellipsoid_crown(300), np.zeros(3), seed=12)
        radii = pipe_radii(sk, tip_radius=0.05)
        assert np.allclose(radii[sk.tips], 0.05)

    def test_trunk_is_the_thickest_limb(self):
        sk = colonize(_ellipsoid_crown(300), np.zeros(3), seed=13)
        radii = pipe_radii(sk)
        assert radii[0] == pytest.approx(radii.max())

    def test_a_parent_is_never_thinner_than_its_child(self):
        sk = colonize(_ellipsoid_crown(400), np.zeros(3), seed=14)
        radii = pipe_radii(sk)
        for child, parent in enumerate(sk.parents):
            if parent >= 0:
                assert radii[parent] >= radii[child] - 1e-9

    def test_a_bigger_book_grows_a_thicker_trunk(self):
        small = pipe_radii(colonize(_ellipsoid_crown(120), np.zeros(3), seed=15))
        large = pipe_radii(colonize(_ellipsoid_crown(2000), np.zeros(3), seed=15))
        assert large[0] > small[0]

    def test_radii_are_stored_on_the_skeleton(self):
        sk = colonize(_ellipsoid_crown(100), np.zeros(3), seed=16)
        assert sk.radii is None
        pipe_radii(sk)
        assert sk.radii is not None


class TestPathsAndSweeps:
    def test_every_tip_yields_a_root_to_tip_path(self):
        sk = colonize(_ellipsoid_crown(300), np.zeros(3), seed=17)
        paths = root_to_tip_paths(sk)
        assert len(paths) == len(sk.tips)
        assert all(p[0] == 0 for p in paths)

    def test_smoothing_adds_points_and_keeps_radii_aligned(self):
        sk = grow_tree(_ellipsoid_crown(300), np.zeros(3), slug="book")
        raw = root_to_tip_paths(sk)
        for (points, radii), path in zip(smooth_paths(sk), (p for p in raw if len(p) >= 2)):
            assert points.shape[0] >= len(path)
            assert points.shape[0] == radii.shape[0]

    def test_smoothing_fills_radii_when_missing(self):
        sk = colonize(_ellipsoid_crown(200), np.zeros(3), seed=18)
        assert sk.radii is None
        assert smooth_paths(sk)
        assert sk.radii is not None


class TestGrowTree:
    def test_same_slug_grows_the_same_tree(self):
        crown = _ellipsoid_crown(300)
        assert np.array_equal(
            grow_tree(crown, np.zeros(3), slug="pepys").points,
            grow_tree(crown, np.zeros(3), slug="pepys").points,
        )

    def test_different_slugs_grow_different_wood(self):
        crown = _ellipsoid_crown(300)
        a = grow_tree(crown, np.zeros(3), slug="pepys")
        b = grow_tree(crown, np.zeros(3), slug="evelyn")
        assert a.n_nodes != b.n_nodes or not np.array_equal(a.points, b.points)

    def test_radii_are_assigned(self):
        sk = grow_tree(_ellipsoid_crown(200), np.zeros(3), slug="x")
        assert sk.radii is not None and sk.radii[0] > 0
