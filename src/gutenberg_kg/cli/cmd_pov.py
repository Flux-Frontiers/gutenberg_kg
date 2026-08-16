"""CLI command: gutenkg pov — write a book's tree as a POV-Ray scene."""

from __future__ import annotations

from pathlib import Path

import click

from gutenberg_kg.cli.cmd_quilt import _resolve_book
from gutenberg_kg.cli.main import cli


@cli.command("pov")
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
    "--out",
    "out_dir",
    default="renders/pov",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Output directory for the .pov scene (and the quilt, with --render).",
)
@click.option(
    "--season",
    type=click.Choice(["spring", "summer", "autumn", "winter"]),
    default="summer",
    show_default=True,
    help="Foliage palette. Winter drops most leaves, baring the wood.",
)
@click.option("--entities", is_flag=True, help="Include the gold entity spores.")
@click.option("--topics", is_flag=True, help="Include the blue topic pollen cloud.")
@click.option(
    "--leaf-size",
    default=None,
    type=float,
    help="Leaf radius before density scaling (default 0.32).",
)
@click.option(
    "--subdivisions",
    default=4,
    show_default=True,
    help="Spline samples per skeleton segment. The one dial trading file size for limb smoothness.",
)
@click.option(
    "--render",
    is_flag=True,
    help="Ray-trace the scene into a Looking Glass quilt. Needs a povray binary on PATH.",
)
@click.option(
    "--spec",
    "spec_name",
    default="16-landscape",
    show_default=True,
    help="Quilt preset for --render.",
)
@click.option(
    "--fov",
    default=14.0,
    show_default=True,
    help="Per-view vertical field of view in degrees.",
)
@click.option(
    "--zoom",
    default=1.0,
    show_default=True,
    help="Camera dolly after framing. >1 fills more of the tile, which is what drives depth.",
)
@click.option(
    "--jobs", default=1, show_default=True, help="Parallel POV-Ray processes for --render."
)
def cmd_pov(
    corpus_root: str,
    book: str,
    genre: str | None,
    out_dir: Path,
    season: str,
    entities: bool,
    topics: bool,
    leaf_size: float | None,
    subdivisions: int,
    render: bool,
    spec_name: str,
    fov: float,
    zoom: float,
    jobs: int,
) -> None:
    """Write one book's knowledge tree as an analytic POV-Ray scene.

    The same tree ``gutenkg quilt`` rasterises, described as primitives instead
    of triangles: a limb is a ``sphere_sweep``, a leaf is one instance of a
    single declared ellipsoid.  The file is one to two orders of magnitude
    smaller than the equivalent mesh dump and its silhouettes stay exact at any
    zoom, which is the reason to leave VTK in the first place.

    Writing a scene needs neither PyVista nor a GL context — only ``--render``
    needs a ``povray`` binary.

    \b
      gutenkg pov --book Hamlet
      gutenkg pov --book Hamlet --season autumn --entities
      gutenkg pov --book Hamlet --render --spec portrait
    """
    from gutenberg_kg.bookgraph import load_book_graph, load_entry_times, scan_corpus
    from gutenberg_kg.povscene import build_tree_pov_scene, tree_pov_camera
    from gutenberg_kg.treegeom import SceneFilters

    root = Path(corpus_root)
    if not root.exists():
        raise click.ClickException(f"Corpus not found: {root}")
    catalogue = scan_corpus(root)
    if not catalogue:
        raise click.ClickException(f"No ingested books under {root}. Run  gutenkg ingest  first.")

    meta = _resolve_book(catalogue, book, genre)
    click.echo(f"Book:  {meta.genre}/{meta.title}  ({meta.kg_dir.name if meta.kg_dir else '?'})")

    nodes, edges = load_book_graph(meta)
    scene, geometry = build_tree_pov_scene(
        nodes,
        edges,
        slug=meta.slug,
        genre=meta.genre,
        entry_times=load_entry_times(meta),
        filters=SceneFilters(show_entities=entities, show_topics=topics),
        season=season,
        subdivisions=subdivisions,
        progress=lambda m: click.echo(f"  {m}"),
        **({"leaf_size": leaf_size} if leaf_size is not None else {}),
    )
    click.echo(f"Scene: {geometry.title}")

    suffix = "" if season == "summer" else f"_{season}"
    stem = out_dir / f"{meta.slug}{suffix}"
    pov_path = scene.write(stem.with_suffix(".pov"))
    click.echo(f"Wrote {pov_path} ({pov_path.stat().st_size / 1024:.0f} KB)")

    if not render:
        return

    try:
        from quiltwright import QUILT_PRESETS, save_quilt
        from quiltwright.povray import render_pov_quilt
    except ImportError as exc:  # pragma: no cover - quiltwright is a hard dep of this path
        raise click.ClickException(f"--render requires quiltwright: {exc}") from exc

    if spec_name not in QUILT_PRESETS:
        raise click.ClickException(
            f"Unknown quilt preset {spec_name!r}. Choose from: {', '.join(QUILT_PRESETS)}"
        )
    spec = QUILT_PRESETS[spec_name]
    camera = tree_pov_camera(scene, fov=fov, zoom=zoom)
    click.echo(
        f"Ray-tracing {spec.n_views} views at {spec.tile_width}x{spec.tile_height} "
        f"(focal distance {camera.focal_distance:.1f})..."
    )
    try:
        quilt = render_pov_quilt(pov_path, spec, camera, jobs=jobs)
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"No povray binary found. Install POV-Ray, or drop --render to keep the scene only.\n"
            f"Details: {exc}"
        ) from exc
    click.echo(f"Wrote {save_quilt(quilt, stem, spec)}")
