"""re-register subcommand — fix KGKind for all built books without rebuilding DocKGs."""

import click

from gutenberg_kg import ingest as ig
from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES


@cli.command("re-register")
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    multiple=True,
    help="Genre to process (repeatable; default: all).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print actions without writing to the registry.",
)
@click.option(
    "--registry",
    default=None,
    metavar="PATH",
    help="Override the KGRAG registry path.",
)
def reregister(genre, dry_run, registry):
    """Re-register all built books with the correct KGKind without rebuilding DocKGs.

    Walks the corpus, finds books that already have a .dockg/graph.sqlite, and
    upserts each one into the KGRAG registry with kind=gutenberg.  Safe to run on
    any machine — including fresh clones where the registry is empty — as a fast
    alternative to a full gutenkg rebuild-indices.
    """
    genres = list(genre) if genre else ALL_GENRES
    if dry_run:
        click.echo("[DRY RUN — no changes will be made]\n")
    rc = ig.run_reregister(genres, registry=registry, dry_run=dry_run)
    if rc != 0:
        raise SystemExit(rc)
