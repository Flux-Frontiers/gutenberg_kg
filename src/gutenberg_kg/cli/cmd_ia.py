"""Internet Archive subcommands — fetch books from archive.org."""

import click

from gutenberg_kg import ia
from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_IA_GENRES


@cli.group("ia")
def ia_group():
    """Download books from the Internet Archive (archive.org)."""
    pass


@ia_group.command("search")
@click.argument("query")
@click.option("--max-results", default=25, show_default=True, help="Maximum results to display.")
def ia_search(query, max_results):
    """Search the Internet Archive catalog.

    :param query: Keyword query sent to the IA full-text search API.
    :param max_results: Maximum number of results to display.
    """
    try:
        results = ia.search_ia(query, max_results=max_results)
    except Exception as exc:
        click.echo(f"Search failed: {exc}", err=True)
        raise SystemExit(1)
    ia.format_search_results(results)


@ia_group.command("download")
@click.argument("identifier")
@click.option(
    "--genre",
    type=click.Choice(ALL_IA_GENRES),
    required=True,
    help="Genre subdirectory to place the book in.",
)
@click.option("--title", default=None, help="Override the book title.")
@click.option("--force", is_flag=True, default=False, help="Re-download even if already present.")
@click.option("--dry-run", is_flag=True, default=False, help="Print actions without downloading.")
def ia_download(identifier, genre, title, force, dry_run):
    """Download a single item by its Internet Archive identifier.

    :param identifier: IA item identifier (e.g. ``audelselectriciansguide01ande``).
    :param genre: Genre subdirectory under corpus/.
    :param title: Optional title override.
    :param force: Re-download even if already present.
    :param dry_run: Print what would be done without actually doing it.
    """
    result = ia.download_book(identifier, title=title, genre=genre, force=force, dry_run=dry_run)
    if result is None:
        raise SystemExit(1)


@ia_group.command("catalog")
@click.argument("catalog_file", type=click.Path(exists=True))
@click.option(
    "--genre",
    type=click.Choice(ALL_IA_GENRES),
    default=None,
    help="Override genre for every entry in the catalog.",
)
@click.option("--force", is_flag=True, default=False, help="Re-download even if already present.")
@click.option("--dry-run", is_flag=True, default=False, help="Print actions without downloading.")
def ia_catalog(catalog_file, genre, force, dry_run):
    """Download multiple items from a catalog file.

    :param catalog_file: Path to a catalog file (one ``<identifier> [genre]`` per line).
    :param genre: Override genre for all entries.
    :param force: Re-download even if already present.
    :param dry_run: Print what would be done without actually doing it.
    """
    rc = ia.run_catalog(catalog_file, genre=genre, force=force, dry_run=dry_run)
    if rc != 0:
        raise SystemExit(rc)


@ia_group.command("survey")
@click.option(
    "--genre",
    type=click.Choice(ALL_IA_GENRES),
    default=None,
    help="Limit survey to one genre.",
)
def ia_survey(genre):
    """Scan the repo and show download/ingest status for IA-sourced genres.

    :param genre: Optional genre filter.
    """
    ia.run_survey(genre)
