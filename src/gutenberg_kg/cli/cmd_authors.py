"""Authors subcommand — rebuild the per-author provenance index."""

import click

from gutenberg_kg import authors
from gutenberg_kg.cli.main import cli


@cli.command("authors")
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Re-fetch the Gutenberg RDF for every book and rewrite the Author "
    "section of its reference.md (all creators, first creator's Born/Died/"
    "Wikipedia) before rebuilding the index.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print actions without writing any files.",
)
def authors_cmd(refresh: bool, dry_run: bool) -> None:
    """Build corpus/authors/ from every reference.md in the corpus.

    Scans corpus/<genre>/<book>/reference.md for all books and writes one
    page per author, listing a co-written book under each of its authors,
    plus a master alphabetical index. Use --refresh to first rewrite every
    reference.md Author section from the Gutenberg RDF catalog, which is how
    a corpus picks up fixes to author parsing.
    \f

    :param refresh: Rewrite every Author section from a fresh RDF fetch.
    :param dry_run: Print actions without writing any files.
    """
    raise SystemExit(authors.build(refresh=refresh, dry_run=dry_run))
