"""audelkg — root Click group."""

import click

from .cmd_download import download
from .cmd_ingest import ingest


@click.group()
def cli() -> None:
    """audelkg — download and ingest Internet Archive technical manuals."""


cli.add_command(download)
cli.add_command(ingest)
