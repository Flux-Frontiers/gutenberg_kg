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
from dataclasses import replace
from pathlib import Path

import numpy as np
from kg_utils.viz3d import (
    LEAF_ASPECT,
    LayoutEdge,
    LayoutNode,
    leaf_frames,
    limb_paths,
    seed_from_key,
)
from quiltwright.povgen import (
    Box,
    Finish,
    LightSource,
    PovScene,
    Sphere,
    Texture,
    Union,
    instances_from_frames,
    sphere_sweeps_from_paths,
    spheres_from_points,
)
from quiltwright.povray import PovCamera

from gutenberg_kg.treegeom import (
    DEFAULT_SEASON,
    GROUND_COLOR,
    KIND_COLOR,
    SPORE_OPACITY,
    SceneFilters,
    TreeGeometry,
    grow_tree_geometry,
)

logger = logging.getLogger(__name__)

__author__ = "Eric G. Suchanek, PhD"

#: Declared name of the leaf prototype.  One ``#declare`` for a whole canopy:
#: POV-Ray parses the ellipsoid once and each leaf costs a single line.
LEAF_PROTOTYPE = "GutenLeaf"

#: Bark finish.  Wood is matte — a phong highlight on a trunk reads as plastic,
#: which is exactly the tell that makes a ray-traced tree look worse than the
#: rasterised one it replaced.
BARK_FINISH = Finish(ambient=0.12, diffuse=0.85, phong=None)

#: Foliage finish.  A weak, wide highlight: leaves are waxy, not wet.
LEAF_FINISH = Finish(ambient=0.18, diffuse=0.78, phong=0.15, phong_size=12.0)

#: Spore finish.  High ambient so the halo glows rather than being lit — these
#: are annotation, not botany, and they must stay legible against a dark sky.
SPORE_FINISH = Finish(ambient=0.55, diffuse=0.45, phong=0.3, phong_size=60.0)


def tree_lights(lo: np.ndarray, hi: np.ndarray, *, intensity: float = 1.0) -> list[LightSource]:
    """
    A three-point rig for a **+z-up** tree, sized to the scene bounds.

    ``quiltwright.povgen.lights_from_bounds`` is the general helper, but its
    offsets are written for a ``+y``-up world: its key light sits at
    ``+1.6y, -1.4z``, which in this repo's ``+z``-up world is level with the
    trunk and *below* the ground.  A tree lit from underneath is not a subtle
    difference, so the rig is rebuilt here in the world the rest of the scene
    uses rather than being wrestled into the helper's.

    Key from the upper front right, shadowless fill from the left to open the
    shadows without doubling them, and a dim back light so the crown separates
    from the sky instead of silhouetting into it.

    :param lo: Lower bound corner, right-handed.
    :param hi: Upper bound corner, right-handed.
    :param intensity: Key light brightness multiplier.
    :return: The light sources, key first.
    """
    lo_a = np.asarray(lo, dtype=float)
    hi_a = np.asarray(hi, dtype=float)
    centre = (lo_a + hi_a) / 2.0
    radius = float(np.linalg.norm(hi_a - lo_a)) / 2.0 or 1.0

    def level(fraction: float) -> tuple[float, float, float]:
        value = intensity * fraction
        return (value, value, value)

    # The camera looks along +y from -y, so "front" is -y.
    return [
        LightSource(position=tuple(centre + np.array([1.4, -1.5, 1.6]) * radius), color=level(1.0)),
        LightSource(
            position=tuple(centre + np.array([-1.6, -1.0, 0.7]) * radius),
            color=level(0.35),
            shadowless=True,
        ),
        LightSource(
            position=tuple(centre + np.array([-0.3, 1.7, 1.3]) * radius),
            color=level(0.25),
            shadowless=True,
        ),
    ]


def _leaf_texture_names(geometry: TreeGeometry) -> list[str]:
    """
    One declared texture identifier per foliage colour.

    :param geometry: The placed tree.
    :return: Identifiers parallel to ``geometry.palette.foliage``.
    """
    return [f"GutenLeafTex{i}" for i in range(len(geometry.palette.foliage))]


