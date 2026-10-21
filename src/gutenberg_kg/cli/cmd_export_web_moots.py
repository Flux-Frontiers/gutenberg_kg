# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""export-web-moots subcommand -- write moot packs for the web forest."""

from __future__ import annotations

from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.export_web_moots import DEFAULT_OUT, MootPackError, write_moots


@cli.command("export-web-moots")
@click.argument(
    "transcripts",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUT,
    show_default=True,
    help="Output directory: the forest's public/moots in a knowledge_press checkout "
    "(set KNOWLEDGE_PRESS_DIR to move the default).",
)
def export_web_moots(transcripts: tuple[Path, ...], out: Path) -> None:
    """Write each `converse --out` transcript as a moot pack the forest can play.

    Each pack is written as <id>.json, the id a slug of both book names and
    the topic, and index.json is updated; a pack with an id already in the
    index replaces it.
    \f

    :param transcripts: Transcript files from `gutenkg converse --out`.
    :param out: Output directory.
    """
    try:
        ids = write_moots(list(transcripts), out)
    except MootPackError as exc:
        raise click.ClickException(str(exc)) from exc
    for moot in ids:
        click.echo(f"  {moot}")
    click.echo(f"wrote {len(ids)} moot pack(s) to {out}")
