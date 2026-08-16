"""
Tests for the analytic POV-Ray backend.

Deliberately **not** gated on ``pyvista``: the whole point of this path is that
a scene can be composed without a VTK stack, and a test that imported pyvista
to check that claim would not be checking it.  The two tests that do compare
against the rasterised tree import pyvista themselves and skip without it.

It *is* gated on ``quiltwright``, which ``gutenberg_kg.povscene`` imports at
module scope for ``povgen``. Without the ``pov`` extra that import fails during
collection, which aborts the whole run instead of skipping this file. CI
installs the extra, so these tests run there.
"""

import re
import shutil
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip("quiltwright", reason="quiltwright not installed — needs the `pov` extra")

from _render import can_render  # noqa: E402
from kg_utils.viz3d import (  # noqa: E402
    LEAF_ASPECT,
    LayoutEdge,
    LayoutNode,
    leaf_frames,
    limb_paths,
    seed_from_key,
)

from gutenberg_kg.povscene import (  # noqa: E402
    build_tree_pov_scene,
    preview_spec,
    tree_camera_frame,
    tree_pov_camera,
    tree_pov_scene,
)
from gutenberg_kg.treegeom import SceneFilters, grow_tree_geometry  # noqa: E402

#: Identifiers quiltwright.povgen.swept_scene declares. Named here because this
#: module no longer chooses them — the composition moved upstream, and these
#: tests assert what gutenberg_kg still decides: the palette, the spore kinds,
#: the finishes and the defaults.
LEAF_PROTOTYPE = "Glyph"
LEAF_TEXTURE = "Tint"

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
        declared = set(re.findall(rf"#declare ({LEAF_TEXTURE}\d+) =", sdl))
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
    def test_the_key_light_is_above_the_tree_not_below_it(self, geometry, sdl):
        """
        The rig is quiltwright's now, driven with ``up=(0, 0, 1)``. This checks
        the wiring rather than the rig: pass the wrong ``up`` from here and the
        key light lands below the ground of a +z-up scene, lighting the tree
        from underneath. Read off the emitted file, since that is what POV-Ray
        reads. Emitted z is negated, so "above" is the most negative.
        """
        lights = re.findall(r"light_source \{ <([^>]*)>", sdl)
        assert lights
        key_z = np.fromstring(lights[0], sep=",")[2]
        assert key_z < -geometry.crown[:, 2].max()

    def test_the_key_light_is_on_the_same_side_as_the_camera(self, geometry, scene, sdl):
        """
        The rig and the camera are two upstream pieces that have to agree, and
        nothing makes them. `lights_from_bounds` derives its side from `up`
        alone, which for a +z-up scene is +y; `frame_tree` stands the camera
        off along -y. Wired together untold, the rig lights the back of the
        tree and the lens looks at its shadow — every structural assertion in
        this file passes and the render comes out dark.
        """
        key = np.fromstring(re.findall(r"light_source \{ <([^>]*)>", sdl)[0], sep=",")
        camera = tree_pov_camera(scene, geometry=geometry)
        focal = np.asarray(camera.look_at, dtype=float)
        eye = np.asarray(camera.location, dtype=float)
        assert (key[1] - focal[1]) * (eye[1] - focal[1]) > 0.0

    def test_a_scene_is_lit_at_all(self, sdl):
        # POV-Ray has no headlight; an unlit scene ray-traces to black.
        assert sdl.count("light_source") >= 1

    def test_lights_can_be_left_out(self, geometry):
        assert "light_source" not in tree_pov_scene(geometry, slug=SLUG, lights=False).sdl()


