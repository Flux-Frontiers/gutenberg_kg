"""
Tests for tree species in the forest layout and the hero tree.

A genre picks a species (``GENRE_SPECIES``); the species' habit, from
kgmodule-utils, places the crown and grows the wood.  What must not change is
what the book decides: every chunk still gets a crown point, and every leaf
still hangs on wood.
"""

import numpy as np
import pytest
from kg_utils.viz3d import SPECIES, LayoutEdge, LayoutNode, envelope_width

from gutenberg_kg.treegeom import (
    DEFAULT_SPECIES,
    DEFAULT_TROPISM,
    GENRE_SPECIES,
    GENRE_TROPISM,
    ForestLayout,
    book_habit,
    grow_tree_geometry,
    species_for,
)


def _book(
    slug: str, n_sections: int = 12, per: int = 15
) -> tuple[list[LayoutNode], list[LayoutEdge]]:
    """A prose book: one document, *n_sections* sections of *per* chunks."""
    nodes = [LayoutNode(id=f"{slug}:doc", kind="document", name=slug)]
    edges: list[LayoutEdge] = []
    for s in range(n_sections):
        sid = f"{slug}:sec{s}"
        nodes.append(LayoutNode(id=sid, kind="section", name=sid))
        edges.append(LayoutEdge(src=f"{slug}:doc", rel="CONTAINS", dst=sid))
        for c in range(per):
            cid = f"{slug}:sec{s}:c{c}"
            nodes.append(LayoutNode(id=cid, kind="chunk", name=cid))
            edges.append(LayoutEdge(src=sid, rel="CONTAINS", dst=cid))
    return nodes, edges


def test_every_species_in_the_table_exists():
    assert set(GENRE_SPECIES.values()) <= set(SPECIES)
    assert DEFAULT_SPECIES in SPECIES
    assert species_for("no-such-genre") == DEFAULT_SPECIES
    # All nine species grow somewhere in the corpus.
    assert set(GENRE_SPECIES.values()) == set(SPECIES)


def test_tropism_table_follows_the_species():
    for genre, species in GENRE_SPECIES.items():
        assert GENRE_TROPISM[genre] == (0.0, 0.0, SPECIES[species].tropism)
    assert DEFAULT_TROPISM == (0.0, 0.0, SPECIES[DEFAULT_SPECIES].tropism)


def test_book_habit_is_seeded_per_book():
    assert book_habit("walden", "philosophy") == book_habit("walden", "philosophy")
    assert book_habit("walden", "philosophy") != book_habit("leviathan", "philosophy")
    assert book_habit("walden", "philosophy").envelope == SPECIES["oak"].envelope


@pytest.mark.parametrize("genre", ["philosophy", "science-fiction", "travel", "shakespeare"])
def test_sections_follow_the_species_envelope(genre):
    slug = "a_book"
    nodes, edges = _book(slug)
    layout = ForestLayout(book_genre_map={slug: genre})
    positions = layout.compute(nodes, edges)
    habit = layout.book_habits[slug]
    assert habit == book_habit(slug, genre)
    base, height = layout.book_trunks[slug]
    tips = np.array([positions[f"{slug}:sec{s}"] for s in range(12)]) - np.array(
        [base[0], base[1], 0.0]
    )
    z = tips[:, 2]
    assert z.min() == pytest.approx(height * habit.clear_bole)
    s = (z - z.min()) / (z.max() - z.min())
    branch = layout.branch_radius + np.sqrt(12) * 0.5
    expected = [branch * habit.width * envelope_width(habit.envelope, t) for t in s]
    np.testing.assert_allclose(np.hypot(tips[:, 0], tips[:, 1]), expected, rtol=1e-9)
    # Every chunk is still placed, one crown point each.
    assert all(n.id in positions for n in nodes)


def test_species_give_different_silhouettes():
    def aspect(genre: str) -> float:
        nodes, edges = _book("same_book")
        tree = grow_tree_geometry(nodes, edges, slug="same_book", genre=genre)
        pts = tree.skeleton.points
        return float(np.hypot(pts[:, 0], pts[:, 1]).max() / pts[:, 2].max())

    # A poplar is a narrow spindle, an oak a broad dome.
    assert aspect("philosophy") > 1.8 * aspect("travel")


@pytest.mark.parametrize(
    "genre", sorted({g for g in GENRE_SPECIES if GENRE_SPECIES[g] in ("willow", "birch")})
)
def test_drooping_trees_keep_every_leaf_on_the_wood(genre):
    slug = "weeping"
    nodes, edges = _book(slug)
    tree = grow_tree_geometry(nodes, edges, slug=slug, genre=genre)
    assert species_for(genre) in tree.title
    # Droop moved the crown; leaves and chunk positions moved with it.
    chunk_pos = np.array([tree.positions[n.id] for n in nodes if n.kind == "chunk"])
    np.testing.assert_allclose(chunk_pos, tree.crown)
    gaps = np.linalg.norm(tree.crown[:, None, :] - tree.skeleton.points[None, :, :], axis=2).min(
        axis=1
    )
    undrooped = grow_tree_geometry(nodes, edges, slug=slug, genre="philosophy")
    extent = np.linalg.norm(undrooped.crown.max(axis=0) - undrooped.crown.min(axis=0))
    assert gaps.max() < 0.1 * extent
