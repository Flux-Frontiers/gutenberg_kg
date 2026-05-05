"""Download subcommands — fetch books from Project Gutenberg."""

import click

from gutenberg_kg import gutenberg as _dg
from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES


@cli.group("download")
def download_group():
    """Download books from Project Gutenberg."""
    pass


@download_group.command("book")
@click.argument("ebook_id", type=int)
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    default=None,
    help="Genre subdirectory to place the book in.",
)
@click.option("--title", default=None, help="Override the book title.")
@click.option("--force", is_flag=True, default=False, help="Re-download even if already present.")
@click.option("--dry-run", is_flag=True, default=False, help="Print actions without downloading.")
def download_book(ebook_id, genre, title, force, dry_run):
    """Download a single book by its Gutenberg ebook ID.

    :param ebook_id: Project Gutenberg numeric book ID.
    :param genre: Optional genre subdirectory.
    :param title: Optional title override.
    :param force: Re-download even if already present.
    :param dry_run: Print what would be done without actually doing it.
    """
    if dry_run:
        click.echo(f"[dry] Would download Gutenberg #{ebook_id}...")
    else:
        click.echo(f"Downloading Gutenberg #{ebook_id}...")
    try:
        path = _dg.download_book(ebook_id, title=title, genre=genre, force=force, dry_run=dry_run)
        if not dry_run:
            click.echo(f"\nDone. Book saved to: {path}")
    except Exception as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1)


@download_group.command("catalog")
@click.argument("catalog_file", type=click.Path(exists=True))
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    default=None,
    help="Override genre for every entry in the catalog.",
)
@click.option("--force", is_flag=True, default=False, help="Re-download even if already present.")
@click.option("--dry-run", is_flag=True, default=False, help="Print actions without downloading.")
def download_catalog(catalog_file, genre, force, dry_run):
    """Download multiple books from a catalog file.

    :param catalog_file: Path to a catalog file (one ``<ebook_id> [genre]`` per line).
    :param genre: Override genre for all entries.
    :param force: Re-download even if already present.
    :param dry_run: Print what would be done without actually doing it.
    """
    _dg.run_catalog(catalog_file, genre=genre, force=force, dry_run=dry_run)


@download_group.command("search")
@click.argument("query", default="")
@click.option("--author", default=None, help="Filter by author name.")
@click.option("--title", default=None, help="Filter by title keyword.")
@click.option("--subject", default=None, help="Filter by subject/topic.")
@click.option("--language", default=None, help="Filter by language code (e.g. en, fr).")
@click.option(
    "--max-results",
    default=25,
    show_default=True,
    help="Maximum number of results to display.",
)
def download_search(query, author, title, subject, language, max_results):
    """Search the Project Gutenberg catalog.

    :param query: General keyword query.
    :param author: Filter by author name.
    :param title: Filter by title keyword.
    :param subject: Filter by subject/topic.
    :param language: Filter by language code.
    :param max_results: Maximum results to display.
    """
    _dg.run_search(
        query=query,
        author=author,
        title=title,
        subject=subject,
        language=language,
        max_results=max_results,
    )


@download_group.command("fetch-genre")
@click.argument("genre", type=click.Choice(ALL_GENRES))
@click.option("--query", default=None, help="Additional search keywords within the genre.")
@click.option(
    "--max-results",
    default=25,
    show_default=True,
    help="Maximum books to search for.",
)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompts.")
@click.option("--force", is_flag=True, default=False, help="Re-download even if already present.")
@click.option("--dry-run", is_flag=True, default=False, help="Print actions without downloading.")
def fetch_genre(genre, query, max_results, yes, force, dry_run):
    """Search, confirm, and download an entire genre in one step.

    :param genre: Genre to fetch books for.
    :param query: Additional keyword refinement for the search.
    :param max_results: Maximum books to consider.
    :param yes: Skip interactive confirmation.
    :param force: Re-download even if already present.
    :param dry_run: Print what would be done without actually doing it.
    """
    _dg.run_fetch_genre(
        genre, query=query, max_results=max_results, yes=yes, force=force, dry_run=dry_run
    )


@download_group.command("survey")
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    default=None,
    help="Limit survey to one genre.",
)
def survey(genre):
    """Scan the repo and show download/ingest status by genre.

    :param genre: Optional genre filter.
    """
    _dg.run_survey(genre)
