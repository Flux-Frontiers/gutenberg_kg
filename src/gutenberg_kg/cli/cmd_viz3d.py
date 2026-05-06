"""CLI command: gutenkg viz3d — launch the 3-D knowledge tree forest visualiser."""

import click

from gutenberg_kg.cli.main import cli


@cli.command("viz3d")
@click.option(
    "--corpus",
    "corpus_root",
    default="corpus",
    show_default=True,
    help="Path to the corpus root directory.",
)
@click.option(
    "--width",
    default=1500,
    show_default=True,
    help="Initial window width in pixels.",
)
@click.option(
    "--height",
    default=950,
    show_default=True,
    help="Initial window height in pixels.",
)
def cmd_viz3d(corpus_root: str, width: int, height: int) -> None:
    """Launch the 3-D Knowledge Tree Forest visualiser.

    Each ingested book is rendered as a tree — trunk (document), branches
    (sections/chapters), leaves (text chunks) — with books grouped by genre
    into groves.  Navigate the forest with the mouse; right-click any node
    to read its text.

    Only books that have been ingested (have a .dockg/graph.sqlite) are shown.
    Run  gutenkg ingest  first to build book knowledge graphs.
    """
    try:
        from gutenberg_kg.viz3d import launch
    except ImportError as exc:
        raise click.ClickException(
            f"viz3d requires pyvista, pyvistaqt, PyQt5, param, and pycode_kg.\n"
            f"Install with:  pip install gutenberg-kg[viz3d]\n"
            f"Details: {exc}"
        ) from exc

    launch(corpus_root=corpus_root, width=width, height=height)
