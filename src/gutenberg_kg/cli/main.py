"""Root Click group for the GutenbergKG CLI."""

import importlib.metadata

import click


@click.group()
@click.version_option(version=importlib.metadata.version("gutenberg-kg"))
def cli():
    """gutenkg — The Knowledge Press. Download, ingest, and query digitized text corpora."""
    pass


# Import subcommands to register them
from gutenberg_kg.cli import (  # noqa: E402, F401
    cmd_authors,
    cmd_download,
    cmd_genres,
    cmd_ia,
    cmd_ingest,
    cmd_rebuild,
    cmd_reregister,
    cmd_snapshot,
    cmd_status,
    cmd_viz3d,
    cmd_viz_timeline,
)
