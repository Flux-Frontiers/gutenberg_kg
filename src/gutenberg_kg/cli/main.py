"""Root Click group for the GutenbergKG CLI."""
import importlib.metadata

import click


@click.group()
@click.version_option(version=importlib.metadata.version("gutenberg-kg"))
def cli():
    """gutenkg — download, ingest, and query Project Gutenberg knowledge graphs."""
    pass


# Import subcommands to register them
from gutenberg_kg.cli import cmd_download, cmd_ingest, cmd_rebuild  # noqa: E402, F401
