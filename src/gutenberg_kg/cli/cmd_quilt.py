"""CLI command: gutenkg quilt — render a book's tree as a light-field quilt."""

from __future__ import annotations

import math
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli


def _resolve_book(catalogue: dict, book: str, genre: str | None):
    """Find the one book whose title matches *book* (case-insensitive substring).

    :param catalogue: ``{genre: [BookMeta]}`` from ``scan_corpus``.
    :param book: Title or fragment of one.
    :param genre: Restrict the search to this genre.
    :return: The matching ``BookMeta``.
    :raises click.ClickException: On no match or an ambiguous one.
    """
    needle = book.lower()
    hits = [
        meta
        for g, metas in catalogue.items()
        if genre is None or g == genre
        for meta in metas
        if needle in meta.title.lower()
    ]
    if not hits:
        scope = f" in genre {genre!r}" if genre else ""
        raise click.ClickException(f"No ingested book matching {book!r}{scope}.")
    exact = [m for m in hits if m.title.lower() == needle]
    if len(hits) > 1 and not exact:
        listing = "\n  ".join(f"{m.genre}/{m.title}" for m in hits[:12])
        raise click.ClickException(f"{book!r} matches {len(hits)} books:\n  {listing}")
    return exact[0] if exact else hits[0]


def _depth_report(plotter, spec) -> str:
    """Disparity report for the framed subject, printed before every render.

    Projects the scene's bounding box onto the view axis to get the near and
    far depths, then hands them to quiltwright's budget formatter.  Numbers
    above roughly 5 px read soft; past ~8 px expect visible ghosting.

    :param plotter: The framed plotter.
    :param spec: Quilt specification.
    :return: Multi-line report.
    """
    import numpy as np
    from quiltwright.povray import PovCamera, format_depth_budget

    camera = plotter.camera
    pos = np.asarray(camera.position, dtype=float)
    focal = np.asarray(camera.focal_point, dtype=float)
    forward = focal - pos
    distance = float(np.linalg.norm(forward))
    forward = forward / max(distance, 1e-9)

    xmin, xmax, ymin, ymax, zmin, zmax = plotter.bounds
    corners = np.array(
        [[x, y, z] for x in (xmin, xmax) for y in (ymin, ymax) for z in (zmin, zmax)],
        dtype=float,
    )
    along = (corners - pos) @ forward

    pov_cam = PovCamera(
        location=tuple(pos), look_at=tuple(focal), sky=(0.0, 0.0, 1.0), fov=camera.view_angle
    )
    return format_depth_budget(
        spec,
        pov_cam,
        {
            "nearest foliage": float(along.min()),
            "focal plane (display surface)": distance,
            "farthest foliage": float(along.max()),
            "sky": math.inf,
        },
    )