def tree_pov_scene(
    geometry: TreeGeometry,
    *,
    subdivisions: int = 4,
    slug: str = "tree",
    cling: float = 0.7,
    ground_size: float = 0.0,
    lights: bool = True,
) -> PovScene:
    """
    Turn a placed :class:`~gutenberg_kg.treegeom.TreeGeometry` into POV-Ray SDL.

    Wood becomes one ``sphere_sweep`` per root-to-tip path, carrying the pipe
    model's per-node radii; foliage becomes one instance of
    :data:`LEAF_PROTOTYPE` per leaf, oriented along its twig; spores become
    plain spheres.  Leaves are grouped into one ``union`` per foliage colour so
    a season's palette costs one texture per colour rather than one per leaf.

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
    :param ground_size: Edge length of a ground plane; ``0`` omits it.  An
        effectively infinite plane guarantees off-budget disparity at the
        horizon, which is why the tree scene leaves it out by default.
    :param lights: Place a three-point rig from the scene bounds.  POV-Ray has
        no equivalent of VTK's headlight, so a scene with no lights at all
        renders black.
    :return: The composed :class:`~quiltwright.povgen.PovScene`.
    """
    palette = geometry.palette
    scene = PovScene(
        background=palette.sky[0],
        ambient_light="#2a2a30",
        comment=(
            f"{slug} — GutenbergKG knowledge tree\n"
            f"{geometry.title}\n"
            f"Grown by kg_utils.viz3d, emitted by gutenberg_kg.povscene."
        ),
    )

    bark = Texture(color=palette.wood, finish=BARK_FINISH)
    scene.declare_texture("GutenBark", bark)

    # The leaf prototype is a unit sphere flattened by LEAF_ASPECT, the same
    # scale the PyVista glyph applies to its prototype.  Instancing it means
    # the canopy is one declared object plus a line per leaf.
    scene.declare(LEAF_PROTOTYPE, Sphere(centre=(0.0, 0.0, 0.0), radius=1.0))
    leaf_textures = _leaf_texture_names(geometry)
    for name, color in zip(leaf_textures, palette.foliage, strict=True):
        scene.declare_texture(name, Texture(color=color, finish=LEAF_FINISH))

    # --- Wood -------------------------------------------------------------
    paths = limb_paths(geometry.skeleton, subdivisions=subdivisions)
    sweeps = sphere_sweeps_from_paths(paths, texture="GutenBark")
    if sweeps:
        scene.add(Union(sweeps))

    # --- Foliage ----------------------------------------------------------
    points, directions = leaf_frames(
        geometry.leaf_points,
        geometry.skeleton,
        size=geometry.leaf_radius,
        cling=cling,
        seed=seed_from_key(slug + ":leaves"),
    )
    if len(points):
        # LEAF_ASPECT is a per-axis ratio; the prototype is a unit sphere, so
        # the instance scale is the leaf radius times that ratio.
        leaf_scale = tuple(float(geometry.leaf_radius) * a for a in LEAF_ASPECT)
        tint = np.asarray(geometry.leaf_tint, dtype=int)
        for index, texture in enumerate(leaf_textures):
            mask = tint == index
            if not mask.any():
                continue
            instances = instances_from_frames(
                LEAF_PROTOTYPE,
                points[mask],
                directions[mask],
                texture=texture,
            )
            # Instance is frozen, and instances_from_frames has no scale
            # parameter — the prototype is a unit sphere, so the scale is
            # applied here.  POV-Ray transforms in written order, so the
            # prototype is scaled, then rotated into its frame, then moved.
            scene.add(Union([replace(i, scale=leaf_scale) for i in instances]))

    # --- Spores -----------------------------------------------------------
    for kind, (spore_points, spore_radius) in geometry.spores.items():
        spore_texture = Texture(color=KIND_COLOR[kind], opacity=SPORE_OPACITY, finish=SPORE_FINISH)
        scene.add(Union(spheres_from_points(spore_points, spore_radius, spore_texture)))

    if ground_size > 0:
        half = ground_size / 2.0
        scene.add(
            Box(
                corner1=(-half, -half, -0.25),
                corner2=(half, half, -0.2),
                texture=Texture(color=GROUND_COLOR, finish=BARK_FINISH),
            )
        )

    if lights:
        # Bounds come from the wood and spores: instanced leaves are not
        # measurable without resolving the prototype, so the canopy does not
        # widen the rig.  The wood reaches the crown anyway, which is what
        # matters for placing lights.
        bounds = scene.bounds()
        if bounds is None:
            scene.add_light(LightSource(position=(0.0, -50.0, 50.0)))
        else:
            for light in tree_lights(*bounds):
                scene.add_light(light)

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
    ground_size: float = 0.0,
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
    :param ground_size: Ground slab edge length; ``0`` omits it.
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
    report(f"Writing {geometry.skeleton.n_nodes:,} skeleton nodes as sphere sweeps...")
    scene = tree_pov_scene(
        geometry,
        subdivisions=subdivisions,
        slug=slug,
        ground_size=ground_size,
    )
    report(f"Composed {len(scene):,} POV-Ray objects.")
    return scene, geometry


def tree_pov_camera(
    scene: PovScene,
    *,
    fov: float = 14.0,
    zoom: float = 1.0,
) -> PovCamera:
    """
    Frame a tree scene the way ``gutenkg quilt`` frames the PyVista one.

    Level view along ``-y``, up is ``+z``, and the focal plane sits at the
    centre of the scene's own bounds so the crown straddles the display surface
    rather than sitting entirely behind it.  Everything is in right-handed
    coordinates; ``povgen`` negates ``z`` on emission, camera included.

    The distance is chosen to fit the scene's bounding sphere in *fov*, which
    is the analytic equivalent of ``plotter.reset_camera()``.

    :param scene: A composed scene; its :meth:`~quiltwright.povgen.PovScene.bounds`
        supply the framing.  Instanced leaves do not contribute to those bounds
        — they cannot be measured without resolving the prototype — so the
        wood and spores are what frame the shot.
    :param fov: Vertical field of view in degrees.
    :param zoom: Dolly factor applied after framing; ``>1`` fills more of the
        tile, which is what drives perceived depth on a light-field panel.
    :return: The camera to hand to
        :func:`~quiltwright.povray.render_pov_quilt`.
    :raises ValueError: If the scene has nothing measurable to frame.
    """
    bounds = scene.bounds()
    if bounds is None:
        raise ValueError("scene has no measurable geometry to frame")
    lo, hi = bounds
    centre = (lo + hi) / 2.0
    radius = float(np.linalg.norm(hi - lo)) / 2.0
    distance = radius / max(np.tan(np.radians(fov / 2.0)), 1e-6) / max(zoom, 1e-6)
    return PovCamera(
        location=(float(centre[0]), float(centre[1] - distance), float(centre[2])),
        look_at=(float(centre[0]), float(centre[1]), float(centre[2])),
        sky=(0.0, 0.0, 1.0),
        fov=fov,
    )


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