class TestCamera:
    def test_the_camera_is_in_pov_coordinates_not_scene_coordinates(self, scene, sdl):
        # The bug this replaces: framing was computed in the right-handed world
        # the scene is authored in and handed over unconverted, so the geometry
        # sat at negative z while the lens aimed at positive z. Every assertion
        # about it passed, because they compared right-handed against
        # right-handed — self-consistently wrong. A dual render showed POV-Ray
        # returning nothing but sky.
        #
        # So assert against the emitted file, which is the only thing POV-Ray
        # actually reads: the camera must live on the same side of z = 0 as the
        # geometry.
        camera = tree_pov_camera(scene)
        emitted_z = [float(m) for m in re.findall(r"<[^,>]+, [^,>]+, ([-\d.eE+]+)>,", sdl)]
        assert min(emitted_z) < 0, "expected the tree to be emitted at negative z"
        assert camera.look_at[2] < 0
        assert camera.location[2] < 0
        assert camera.sky == (0.0, 0.0, -1.0)  # +z up, converted

    def test_the_camera_frames_the_scene_from_the_front(self, scene):
        camera = tree_pov_camera(scene)
        lo, hi = scene.bounds()
        # Bounds are right-handed, the camera is not, so z compares against the
        # flipped interval.
        assert camera.location[1] < lo[1]  # stands off along -y
        assert -hi[2] <= camera.look_at[2] <= -lo[2]  # focal plane inside the tree

    def test_framing_matches_what_pov_camera_from_plotter_would_produce(self, scene):
        # Same convention as the helper povgen offers for the PyVista path —
        # which is the definition of "POV-Ray coordinates" here.
        from quiltwright.povgen import to_pov

        camera = tree_pov_camera(scene)
        lo, hi = scene.bounds()
        centre = (lo + hi) / 2.0
        assert np.allclose(camera.look_at, to_pov(tuple(centre)))

    def test_zoom_dollies_in(self, scene):
        near = tree_pov_camera(scene, zoom=2.0)
        far = tree_pov_camera(scene, zoom=1.0)
        assert near.focal_distance < far.focal_distance

    def test_framing_an_empty_scene_is_an_error_not_a_nan(self):
        from quiltwright.povgen import PovScene

        with pytest.raises(ValueError, match="measurable"):
            tree_pov_camera(PovScene())


class TestPreviewSpec:
    """The one-view spec the viewer's Render button traces through."""

    def test_it_is_a_single_view(self):
        spec = preview_spec(800, 600)
        assert spec.n_views == 1
        assert (spec.columns, spec.rows) == (1, 1)

    def test_the_view_cone_is_flat(self):
        # A preview is one straight-on frame. Any cone would sweep the camera
        # off-axis and show a tile that is not what the centre view contains.
        assert preview_spec().view_cone == 0.0

    def test_the_tile_is_the_requested_size(self):
        spec = preview_spec(900, 675)
        assert (spec.tile_width, spec.tile_height) == (900, 675)
        assert spec.aspect == pytest.approx(4 / 3)


class TestCameraFrame:
    """The framing rule the viewport and both renderers share."""

    def test_geometry_and_the_pov_camera_agree(self):
        # The whole point of exposing the frame: what the viewport is told to
        # look at must be what the ray-tracer frames, not merely similar.
        nodes, edges = _book()
        scene, geometry = build_tree_pov_scene(nodes, edges, slug=SLUG, genre="philosophy")
        frame = tree_camera_frame(geometry, fov=14.0)
        camera = tree_pov_camera(scene, geometry=geometry, fov=14.0)
        # Same point, expressed in POV-Ray's left-handed world: the scene is
        # written `flip-z`, so z negates and x is carried straight over. Pinned
        # explicitly because a silent handedness change would not break any
        # render — it would quietly mirror the tree.
        assert scene.handedness == "flip-z"
        assert frame.focal_point[0] == pytest.approx(camera.look_at[0], abs=1e-6)
        assert frame.focal_point[2] == pytest.approx(-camera.look_at[2], abs=1e-6)

    def test_it_frames_from_bounds_without_geometry(self):
        lo, hi = np.array([-2.0, -2.0, 0.0]), np.array([2.0, 2.0, 6.0])
        frame = tree_camera_frame(bounds=(lo, hi), fov=14.0)
        # Level view, +z up, standing off along -y.
        assert frame.up == (0.0, 0.0, 1.0)
        assert frame.position[1] < frame.focal_point[1]
        assert frame.position[2] == pytest.approx(frame.focal_point[2])

    def test_a_narrower_lens_stands_further_back(self):
        lo, hi = np.array([-2.0, -2.0, 0.0]), np.array([2.0, 2.0, 6.0])
        near = tree_camera_frame(bounds=(lo, hi), fov=40.0)
        far = tree_camera_frame(bounds=(lo, hi), fov=10.0)
        assert abs(far.position[1]) > abs(near.position[1])

    def test_nothing_to_frame_is_an_error(self):
        with pytest.raises(ValueError, match="measurable"):
            tree_camera_frame()


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


# ---------------------------------------------------------------------------
# Dual render — the check that a silhouette, not an assertion, has to pass
# ---------------------------------------------------------------------------

requires_dual_render = pytest.mark.skipif(
    shutil.which("povray") is None or not can_render(),
    reason="needs both a povray binary and a working off-screen GL stack",
)


