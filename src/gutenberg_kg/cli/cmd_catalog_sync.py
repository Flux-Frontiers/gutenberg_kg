"""catalog-sync subcommand — record downloaded books in their genre catalogs."""

import click

from gutenberg_kg import gutenberg as dg
from gutenberg_kg import ia
from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES


@cli.command("catalog-sync")
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
    help="Print actions without writing to any catalog.",
)
def catalog_sync(genre, dry_run):
    """Record every downloaded book in its genre catalog.

    Repairs catalog drift left by downloads that predate catalog write-back:
    `download book`, `download fetch-genre` and `ia download` wrote the corpus
    but never the catalog, so those books are absent from the manifest that
    `download catalog` replays -- a fresh clone rebuilds a strict subset.

    Nothing is downloaded.  Each book's reference.md already carries its
    Gutenberg ID, so the catalog is reconstructed by reading the corpus.  This
    is the catalog counterpart to `gutenkg re-register`, which rebuilds registry
    entries from built indices the same way.

    Idempotent: books already catalogued are left alone, so it is safe to re-run
    and safe to run on a fresh clone.  Gutenberg genres are keyed on the
    Gutenberg ID, IA genres on the Internet Archive identifier; both live in
    each book's reference.md.  Run `gutenkg audit` afterwards to confirm the
    warnings clear.
    """
    genres = list(genre) if genre else ALL_GENRES
    if dry_run:
        click.echo("[DRY RUN — no changes will be made]\n")

    added = dg.run_catalog_sync(genres, dry_run=dry_run)
    added += ia.run_catalog_sync(genres, dry_run=dry_run)

    if not added:
        click.echo("Every downloaded book is already catalogued — nothing to do.")
    elif dry_run:
        click.echo(f"\n[dry] {added} catalog entr{'y' if added == 1 else 'ies'} would be added.")
    else:
        click.echo(f"\nDone. {added} catalog entr{'y' if added == 1 else 'ies'} added.")
