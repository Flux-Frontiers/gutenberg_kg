"""audelkg download commands — thin Click wrappers around scripts/download_ia.py."""

import sys
from pathlib import Path

import click

# Resolve the scripts directory so we can import without installing
_SCRIPTS = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from download_ia import (  # noqa: E402
    ALL_GENRES,
    cmd_catalog,
    cmd_download,
    cmd_search,
    cmd_survey,
)


@click.group("download")
def download() -> None:
    """Download books from Internet Archive as structured Markdown."""


@download.command("search")
@click.argument("query", nargs=-1, required=True)
@click.option("-n", default=25, show_default=True, help="Max results")
def search_cmd(query: tuple[str, ...], n: int) -> None:
    """Search Internet Archive for texts."""
    import argparse

    args = argparse.Namespace(query=list(query), n=n)
    sys.exit(cmd_search(args))


@download.command("book")
@click.argument("identifier")
@click.option("--title", default=None, help="Override book title")
@click.option("--genre", type=click.Choice(ALL_GENRES), default=None)
@click.option("--force", is_flag=True, help="Re-download if already exists")
@click.option("--dry-run", is_flag=True)
def book_cmd(
    identifier: str, title: str | None, genre: str | None, force: bool, dry_run: bool
) -> None:
    """Download a single Internet Archive item by identifier."""
    import argparse

    args = argparse.Namespace(
        identifier=identifier,
        title=title,
        genre=genre,
        force=force,
        dry_run=dry_run,
    )
    sys.exit(cmd_download(args))


@download.command("catalog")
@click.argument("catalog_file", type=click.Path(exists=True))
@click.option("--genre", type=click.Choice(ALL_GENRES), default=None)
@click.option("--force", is_flag=True)
@click.option("--dry-run", is_flag=True)
def catalog_cmd(catalog_file: str, genre: str | None, force: bool, dry_run: bool) -> None:
    """Download all items from a tab-separated catalog file."""
    import argparse

    args = argparse.Namespace(catalog=catalog_file, genre=genre, force=force, dry_run=dry_run)
    sys.exit(cmd_catalog(args))


@download.command("survey")
@click.option("--genre", type=click.Choice(ALL_GENRES), default=None)
def survey_cmd(genre: str | None) -> None:
    """Show download/ingest status for the corpus."""
    import argparse

    args = argparse.Namespace(genre=genre)
    sys.exit(cmd_survey(args))
