"""Ingest subcommands — build DocKG indices and register with KGRAG."""

import click

from gutenberg_kg import ingest as ig
from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES


@cli.command("ingest")
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    multiple=True,
    help="Genre to process (repeatable; default: all).",
)
@click.option(
    "--force-build",
    is_flag=True,
    default=False,
    help="Rebuild DocKG even if .dockg already exists.",
)
@click.option(
    "--force-register",
    is_flag=True,
    default=False,
    help="Re-register even if KG name already in registry.",
)
@click.option(
    "--push",
    is_flag=True,
    default=False,
    help="git add + commit + push after each genre completes.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print actions without executing anything.",
)
@click.option(
    "--registry",
    default=None,
    metavar="PATH",
    help="Override the KGRAG registry path.",
)
def ingest(genre, force_build, force_register, push, dry_run, registry):
    """Build DocKG indices, register with KGRAG, and optionally push to git.

    :param genre: Tuple of genres to process (empty = all genres).
    :param force_build: Rebuild even if .dockg already exists.
    :param force_register: Re-register even if already in the registry.
    :param push: Push to git after each genre completes.
    :param dry_run: Print what would be done without executing.
    :param registry: Override the KGRAG registry path.
    """
    genres = list(genre) if genre else ALL_GENRES
    opts = ig.IngestOptions(
        force_build=force_build,
        force_register=force_register,
        dry_run=dry_run,
        push=push,
    )
    if opts.dry_run:
        click.echo("[DRY RUN — no changes will be made]\n")
    rc = ig.run_ingest(genres, opts, registry)
    if rc != 0:
        raise SystemExit(rc)


@cli.command("list-genres")
def list_genres():
    """Print all known Gutenberg genres."""
    click.echo("Known genres:")
    for g in ALL_GENRES:
        click.echo(f"  {g}")
