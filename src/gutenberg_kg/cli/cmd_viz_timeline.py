"""CLI command: gutenkg viz-timeline — visualize corpus growth across snapshots."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import CORPUS_ROOT

_SNAPSHOTS_DEFAULT = CORPUS_ROOT / ".snapshots"
_VIZ_EXTRA = "pip install gutenberg-kg[viz]"


@cli.command("viz-timeline")
@click.option(
    "--snapshots",
    default=str(_SNAPSHOTS_DEFAULT),
    show_default=True,
    help="Path to the snapshots directory.",
)
@click.option(
    "--type",
    "chart_type",
    type=click.Choice(["2d", "3d"]),
    default="2d",
    show_default=True,
    help="Chart style: 2d (four subplots) or 3d (normalized scatter).",
)
def viz_timeline(snapshots: str, chart_type: str) -> None:
    """Visualize corpus growth across saved snapshots.

    Plots total books, authors, nodes, and edges over time using an
    interactive Plotly chart.  Run ``gutenkg snapshot save`` first to
    build the snapshot history.

    :param snapshots: Path to the directory containing ``snapshot-*.json`` files.
    :param chart_type: ``2d`` for a 2×2 subplot grid or ``3d`` for a normalized
        multi-metric 3-D scatter plot.
    """
    snapshots_dir = Path(snapshots)
    if not snapshots_dir.is_dir():
        raise click.UsageError(
            f"Snapshots directory not found: {snapshots_dir}\n"
            "Run 'gutenkg snapshot save' first to capture a snapshot."
        )

    if importlib.util.find_spec("plotly") is None:
        raise click.UsageError(
            f"plotly is not installed. Install viz dependencies with:\n  {_VIZ_EXTRA}"
        )

    from gutenberg_kg.viz_timeline import (  # pylint: disable=import-outside-toplevel
        create_3d_timeline_figure,
        create_timeline_figure,
        display_timeline_summary,
    )

    click.echo(display_timeline_summary(snapshots_dir))

    fig = (
        create_3d_timeline_figure(snapshots_dir)
        if chart_type == "3d"
        else create_timeline_figure(snapshots_dir)
    )

    try:
        fig.show()
    except (OSError, AttributeError, ImportError) as exc:
        click.echo(f"Could not display visualization: {exc}", err=True)
