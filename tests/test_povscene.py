"""
Tests for the analytic POV-Ray backend.

Deliberately **not** gated on ``pyvista``: the whole point of this path is that
a scene can be composed without a VTK stack, and a test that imported pyvista
to check that claim would not be checking it.  The two tests that do compare
against the rasterised tree import pyvista themselves and skip without it.
"""

import re
import subprocess
import sys

import numpy as np
import pytest
from _render import can_render
from kg_utils.viz3d import (
    LEAF_ASPECT,
    LayoutEdge,
    LayoutNode,
    leaf_frames,
    limb_paths,
    seed_from_key,
)

from gutenberg_kg.povscene import (
    LEAF_PROTOTYPE,
    build_tree_pov_scene,
    tree_lights,
    tree_pov_camera,
    tree_pov_scene,
)
from gutenberg_kg.treegeom import SceneFilters, grow_tree_geometry

SLUG = "a_treatise"

_INSTANCE = re.compile(
    r"object \{ " + LEAF_PROTOTYPE + r" scale <([^>]*)>.*?translate <([^>]*)>.*?"
    r"texture \{ (\w+) \}"
)


def _book(n_sections=4, chunks_per_section=6, n_spores=0):
    """A synthetic prose book: one document, sections, chunks under each."""
    nodes = [LayoutNode(id=f"{SLUG}:doc:book", kind="document", name="book")]
    edges: list[LayoutEdge] = []
    for kind in ("entity", "topic"):
        for i in range(n_spores):
            nodes.append(LayoutNode(id=f"{SLUG}:{kind}:{i}", kind=kind, name=f"{kind}{i}"))
    for s in range(n_sections):
        sid = f"{SLUG}:sec:{s}"
        nodes.append(LayoutNode(id=sid, kind="section", name=f"s{s}"))
        edges.append(LayoutEdge(src=f"{SLUG}:doc:book", rel="CONTAINS", dst=sid))
        for c in range(chunks_per_section):
            cid = f"{SLUG}:chunk:{s}:{c}"
            nodes.append(LayoutNode(id=cid, kind="chunk", name=f"c{s}{c}"))
            edges.append(LayoutEdge(src=sid, rel="CONTAINS", dst=cid))
    return nodes, edges


@pytest.fixture
def geometry():
    nodes, edges = _book()
    return grow_tree_geometry(nodes, edges, slug=SLUG, genre="philosophy")


@pytest.fixture
def scene(geometry):
    return tree_pov_scene(geometry, slug=SLUG)


@pytest.fixture
def sdl(scene):
    return scene.sdl()


def _instances(sdl):
    """``[(scale, translate, texture name), ...]`` for every leaf instance."""
    out = []
    for scale, translate, texture in _INSTANCE.findall(sdl):
        out.append(
            (
                np.fromstring(scale, sep=","),
                np.fromstring(translate, sep=","),
                texture,
            )
        )
    return out


#: Import blocker: makes ``pyvista`` and ``vtkmodules`` unimportable, so a
#: subprocess sees the environment a headless render box actually has.  Note
#: that merely asserting ``"pyvista" not in sys.modules`` would NOT test this:
#: ``quiltwright/__init__`` eagerly imports ``lfd``, which imports pyvista when
#: it happens to be installed, so povgen drags it in through no fault of ours.
#: What matters — and what this checks — is that the POV path still *works*
#: when the rendering stack is absent.
_BLOCK_RENDERING_STACK = """
import sys

class _Block:
    def find_module(self, name, path=None):
        return self if name.split(".")[0] in ("pyvista", "vtk", "vtkmodules") else None
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("pyvista", "vtk", "vtkmodules"):
            raise ImportError(f"blocked: {name}")
        return None

sys.meta_path.insert(0, _Block())
"""


