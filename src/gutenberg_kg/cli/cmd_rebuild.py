"""Rebuild subcommands — reconstruct knowledge graph indices after cloning."""

import click

from gutenberg_kg import ingest as ig
from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES


@cli.command("rebuild-indices")
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    multiple=True,
    help="Genre to rebuild (repeatable; default: all).",
)
@click.option(
    "--force-build",
    is_flag=True,
    default=False,
    help="Rebuild DocKG even if .dockg already exists.",
)
def rebuild_indices(genre, force_build):
    """Rebuild knowledge graph indices after cloning.

    Graph indices are not committed to git. Run this once after cloning to
    reconstruct them from the committed Markdown source files.

    :param genre: Tuple of genres to rebuild (empty = all genres).
    :param force_build: Rebuild even if .dockg already exists.
    """
    genres = list(genre) if genre else ALL_GENRES
    opts = ig.IngestOptions(force_build=force_build)
    rc = ig.run_ingest(genres, opts)
    if rc != 0:
        raise SystemExit(rc)