@cli.command("quilt")
@click.option(
    "--corpus",
    "corpus_root",
    default="corpus",
    show_default=True,
    help="Path to the corpus root directory.",
)
@click.option("--book", required=True, help="Book title, or a unique fragment of one.")
@click.option("--genre", default=None, help="Restrict the book search to this genre.")
@click.option(
    "--spec",
    "spec_name",
    default="16-landscape",
    show_default=True,
    help="Looking Glass quilt preset (16-landscape, 16-portrait, portrait, go, 27-*, 32-*, 65).",
)
@click.option(
    "--out",
    "out_dir",
    default="renders/quilts",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Output directory for the quilt.",
)
@click.option(
    "--schematic",
    is_flag=True,
    help="Render the original spiral layout instead of the grown organic tree.",
)
@click.option(
    "--season",
    type=click.Choice(["spring", "summer", "autumn", "winter"]),
    default="summer",
    show_default=True,
    help="Foliage palette. Winter drops most leaves, baring the wood.",
)
@click.option("--entities", is_flag=True, help="Include the gold entity spores.")
@click.option(
    "--zoom",
    default=1.0,
    show_default=True,
    help="Camera dolly after framing. >1 fills more of the tile, which is what drives depth.",
)
@click.option(
    "--fov",
    default=14.0,
    show_default=True,
    help="Per-view vertical field of view in degrees; Looking Glass recommends ~14.",
)
@click.option(
    "--orbit",
    default=0,
    show_default=True,
    help="Render a turntable quilt VIDEO of this many frames instead of a still.",
)
@click.option("--fps", default=24, show_default=True, help="Frame rate for --orbit.")
@click.option("--cast", is_flag=True, help="Send the finished quilt to Looking Glass Bridge.")
def cmd_quilt(
    corpus_root: str,
    book: str,
    genre: str | None,
    spec_name: str,
    out_dir: Path,
    schematic: bool,
    season: str,
    entities: bool,
    zoom: float,
    fov: float,
    orbit: int,
    fps: int,
    cast: bool,
) -> None:
    """Render one book's knowledge tree as a Looking Glass quilt.

    The book is grown by space colonization so its limbs reach its own text
    chunks: the canopy's shape is the book's structure, not decoration.  The
    depth budget is printed before every render — that is where a blown
    disparity budget shows up, at no cost, rather than after the render.

    \b
      gutenkg quilt --book "Pepys"                     # 16" Gen3 Landscape
      gutenkg quilt --book Hamlet --entities --zoom 1.2
      gutenkg quilt --book Hamlet --season autumn
      gutenkg quilt --book Hamlet --spec portrait      # another device
      gutenkg quilt --book Hamlet --orbit 180 --cast
    """
    try:
        import pyvista as pv
        from quiltwright import QUILT_PRESETS, render_quilt, render_quilt_video, save_quilt
    except ImportError as exc:
        raise click.ClickException(
            f"quilt requires pyvista and quiltwright.\n"
            f"Install with:  pip install gutenberg-kg[viz3d]\n"
            f"Details: {exc}"
        ) from exc

    from gutenberg_kg.scene import (
        SceneFilters,
        build_forest_scene,
        build_tree_scene,
        load_book_graph,
        load_entry_times,
        scan_corpus,
    )

    if spec_name not in QUILT_PRESETS:
        raise click.ClickException(
            f"Unknown quilt preset {spec_name!r}. Choose from: {', '.join(QUILT_PRESETS)}"
        )
    spec = QUILT_PRESETS[spec_name]

    root = Path(corpus_root)
    if not root.exists():
        raise click.ClickException(f"Corpus not found: {root}")
    catalogue = scan_corpus(root)
    if not catalogue:
        raise click.ClickException(f"No ingested books under {root}. Run  gutenkg ingest  first.")

    meta = _resolve_book(catalogue, book, genre)
    click.echo(f"Book:  {meta.genre}/{meta.title}  ({meta.kg_dir.name if meta.kg_dir else '?'})")

    nodes, edges = load_book_graph(meta)
    entry_times = load_entry_times(meta)
    filters = SceneFilters(show_entities=entities)

    plotter = pv.Plotter(off_screen=True)
    if schematic:
        info = build_forest_scene(
            nodes,
            edges,
            plotter,
            book_genre_map={meta.slug: meta.genre},
            entry_times=entry_times,
            filters=filters,
            ground_size=0.0,
            frame_camera=False,
            progress=lambda m: click.echo(f"  {m}"),
        )
    else:
        info = build_tree_scene(
            nodes,
            edges,
            plotter,
            slug=meta.slug,
            genre=meta.genre,
            entry_times=entry_times,
            filters=filters,
            season=season,
            progress=lambda m: click.echo(f"  {m}"),
        )
    click.echo(f"Scene: {info.title}")

    # Frame the subject: level view, up = +Z, focal plane at mid-canopy so
    # the crown straddles the display surface rather than sitting behind it.
    xmin, xmax, ymin, ymax, zmin, zmax = plotter.bounds
    centre = ((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2)
    plotter.camera.up = (0.0, 0.0, 1.0)
    plotter.camera.focal_point = centre
    plotter.camera.position = (centre[0], ymin - (zmax - zmin) * 1.5, centre[2])
    plotter.reset_camera()  # ty: ignore[missing-argument]

    click.echo(_depth_report(plotter, spec))

    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_schematic" if schematic else ("" if season == "summer" else f"_{season}")
    stem = out_dir / f"{meta.slug}{suffix}"

    if orbit:
        click.echo(f"Rendering {orbit} frames x {spec.n_views} views...")
        path = render_quilt_video(plotter, spec, stem, n_frames=orbit, fps=fps, fov=fov, zoom=zoom)
    else:
        click.echo(f"Rendering {spec.n_views} views at {spec.tile_width}x{spec.tile_height}...")
        path = save_quilt(render_quilt(plotter, spec, fov=fov, zoom=zoom), stem, spec)
    plotter.close()
    click.echo(f"Wrote {path}")

    if cast:
        from quiltwright import cast_quilt

        try:
            cast_quilt(path.resolve(), spec)
            click.echo("Cast to Looking Glass Bridge.")
        except Exception as exc:  # noqa: BLE001 — Bridge absence must not fail the render
            click.echo(f"Cast failed (is Looking Glass Bridge running?): {exc}", err=True)