class TestNoRenderingStack:
    def test_a_scene_composes_with_no_pyvista_installed(self):
        # The claim this whole module exists to make.  If povscene ever reaches
        # for scene.py rather than treegeom.py, this is what says so.
        probe = (
            _BLOCK_RENDERING_STACK
            + """
from gutenberg_kg.povscene import build_tree_pov_scene
from kg_utils.viz3d import LayoutEdge, LayoutNode

nodes = [LayoutNode(id="b:doc:1", kind="document", name="d")]
edges = []
for s in range(2):
    nodes.append(LayoutNode(id=f"b:sec:{s}", kind="section", name="s"))
    edges.append(LayoutEdge(src="b:doc:1", rel="CONTAINS", dst=f"b:sec:{s}"))
    for c in range(4):
        nodes.append(LayoutNode(id=f"b:chunk:{s}:{c}", kind="chunk", name="c"))
        edges.append(LayoutEdge(src=f"b:sec:{s}", rel="CONTAINS", dst=f"b:chunk:{s}:{c}"))

scene, _ = build_tree_pov_scene(nodes, edges, slug="b")
assert "sphere_sweep {" in scene.sdl()
assert "pyvista" not in sys.modules and "vtkmodules" not in sys.modules
print("OK")
"""
        )
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout

    def test_the_pov_path_does_not_import_the_pyvista_scene_module(self):
        # The layering, stated directly: povscene depends on treegeom, and
        # treegeom is the half with no renderer in it.
        probe = (
            "import sys, gutenberg_kg.povscene;"
            "assert 'gutenberg_kg.scene' not in sys.modules, "
            "'povscene reached for the PyVista scene module'"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr

    def test_a_scene_composes_and_emits(self, sdl):
        assert sdl.startswith("// Generated by quiltwright.povgen")
        assert "sphere_sweep {" in sdl


class TestWood:
    def test_one_sweep_per_limb_path(self, geometry, sdl):
        assert sdl.count("sphere_sweep {") == len(limb_paths(geometry.skeleton, subdivisions=4))

    def test_sweeps_carry_the_pipe_model_radii(self, geometry, sdl):
        # The trunk is thicker than a twig because the pipe model says so; a
        # sweep emitted at one radius would throw that away silently.
        radii = [float(m) for m in re.findall(r"^\s+<[^>]+>, ([\d.eE+-]+),?$", sdl, re.MULTILINE)]
        assert radii, "no sweep radii emitted"
        assert max(radii) > min(radii) * 1.5

    def test_subdivisions_trade_size_for_smoothness(self, geometry):
        coarse = tree_pov_scene(geometry, slug=SLUG, subdivisions=2).sdl()
        fine = tree_pov_scene(geometry, slug=SLUG, subdivisions=8).sdl()
        assert len(fine) > len(coarse)


class TestFoliage:
    def test_one_instance_per_leaf(self, geometry, sdl):
        assert len(_instances(sdl)) == len(geometry.leaf_points)

    def test_the_prototype_is_declared_once(self, sdl):
        assert sdl.count(f"#declare {LEAF_PROTOTYPE} =") == 1

    def test_instance_scale_is_the_leaf_aspect(self, geometry, sdl):
        expected = np.asarray(LEAF_ASPECT) * geometry.leaf_radius
        for scale, _, _ in _instances(sdl):
            assert np.allclose(scale, expected)

    def test_leaves_sit_where_leaf_frames_puts_them(self, geometry, sdl):
        # Position parity with the PyVista path, checked without PyVista:
        # both backends call leaf_frames, so the emitted translations are that
        # function's output with z negated on the way out.
        points, _ = leaf_frames(
            geometry.leaf_points,
            geometry.skeleton,
            size=geometry.leaf_radius,
            cling=0.7,
            seed=seed_from_key(SLUG + ":leaves"),
        )
        emitted = np.asarray([t for _, t, _ in _instances(sdl)])
        expected = points.copy()
        expected[:, 2] *= -1.0
        assert np.allclose(np.sort(emitted, axis=0), np.sort(expected, axis=0))

    def test_every_palette_colour_is_declared_and_used(self, geometry, sdl):
        declared = set(re.findall(r"#declare (GutenLeafTex\d+) =", sdl))
        assert len(declared) == len(geometry.palette.foliage)
        assert {texture for _, _, texture in _instances(sdl)} <= declared

    def test_winter_bares_the_wood(self):
        nodes, edges = _book()
        summer = grow_tree_geometry(nodes, edges, slug=SLUG, season="summer")
        winter = grow_tree_geometry(nodes, edges, slug=SLUG, season="winter")
        leaves = [len(_instances(tree_pov_scene(g, slug=SLUG).sdl())) for g in (summer, winter)]
        assert leaves[1] < leaves[0]


class TestSpores:
    def test_no_halo_unless_asked_for(self, sdl):
        # Entities and topics are off by default: wood and leaves are the point
        # of this scene, and an unasked-for halo buries them.
        assert not _spore_spheres(sdl)

    def test_enabled_halos_are_emitted(self):
        nodes, edges = _book(n_spores=15)
        geometry = grow_tree_geometry(
            nodes,
            edges,
            slug=SLUG,
            filters=SceneFilters(show_entities=True, show_topics=True),
        )
        assert set(geometry.spores) == {"entity", "topic"}
        assert _spore_spheres(tree_pov_scene(geometry, slug=SLUG).sdl())

    def test_spores_stay_finer_than_the_foliage(self):
        nodes, edges = _book(n_spores=15)
        geometry = grow_tree_geometry(
            nodes, edges, slug=SLUG, filters=SceneFilters(show_entities=True)
        )
        radius = geometry.spores["entity"][1]
        assert 0 < radius < geometry.leaf_radius


def _spore_spheres(sdl):
    """Radii of the standalone ``sphere`` statements — the spore halo."""
    return [
        float(m)
        for m in re.findall(r"^\s+sphere \{ <[^>]+>, ([\d.eE+-]+) texture", sdl, re.MULTILINE)
    ]


class TestHandedness:
    def test_z_is_negated_on_emission(self, geometry, sdl):
        # POV-Ray is left-handed; the scene is authored right-handed. Both the
        # geometry and the camera are flipped, so the ray-traced image matches
        # the PyVista render rather than mirroring it.
        crown_top = float(geometry.crown[:, 2].max())
        emitted_z = [float(m) for m in re.findall(r"<[^,>]+, [^,>]+, ([-\d.eE+]+)>,", sdl)]
        assert emitted_z, "no emitted points found"
        # The tree grows up in +z, so every emitted z must be at or below zero.
        assert max(emitted_z) <= 1e-6
        assert min(emitted_z) < -crown_top / 2


class TestLighting:
    def test_the_key_light_is_above_the_tree_not_below_it(self, geometry):
        # Regression against quiltwright's lights_from_bounds, whose offsets
        # assume a +y-up world: used unchanged it puts the key light below the
        # ground of a +z-up scene, lighting the tree from underneath.
        lo = geometry.crown.min(axis=0)
        hi = geometry.crown.max(axis=0)
        key = tree_lights(lo, hi)[0]
        assert key.position[2] > hi[2]

    def test_a_scene_is_lit_at_all(self, sdl):
        # POV-Ray has no headlight; an unlit scene ray-traces to black.
        assert sdl.count("light_source") >= 1

    def test_lights_can_be_left_out(self, geometry):
        assert "light_source" not in tree_pov_scene(geometry, slug=SLUG, lights=False).sdl()


class TestCamera:
    def test_the_camera_frames_the_scene_from_the_front(self, scene):
        camera = tree_pov_camera(scene)
        lo, hi = scene.bounds()
        assert camera.sky == (0.0, 0.0, 1.0)
        assert camera.location[1] < lo[1]  # stands off along -y
        assert lo[2] <= camera.look_at[2] <= hi[2]  # focal plane inside the tree

    def test_zoom_dollies_in(self, scene):
        near = tree_pov_camera(scene, zoom=2.0)
        far = tree_pov_camera(scene, zoom=1.0)
        assert near.focal_distance < far.focal_distance

    def test_framing_an_empty_scene_is_an_error_not_a_nan(self):
        from quiltwright.povgen import PovScene

        with pytest.raises(ValueError, match="measurable"):
            tree_pov_camera(PovScene())


class TestReproducibility:
    def test_the_same_book_emits_the_same_file(self):
        nodes, edges = _book()
        first, _ = build_tree_pov_scene(nodes, edges, slug=SLUG, genre="philosophy")
        second, _ = build_tree_pov_scene(nodes, edges, slug=SLUG, genre="philosophy")
        assert first.sdl() == second.sdl()

    def test_a_different_season_is_a_different_file(self):
        nodes, edges = _book()
        summer, _ = build_tree_pov_scene(nodes, edges, slug=SLUG, season="summer")
        autumn, _ = build_tree_pov_scene(nodes, edges, slug=SLUG, season="autumn")
        assert summer.sdl() != autumn.sdl()

    def test_writing_lands_on_disk(self, tmp_path):
        from gutenberg_kg.povscene import write_tree_pov

        nodes, edges = _book()
        path, geometry = write_tree_pov(nodes, edges, tmp_path / "sub" / "t.pov", slug=SLUG)
        assert path.exists() and path.stat().st_size > 0
        assert geometry.skeleton.n_nodes > 0


class TestParityWithTheRasterisedTree:
    """The two backends must describe one tree, not two similar ones."""

    def test_both_backends_grow_the_same_skeleton(self):
        pv = pytest.importorskip("pyvista")
        if not can_render():
            # This is the one test here that builds a Plotter. An importable
            # pyvista is not a renderable one: on a VTK build with no OSMesa or
            # EGL fallback, constructing a render window without a GL context
            # aborts the interpreter rather than raising, taking every queued
            # test with it. See tests/_render.py.
            pytest.skip("pyvista off-screen rendering unavailable")

        from gutenberg_kg.scene import build_tree_scene

        nodes, edges = _book()
        plotter = pv.Plotter(off_screen=True)
        info = build_tree_scene(nodes, edges, plotter, slug=SLUG, genre="philosophy")
        _, geometry = build_tree_pov_scene(nodes, edges, slug=SLUG, genre="philosophy")
        plotter.close()

        assert info.skeleton is not None
        assert np.allclose(info.skeleton.points, geometry.skeleton.points)
        assert np.array_equal(info.skeleton.parents, geometry.skeleton.parents)
        assert info.title == geometry.title

    def test_analytic_sdl_is_far_smaller_than_the_tessellated_wood(self):
        pytest.importorskip("pyvista")
        from kg_utils.viz3d import tree_mesh

        nodes, edges = _book(n_sections=6, chunks_per_section=10)
        scene, geometry = build_tree_pov_scene(nodes, edges, slug=SLUG)
        wood = tree_mesh(geometry.skeleton)
        # A mesh2 dump costs roughly three floats per vertex plus three indices
        # per face, as text.  The exact constant does not matter; the order of
        # magnitude is the entire argument for emitting primitives.
        mesh_bytes = wood.n_points * 3 * 12 + wood.n_cells * 3 * 7
        assert len(scene.sdl()) < mesh_bytes / 4


class TestCli:
    """``gutenkg pov`` — the command that makes the backend reachable."""

    @staticmethod
    def _corpus(tmp_path):
        import sqlite3

        schema = (
            "CREATE TABLE nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
            "name TEXT NOT NULL, title TEXT, file_path TEXT, text TEXT, timestamp TEXT);"
            "CREATE TABLE edges (src TEXT, rel TEXT, dst TEXT);"
        )
        rows, edges = [("doc:book", "document", "book", "Book", "b.md", None, None)], []
        for s in range(4):
            rows.append((f"sec:{s}", "section", f"s{s}", f"Section {s}", "b.md", None, None))
            edges.append(("doc:book", "CONTAINS", f"sec:{s}"))
            for c in range(6):
                rows.append((f"chunk:{s}:{c}", "chunk", f"c{s}{c}", None, "b.md", "t", None))
                edges.append((f"sec:{s}", "CONTAINS", f"chunk:{s}:{c}"))

        db = tmp_path / "philosophy" / "A Treatise" / ".dockg" / "graph.sqlite"
        db.parent.mkdir(parents=True)
        con = sqlite3.connect(db)
        con.executescript(schema)
        con.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?,?)", rows)
        con.executemany("INSERT INTO edges VALUES (?,?,?)", edges)
        con.commit()
        con.close()
        return tmp_path

    def test_pov_writes_a_scene(self, tmp_path):
        pytest.importorskip("click")
        from click.testing import CliRunner

        from gutenberg_kg.cli.main import cli

        corpus = self._corpus(tmp_path / "corpus")
        out = tmp_path / "out"
        result = CliRunner().invoke(
            cli, ["pov", "--corpus", str(corpus), "--book", "Treatise", "--out", str(out)]
        )
        assert result.exit_code == 0, result.output
        written = list(out.glob("*.pov"))
        assert len(written) == 1
        assert "sphere_sweep" in written[0].read_text()

    def test_an_unknown_book_is_a_clean_error(self, tmp_path):
        pytest.importorskip("click")
        from click.testing import CliRunner

        from gutenberg_kg.cli.main import cli

        corpus = self._corpus(tmp_path / "corpus")
        result = CliRunner().invoke(cli, ["pov", "--corpus", str(corpus), "--book", "Nonesuch"])
        assert result.exit_code != 0
        assert "No ingested book matching" in result.output