@requires_dual_render
class TestDualRender:
    """
    Render the same tree through both backends and compare silhouettes.

    Every other test in this file inspects the SDL, which can only catch what
    it thinks to look for. This one asks the question that matters — does
    POV-Ray put the tree where PyVista does — and it is what caught
    `tree_pov_camera` handing over an unconverted camera: the SDL was perfect,
    the assertions all passed, and the render came back empty sky.

    Lighting models differ, so the comparison is of silhouettes against a
    matched black background, not of pixels.
    """

    SIZE = 300

    @staticmethod
    def _silhouette(img):
        return np.asarray(img).sum(axis=2) > 24

    def _render_both(self, tmp_path, nodes, edges):
        import pyvista as pv
        from PIL import Image
        from quiltwright.povgen import pov_camera_from_plotter
        from quiltwright.povray import camera_block

        from gutenberg_kg.scene import build_tree_scene

        plotter = pv.Plotter(off_screen=True, window_size=(self.SIZE, self.SIZE))
        build_tree_scene(nodes, edges, plotter, slug=SLUG, genre="philosophy")
        xmin, xmax, ymin, ymax, zmin, zmax = plotter.bounds
        centre = ((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2)
        plotter.camera.up = (0.0, 0.0, 1.0)
        plotter.camera.focal_point = centre
        plotter.camera.position = (centre[0], ymin - (zmax - zmin) * 1.5, centre[2])
        plotter.reset_camera()
        plotter.set_background("black")
        raster = plotter.screenshot(None, return_img=True)
        # Carry the viewpoint across rather than reframing, so the comparison
        # isolates geometry from framing policy.
        camera = pov_camera_from_plotter(plotter)
        plotter.close()

        # build_tree_scene draws no ground, so neither may this one — the
        # comparison is of geometry, and a slab in one silhouette and not the
        # other would swamp it.
        scene, _ = build_tree_pov_scene(nodes, edges, slug=SLUG, genre="philosophy", ground_size=0)
        scene.background = "#000000"
        scene.ambient_light = None
        scene.write(tmp_path / "tree.pov")
        (tmp_path / "wrap.pov").write_text(
            '#include "tree.pov"\n' + camera_block(camera, 0.0, 1.0) + "\n"
        )
        subprocess.run(
            [
                "povray",
                "+Iwrap.pov",
                "+Otree.png",
                f"+W{self.SIZE}",
                f"+H{self.SIZE}",
                "+FN",
                "-D",
                "+Q9",
                "+A0.3",
            ],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        traced = np.asarray(Image.open(tmp_path / "tree.png").convert("RGB"))
        return self._silhouette(raster), self._silhouette(traced)

    def test_the_ray_traced_tree_lands_where_the_rasterised_one_does(self, tmp_path):
        nodes, edges = _book(n_sections=5, chunks_per_section=8)
        raster, traced = self._render_both(tmp_path, nodes, edges)

        assert traced.any(), "POV-Ray rendered nothing — camera and geometry disagree"
        iou = (raster & traced).sum() / (raster | traced).sum()
        # A canopy is thousands of small disconnected blades, so a pixel of
        # misregistration costs IoU heavily; measured 0.877 with the camera
        # carried across. Far below this and the two are not the same tree.
        assert iou > 0.75, f"silhouette IoU {iou:.3f}"

    def test_both_silhouettes_have_the_same_extent(self, tmp_path):
        nodes, edges = _book(n_sections=5, chunks_per_section=8)
        raster, traced = self._render_both(tmp_path, nodes, edges)

        def bbox(mask):
            ys, xs = np.nonzero(mask)
            return ys.min(), ys.max(), xs.min(), xs.max()

        # Extent is what pins the lens: a wrong FOV, a wrong dolly or a
        # mirrored axis all move these edges, and none of them survive 3 px.
        assert np.allclose(bbox(raster), bbox(traced), atol=3)

    def test_our_own_framing_actually_points_at_the_tree(self, tmp_path):
        # The carried-camera tests above isolate geometry, which means they say
        # nothing about tree_pov_camera — and tree_pov_camera is exactly where
        # the unconverted-camera bug lived. Render through our own framing and
        # insist the tree is in the picture.
        from PIL import Image
        from quiltwright.povray import camera_block

        nodes, edges = _book(n_sections=5, chunks_per_section=8)
        # build_tree_scene draws no ground, so neither may this one — the
        # comparison is of geometry, and a slab in one silhouette and not the
        # other would swamp it.
        scene, _ = build_tree_pov_scene(nodes, edges, slug=SLUG, genre="philosophy", ground_size=0)
        scene.background = "#000000"
        scene.ambient_light = None
        scene.write(tmp_path / "tree.pov")
        camera = tree_pov_camera(scene, fov=30.0)
        (tmp_path / "wrap.pov").write_text(
            '#include "tree.pov"\n' + camera_block(camera, 0.0, 1.0) + "\n"
        )
        subprocess.run(
            [
                "povray",
                "+Iwrap.pov",
                "+Otree.png",
                f"+W{self.SIZE}",
                f"+H{self.SIZE}",
                "+FN",
                "-D",
                "+Q9",
                "+A0.3",
            ],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        traced = self._silhouette(Image.open(tmp_path / "tree.png").convert("RGB"))

        assert traced.any(), "own framing rendered an empty sky — camera and geometry disagree"
        # A framed hero shot: the tree is neither a speck nor the whole frame.
        assert 0.005 < traced.mean() < 0.60, f"coverage {traced.mean():.2%}"
        ys, xs = np.nonzero(traced)
        # And it is roughly centred, not clipped against one edge.
        assert abs(ys.mean() - self.SIZE / 2) < self.SIZE * 0.25
        assert abs(xs.mean() - self.SIZE / 2) < self.SIZE * 0.25


class TestGroundAndLighting:
    """
    The three dials that decide whether the render looks like a tree standing
    somewhere, or a dark shape floating in the void.  None of this is caught by
    the SDL-shape tests above — a scene can be structurally perfect and visually
    unusable, which is exactly what the first Pepys render was.
    """

    @staticmethod
    def _box(sdl):
        """The emitted ground slab's two corners, or None."""
        m = re.search(r"^box \{ <([^>]*)>, <([^>]*)>", sdl, re.MULTILINE)
        return (
            None
            if m is None
            else (
                np.fromstring(m.group(1), sep=","),
                np.fromstring(m.group(2), sep=","),
            )
        )

    @staticmethod
    def _light_levels(sdl):
        return [float(m) for m in re.findall(r"light_source \{ <[^>]*> color rgb <([\d.]+)", sdl)]

    def test_a_ground_slab_is_laid_by_default(self, geometry):
        assert self._box(tree_pov_scene(geometry, slug=SLUG).sdl()) is not None

    def test_ground_can_be_omitted(self, geometry):
        assert self._box(tree_pov_scene(geometry, slug=SLUG, ground_size=0).sdl()) is None

    def test_the_tree_stands_on_the_slab_rather_than_over_it(self, geometry):
        # The trunk's root node is at z = 0, so the slab's top face must be too.
        # POV-Ray sees z negated, so "top" is the smaller emitted z.
        lo, hi = self._box(tree_pov_scene(geometry, slug=SLUG).sdl())
        assert min(lo[2], hi[2]) == pytest.approx(0.0)

    def test_the_slab_scales_with_the_crown(self, geometry):
        """One multiplier has to suit a sonnet and a nine-year diary alike."""
        narrow = self._box(tree_pov_scene(geometry, slug=SLUG, ground_size=2.0).sdl())
        wide = self._box(tree_pov_scene(geometry, slug=SLUG, ground_size=6.0).sdl())
        assert (wide[1][0] - wide[0][0]) > 2.5 * (narrow[1][0] - narrow[0][0])

    def test_only_the_key_light_casts_a_shadow(self, geometry):
        """Three casting lights would give the tree three overlapping shadows."""
        sdl = tree_pov_scene(geometry, slug=SLUG).sdl()
        lights = re.findall(r"light_source \{.*", sdl)
        assert len(lights) == 3
        assert sum("shadowless" not in light for light in lights) == 1

    def test_the_ground_does_not_push_the_lights_away_from_the_tree(self, geometry):
        """
        Regression: the rig is sized from scene.bounds(), and the slab is wider
        than the crown.  Building the ground first made the "scene radius" the
        slab's half-diagonal, which flattened the tree and shrank its shadow to
        nothing.  Lights are placed before the floor is laid.
        """
        lit = re.findall(r"light_source \{ <([^>]*)>", tree_pov_scene(geometry, slug=SLUG).sdl())
        bare = re.findall(
            r"light_source \{ <([^>]*)>",
            tree_pov_scene(geometry, slug=SLUG, ground_size=0).sdl(),
        )
        assert lit == bare

    def test_the_scene_is_lit_from_above_the_canopy(self, geometry, sdl):
        """Every light clears the crown; none of them lights the tree from below."""
        emitted = [np.fromstring(m, sep=",") for m in re.findall(r"light_source \{ <([^>]*)>", sdl)]
        assert emitted
        top = geometry.crown[:, 2].max()
        assert all(light[2] < -top * 0.5 for light in emitted)

    def test_brightness_scales_the_whole_rig(self, geometry):
        dim = self._light_levels(tree_pov_scene(geometry, slug=SLUG, brightness=1.0).sdl())
        bright = self._light_levels(tree_pov_scene(geometry, slug=SLUG, brightness=3.0).sdl())
        assert bright == pytest.approx([level * 3.0 for level in dim])

    def test_the_default_is_brighter_than_unity(self, geometry):
        """Measured on Pepys: a unit key renders a correct, unreadable tree."""
        from gutenberg_kg.povscene import DEFAULT_BRIGHTNESS

        assert DEFAULT_BRIGHTNESS > 1.0
        assert max(self._light_levels(tree_pov_scene(geometry, slug=SLUG).sdl())) > 1.0

    def test_sky_overrides_the_season_background(self, geometry):
        sdl = tree_pov_scene(geometry, slug=SLUG, sky="#6d7f9e").sdl()
        r, g, b = (int("6d7f9e"[i : i + 2], 16) / 255 for i in (0, 2, 4))
        m = re.search(r"background \{ color rgb <([^>]*)>", sdl)
        assert np.allclose(np.fromstring(m.group(1), sep=","), [r, g, b], atol=1e-4)

    def test_the_season_sky_is_kept_when_none_is_given(self, geometry):
        sdl = tree_pov_scene(geometry, slug=SLUG).sdl()
        assert "background {" in sdl
        assert tree_pov_scene(geometry, slug=SLUG, sky="#ffffff").sdl() != sdl


class TestFramingIgnoresTheGround:
    def test_the_camera_frames_the_tree_not_the_floor(self, geometry):
        """
        Regression from making the ground default-on: tree_pov_camera read
        scene.bounds(), so once a slab three crown-widths across was in the
        scene it framed mostly floor and the tree came out small and high.
        """
        scene = tree_pov_scene(geometry, slug=SLUG, ground_size=6.0)
        framed = tree_pov_camera(scene, geometry=geometry, fov=26.0)
        floored = tree_pov_camera(scene, fov=26.0)
        assert framed.focal_distance < floored.focal_distance

    def test_framing_is_unchanged_by_how_wide_the_slab_is(self, geometry):
        narrow = tree_pov_scene(geometry, slug=SLUG, ground_size=2.0)
        wide = tree_pov_scene(geometry, slug=SLUG, ground_size=8.0)
        a = tree_pov_camera(narrow, geometry=geometry, fov=26.0)
        b = tree_pov_camera(wide, geometry=geometry, fov=26.0)
        assert a.location == pytest.approx(b.location)
        assert a.look_at == pytest.approx(b.look_at)


class TestTheLensSetsTheStandoff:
    """
    The regression the Pepys render caught and the rest of this file missed:
    framing moved upstream to ``frame_tree``, whose default rule is a fixed
    multiple of the subject's height.  PyVista callers get away with that
    because ``plotter.reset_camera()`` fits afterwards; POV-Ray has no such
    pass, so the tree came out cropped top and bottom.  Every assertion here
    still passed, because a badly-fitted frame is a structurally valid one.
    """

    @staticmethod
    def _subtended(camera, geometry) -> float:
        """Vertical angle the crown subtends from the camera, in degrees."""
        from quiltwright.povgen import to_pov

        crown = np.vstack([np.atleast_2d(geometry.crown), np.zeros(3)])
        pov = np.array([to_pov(tuple(p)) for p in crown])
        eye = np.asarray(camera.location, dtype=float)
        centre = np.asarray(camera.look_at, dtype=float)
        radius = float(np.linalg.norm(pov - centre, axis=1).max())
        return 2.0 * np.degrees(np.arctan(radius / np.linalg.norm(centre - eye)))

    @pytest.mark.parametrize("fov", [14.0, 26.0, 60.0])
    def test_the_crown_fits_the_lens(self, geometry, fov):
        camera = tree_pov_camera(tree_pov_scene(geometry, slug=SLUG), geometry=geometry, fov=fov)
        assert self._subtended(camera, geometry) <= fov + 1e-6

    @pytest.mark.parametrize("fov", [14.0, 26.0, 60.0])
    def test_the_crown_is_not_lost_in_the_lens(self, geometry, fov):
        # The other half of fitting: a frame that merely contains the subject
        # is satisfied by standing a mile back. The bounding sphere is the
        # tightest thing a single distance can fit, so it should nearly fill.
        camera = tree_pov_camera(tree_pov_scene(geometry, slug=SLUG), geometry=geometry, fov=fov)
        assert self._subtended(camera, geometry) > 0.7 * fov

    def test_a_narrower_lens_stands_further_back(self, geometry):
        scene = tree_pov_scene(geometry, slug=SLUG)
        near = tree_pov_camera(scene, geometry=geometry, fov=60.0)
        far = tree_pov_camera(scene, geometry=geometry, fov=14.0)
        assert far.focal_distance > near.focal_distance
