"""
povscene.py — a book's knowledge tree as analytic POV-Ray primitives.

The PyVista path in :mod:`gutenberg_kg.scene` tessellates: a limb becomes a
tubed spline of a few thousand triangles, a leaf becomes a glyphed ellipsoid.
That is the right shape for a live viewport, and the wrong one for a
ray-tracer.  By the time geometry reaches ``pv.Plotter`` its silhouettes are
already faceted, and a mesh dump re-parses those facets once per view — 48
times for a Portrait quilt.

This module describes the same tree *analytically* instead.  A limb is a
``sphere_sweep`` through its smoothed path; a leaf is one instance of a single
declared ellipsoid.  The tree is not approximated at any zoom, and the file is
one to two orders of magnitude smaller than the equivalent triangle dump.

The exception is bark.  A ``sphere_sweep`` has no texture coordinates, so by
default the wood is :func:`kg_utils.viz3d.bark_sweep` -- the same UV-mapped
sweep the PyVista path draws -- written as a ``mesh2`` wearing the species'
bark photograph.  ``species_look=False`` keeps the plain analytic sweeps.

Both backends start from :func:`gutenberg_kg.treegeom.grow_tree_geometry`, so
the ray-traced tree is the *same* tree as the rasterised one — same skeleton,
same clung leaves, same halo — not a second implementation that has to be kept
in step by hand.  Nothing here imports PyVista, so a headless render farm can
write a scene with no VTK stack installed at all.

The scene carries **no camera**: ``quiltwright.povray.render_pov_quilt``
appends one off-axis camera per view, and POV-Ray honours the last camera it
parses.  Use :func:`tree_pov_camera` to frame the tree and hand the result to
the renderer.

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np
from kg_utils.viz3d import (
    LEAF_ASPECT,
    LayoutEdge,
    LayoutNode,
    bark_sweep,
    frame_tree,
    leaf_frames,
    limb_paths,
    seed_from_key,
)
from PIL import Image
from quiltwright.povgen import (
    Finish,
    ImageTexture,
    Instance,
    Mesh2,
    PovScene,
    Texture,
    Union,
    parse_color,
    pov_camera_from_frame,
    swept_scene,
)
from quiltwright.povray import PovCamera, QuiltSpec

from gutenberg_kg.leafshapes import LEAF_SHAPES, leaf_outline
from gutenberg_kg.treegeom import (
    BARK_TILE,
    DEFAULT_SEASON,
    GROUND_COLOR,
    KIND_COLOR,
    SPORE_OPACITY,
    SceneFilters,
    TreeGeometry,
    bark_texture_path,
    grow_tree_geometry,
    species_leaf_frames,
)

logger = logging.getLogger(__name__)

__author__ = "Eric G. Suchanek, PhD"

#: Bark finish.  Wood is matte — a phong highlight on a trunk reads as plastic,
#: which is exactly the tell that makes a ray-traced tree look worse than the
#: rasterised one it replaced.
BARK_FINISH = Finish(ambient=0.12, diffuse=0.85, phong=None)

#: Finish for the photographed bark.  Dimmer than :data:`BARK_FINISH`: the
#: photographs are far lighter than the flat wood colour that finish was tuned
#: for, and at 0.85 under :data:`DEFAULT_BRIGHTNESS` they clip toward white.
#: 0.55 chosen by eye against 0.85 and 0.40 on Hamlet's willow.
BARK_IMAGE_FINISH = Finish(ambient=0.12, diffuse=0.55, phong=None)

#: How far the season's wood colour is lifted toward white before it tints the
#: bark photograph -- the web forest's figure (``Trees.tsx``), so the photo
#: carries the bark and the season only shades it.
BARK_TINT_LIFT: float = 0.55

#: Bark relief, as POV-Ray ``bump_size`` on the photograph's own brightness.
BARK_BUMP: float = 0.4

#: POV-Ray version the species look declares.  Undeclared, POV-Ray lights the
#: scene in its pre-3.7 mode, which washes the bark photograph out.
SPECIES_POV_VERSION = "3.7"

#: Foliage finish.  A weak, wide highlight: leaves are waxy, not wet.
LEAF_FINISH = Finish(ambient=0.18, diffuse=0.78, phong=0.15, phong_size=12.0)

#: Spore finish.  High ambient so the halo glows rather than being lit — these
#: are annotation, not botany, and they must stay legible against a dark sky.
SPORE_FINISH = Finish(ambient=0.55, diffuse=0.45, phong=0.3, phong_size=60.0)

#: Ground finish.  Matte, and deliberately dim: its whole job is to catch the
#: tree's shadow.  ``diffuse`` is low because it is multiplied by a key light
#: running at :data:`DEFAULT_BRIGHTNESS` — at 0.7 the slab clipped to a flat
#: lime that pulled the eye straight off the tree.
GROUND_FINISH = Finish(ambient=0.10, diffuse=0.42, phong=None)

#: Key-light multiplier.  Not ``1.0``: a canopy of thousands of small blades
#: self-shadows heavily, and the wood is a dark brown against a dark sky, so a
#: unit key renders a tree that is technically correct and visually black.
#: Measured on Pepys — 9,993 leaves — where 1.0 left the trunk unreadable.
DEFAULT_BRIGHTNESS: float = 2.6

#: Global ambient.  Lifts the shadow side just enough that the far half of the
#: crown is not a silhouette; higher flattens the form.
AMBIENT_LIGHT = "#3a3a44"

#: Default ground slab edge, as a multiple of the crown's width.  Wide enough
#: that the shadow falls on it rather than off its edge, narrow enough to stay
#: inside the light-field depth budget.
DEFAULT_GROUND: float = 3.0

#: Which side of the tree the camera is on, so the key light goes there rather
#: than behind it.  This is not a free choice: :func:`kg_utils.viz3d.frame_tree`
#: stands the camera off along ``-y``, and a rig that derives its own side from
#: ``up`` alone picks ``+y`` for a ``+z``-up scene — the far side.  The scene is
#: then perfectly lit and the picture is dark.
CAMERA_SIDE: tuple[float, float, float] = (0.0, -1.0, 0.0)


def bark_tint(wood: str) -> str:
    """
    The season's wood colour as the web forest tints its bark with it.

    three.js mixes colours in linear light, so the lift toward white is taken
    there and the result encoded back to sRGB hex.

    :param wood: The season's wood colour, ``"#rrggbb"``.
    :return: The tint, ``"#rrggbb"``.
    """
    rgb = np.asarray(parse_color(wood))
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    linear += (1.0 - linear) * BARK_TINT_LIFT
    srgb = np.where(linear <= 0.0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - 0.055)
    return "#" + "".join(f"{round(float(c) * 255):02x}" for c in srgb)


def add_species_leaves(scene: PovScene, geometry: TreeGeometry) -> None:
    """
    Hang the tree's leaves as the web forest does, in the species' outline.

    Each leaf is placed and sized by
    :func:`~gutenberg_kg.treegeom.species_leaf_frames` -- the same frames the
    PyVista path uses -- and drawn as one flat ``polygon`` of the species'
    outline (:mod:`gutenberg_kg.leafshapes`), declared once and instanced per
    leaf.

    :param scene: Scene to add the leaves to.
    :param geometry: The placed tree.
    """
    palette = geometry.palette.foliage
    tint = np.asarray(geometry.leaf_tint, dtype=int)
    centres, half, across, blades, faces = species_leaf_frames(
        geometry.leaf_points,
        geometry.skeleton,
        size=geometry.leaf_radius,
        tint=tint,
        n_tints=len(palette),
    )
    if not len(centres):
        return
    outline = leaf_outline(LEAF_SHAPES.get(geometry.species, LEAF_SHAPES["chestnut"]))
    ring = [*outline, outline[0]]
    points = ", ".join(f"<{x:.5g}, {y:.5g}>" for x, y in ring)
    scene.declare("Leaf", f"polygon {{ {len(ring)}, {points} }}")

    for i, colour in enumerate(palette):
        members = [
            Instance(
                "Leaf",
                translate=centres[k],
                scale=float(half[k]),
                matrix=np.stack([across[k], blades[k], faces[k]]),
            )
            for k in np.flatnonzero(tint == i)
        ]
        if members:
            scene.declare_texture(f"Leaf{i}", Texture(color=colour, finish=LEAF_FINISH))
            scene.add(Union(members, texture=f"Leaf{i}"))


def tree_pov_scene(
    geometry: TreeGeometry,
    *,
    subdivisions: int = 4,
    slug: str = "tree",
    cling: float = 0.7,
    ground_size: float = DEFAULT_GROUND,
    lights: bool = True,
    brightness: float = DEFAULT_BRIGHTNESS,
    sky: str | None = None,
    species_look: bool = True,
) -> PovScene:
    """
    Turn a placed :class:`~gutenberg_kg.treegeom.TreeGeometry` into POV-Ray SDL.

    The composition is :func:`quiltwright.povgen.swept_scene`: limbs are its
    swept paths, leaves its oriented instances, spores its point clouds.  What
    is left here is the part that is actually about books — the season's
    palette, which node kinds become spores, and the finishes — which is the
    only part another KG module would not share.

    The scene is authored **right-handed** (``+z`` up, as everything else in
    this repo is) and emitted left-handed; ``povgen`` negates ``z`` on the way
    out, cameras included, so the ray-traced image matches the PyVista render
    rather than mirroring it.

    :param geometry: Placed tree from
        :func:`~gutenberg_kg.treegeom.grow_tree_geometry`.
    :param subdivisions: Spline samples per skeleton segment.  This is the one
        dial that trades file size for limb smoothness; 4 matches the PyVista
        path.
    :param slug: Book slug, written into the file header and used to seed the
        leaf roll jitter so the canopy matches the rasterised one.
    :param cling: How far each leaf is drawn toward its nearest twig, ``0`` to
        ``1``.  Must match the PyVista path's default for the two renders to
        agree.
    :param ground_size: Edge length of the ground slab, as a multiple of the
        crown's own width; ``0`` omits it.  **On by default, unlike
        :func:`~gutenberg_kg.scene.build_tree_scene`.**  That path omits its
        ground because it draws an effectively infinite plane, which guarantees
        off-budget disparity at the horizon; this slab is finite and sized to
        the crown, so it carries no such cost — and a ray-traced tree with no
        contact shadow reads as floating, which the rasterised one does not,
        since VTK's headlight casts nothing anyway.  Sized relative to the
        crown rather than in scene units, so one value works for a sonnet and
        for a nine-year diary.
    :param lights: Place a three-point rig from the scene bounds.  POV-Ray has
        no equivalent of VTK's headlight, so a scene with no lights at all
        renders black.
    :param brightness: Key-light multiplier.  See :data:`DEFAULT_BRIGHTNESS`
        for why this is not ``1.0``.
    :param sky: Background colour override, ``"#rrggbb"``.  ``None`` keeps the
        season's own sky, which is chosen for a dark hero shot.
    :param species_look: The web forest's look.  The wood wears the species'
        bark photograph, tinted by the season (:func:`bark_tint`), as a
        ``mesh2`` from :func:`kg_utils.viz3d.bark_sweep`; the leaves hang as
        the web hangs them, in the species' outline
        (:func:`add_species_leaves`); and the scene declares ``#version 3.7``
        so the photograph keeps its contrast.  ``False`` draws plain
        ``sphere_sweep`` limbs in the season's wood colour and ellipsoid
        leaves from :func:`kg_utils.viz3d.leaf_frames`, undeclared as before.
        The ``.pov`` names the photograph by file name, and
        ``PovScene.write`` copies it alongside.
    :return: The composed :class:`~quiltwright.povgen.PovScene`.
    """
    palette = geometry.palette
    bark_path = bark_texture_path(geometry.species) if species_look else None
    if bark_path is not None:
        with Image.open(bark_path) as image:
            width, height = image.size
        wood = bark_sweep(
            geometry.skeleton, aspect=height / width, tile=BARK_TILE, subdivisions=subdivisions
        )
        sweeps: Mesh2 | list[tuple[np.ndarray, np.ndarray]] = Mesh2(
            vertices=wood.points, faces=wood.faces, normals=wood.normals, uv=wood.uv
        )
        bark: ImageTexture | None = ImageTexture(
            bark_path, tint=bark_tint(palette.wood), bump=BARK_BUMP, finish=BARK_IMAGE_FINISH
        )
    else:
        sweeps = limb_paths(geometry.skeleton, subdivisions=subdivisions)
        bark = None
    clouds = [
        (points, radius, KIND_COLOR[kind], SPORE_OPACITY)
        for kind, (points, radius) in geometry.spores.items()
    ]
    scene = swept_scene(
        sweeps,
        sweep_color=palette.wood,
        sweep_finish=BARK_FINISH,
        sweep_texture=bark,
        instances=None
        if species_look
        else leaf_frames(
            geometry.leaf_points,
            geometry.skeleton,
            size=geometry.leaf_radius,
            cling=cling,
            seed=seed_from_key(slug + ":leaves"),
        ),
        instance_shape=LEAF_ASPECT,
        instance_radius=geometry.leaf_radius,
        instance_palette=palette.foliage,
        # .tolist(): swept_scene takes Sequence[int], and an ndarray is not one
        # as far as the type checker is concerned.
        instance_index=np.asarray(geometry.leaf_tint, dtype=int).tolist(),
        instance_finish=LEAF_FINISH,
        clouds=clouds,
        cloud_finish=SPORE_FINISH,
        up=(0.0, 0.0, 1.0),
        sky=sky or palette.sky[0],
        ambient=AMBIENT_LIGHT,
        lights=lights,
        ground=ground_size,
        # The trunk's root is at z = 0; the swept bounds are padded by its
        # radius, so left to infer the floor would sit a trunk-radius low.
        ground_base=0.0,
        ground_color=GROUND_COLOR,
        ground_finish=GROUND_FINISH,
        brightness=brightness,
        key_side=CAMERA_SIDE,
        rim_light=True,
        comment=(
            f"{slug} — GutenbergKG knowledge tree\n"
            f"{geometry.title}\n"
            f"Grown by kg_utils.viz3d, composed by quiltwright.povgen.swept_scene."
        ),
    )
    if species_look:
        add_species_leaves(scene, geometry)
        scene.version = SPECIES_POV_VERSION
    return scene


def build_tree_pov_scene(
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
    subdivisions: int = 4,
    ground_size: float = DEFAULT_GROUND,
    brightness: float = DEFAULT_BRIGHTNESS,
    sky: str | None = None,
    species_look: bool = True,
    progress: Callable[[str], None] | None = None,
) -> tuple[PovScene, TreeGeometry]:
    """
    Grow one book and compose it as a POV-Ray scene, in one call.

    The POV-Ray counterpart of
    :func:`~gutenberg_kg.scene.build_tree_scene`.  Same arguments, same tree;
    the difference is that nothing is tessellated and no plotter is touched.

    :param nodes: Nodes of one book (IDs namespaced by *slug*).
    :param edges: Edges of the same book.
    :param slug: Book slug; seeds growth so the tree is reproducible.
    :param genre: Genre name, which selects the tropism silhouette.
    :param entry_times: ``{document id: ISO timestamp}``; grows a dated book's
        limbs as calendar years.
    :param filters: Only ``show_entities`` and ``show_topics`` are consulted.
    :param season: Key into :data:`~gutenberg_kg.treegeom.SEASONS`.
    :param tip_radius: Radius of leaf-bearing twigs, in scene units.
    :param leaf_size: Leaf radius before density scaling.
    :param subdivisions: Spline samples per skeleton segment.
    :param ground_size: Ground slab edge as a multiple of crown width; ``0``
        omits it.  On by default — a tree with no contact shadow floats.
    :param brightness: Key-light multiplier.
    :param sky: Background colour override, ``"#rrggbb"``.
    :param species_look: Bark-textured wood; see :func:`tree_pov_scene`.
    :param progress: Optional ``fn(message)`` progress callback.
    :return: ``(scene, geometry)`` — the geometry is returned because framing
        the camera needs the crown, and regrowing the tree to get it would be
        both slow and a chance for the two to disagree.
    """
    report = progress or (lambda _msg: None)
    geometry = grow_tree_geometry(
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
    wood = "bark" if species_look else "sphere sweeps"
    report(f"Writing {geometry.skeleton.n_nodes:,} skeleton nodes as {wood}...")
    scene = tree_pov_scene(
        geometry,
        subdivisions=subdivisions,
        slug=slug,
        ground_size=ground_size,
        brightness=brightness,
        sky=sky,
        species_look=species_look,
    )
    report(f"Composed {len(scene):,} POV-Ray objects.")
    return scene, geometry


def preview_spec(width: int = 1200, height: int = 900) -> QuiltSpec:
    """
    A one-view :class:`~quiltwright.QuiltSpec` — a plain ray-traced image.

    ``render_pov_quilt`` is the only entry point that drives POV-Ray and
    assembles the result, and it is parameterised entirely by the spec.  A
    1x1 grid with a zero view cone therefore gives a single straight-on frame
    through exactly the code path a quilt uses, rather than a second
    render function that could drift from it.  What the preview shows is what
    a tile of the quilt will contain.

    :param width: Image width in pixels.
    :param height: Image height in pixels.
    :return: A spec whose ``n_views`` is 1.
    """
    return QuiltSpec(
        columns=1,
        rows=1,
        quilt_width=int(width),
        quilt_height=int(height),
        aspect=float(width) / float(height),
        view_cone=0.0,
    )


def tree_camera_frame(
    geometry: TreeGeometry | None = None,
    *,
    bounds: tuple[np.ndarray, np.ndarray] | None = None,
    fov: float = 14.0,
):
    """
    The framing rule, before either renderer's coordinate conventions.

    :func:`tree_pov_camera` converts this into POV-Ray's left-handed world;
    a PyVista caller can assign ``(position, focal_point, up)`` straight to
    ``plotter.camera_position``.  Exposing the frame itself is what lets the
    interactive viewport show the *same* composition the ray-tracer will use,
    instead of two framings that agree only by eye.

    :param geometry: The placed tree.  **Pass this** — see
        :func:`tree_pov_camera` for why framing the crown beats framing the
        scene.
    :param bounds: ``(lo, hi)`` fallback when no geometry is available.
    :param fov: Vertical field of view in degrees.
    :return: A ``kg_utils.viz3d.CameraFrame``.
    :raises ValueError: If neither *geometry* nor *bounds* is usable.
    """
    if geometry is not None:
        return frame_tree(geometry.crown, fov=fov)
    if bounds is None:
        raise ValueError("nothing measurable to frame: pass geometry or bounds")
    lo, hi = bounds
    return frame_tree(np.vstack([lo, hi]), fov=fov, include_root=False)


def tree_pov_camera(
    scene: PovScene,
    *,
    geometry: TreeGeometry | None = None,
    fov: float = 14.0,
    zoom: float = 1.0,
) -> PovCamera:
    """
    Frame the tree for a hero shot, in POV-Ray coordinates.

    Both halves now come from upstream: :func:`kg_utils.viz3d.frame_tree` is
    the framing rule — one copy, shared with ``gutenkg quilt`` and every other
    consumer — and :func:`quiltwright.povgen.pov_camera_from_frame` performs
    the conversion into POV-Ray's left-handed world.

    :param scene: A composed scene, used only when *geometry* is absent.
    :param geometry: The placed tree.  **Pass this.**  Framing from the scene
        means framing whatever is in it, and the ground slab is three
        crown-widths across.
    :param fov: Vertical field of view in degrees.  It sets the standoff as
        well as the lens: POV-Ray has no ``reset_camera()``, so the distance
        that fits the crown has to be computed up front or the tree overflows
        a narrow lens and swims in a wide one.
    :param zoom: Dolly toward the focal point after framing.
    :return: The camera, in POV-Ray coordinates.
    :raises ValueError: If there is nothing measurable to frame.
    """
    frame = tree_camera_frame(
        geometry,
        bounds=None if geometry is not None else scene.bounds(),
        fov=fov,
    )
    return pov_camera_from_frame(frame, fov=fov, zoom=zoom, handedness=scene.handedness)


def write_tree_pov(
    nodes: list[LayoutNode],
    edges: list[LayoutEdge],
    path: str | Path,
    *,
    slug: str,
    progress: Callable[[str], None] | None = None,
    **kwargs,
) -> tuple[Path, TreeGeometry]:
    """
    Grow a book and write it to a ``.pov`` file.

    :param nodes: Nodes of one book.
    :param edges: Edges of the same book.
    :param path: Destination ``.pov`` file; parent directories are created.
    :param slug: Book slug.
    :param progress: Optional ``fn(message)`` progress callback.
    :param kwargs: Passed through to :func:`build_tree_pov_scene`.
    :return: ``(written path, geometry)``.
    """
    scene, geometry = build_tree_pov_scene(nodes, edges, slug=slug, progress=progress, **kwargs)
    written = scene.write(path)
    if progress:
        progress(f"Wrote {written} ({written.stat().st_size / 1024:.0f} KB)")
    return written, geometry
