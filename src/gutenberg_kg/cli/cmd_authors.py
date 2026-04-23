"""Authors subcommand — rebuild the per-author provenance index."""
import click

from gutenberg_kg import authors
from gutenberg_kg.cli.main import cli


@cli.command("authors")
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Re-fetch Gutenberg RDF for books missing Born/Died and patch "
         "their reference.md files in place before rebuilding the index.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print actions without writing any files.",
)
def authors_cmd(refresh: bool, dry_run: bool) -> None:
    """Build corpus/authors/ from every reference.md in the corpus.

    Scans corpus/<genre>/<book>/reference.md for all books, groups by
    author, and writes one page per author plus a master alphabetical
    index. Use --refresh to also backfill Born/Died/Wikipedia for any
    reference.md that predates the RDF fetch.

    :param refresh: Re-fetch RDF for books missing provenance.
    :param dry_run: Print actions without writing any files.
    """
    raise SystemExit(authors.build(refresh=refresh, dry_run=dry_run))
