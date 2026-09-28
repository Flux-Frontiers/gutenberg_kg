# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""export-web-catalog subcommand -- write the web forest's book catalog."""

from __future__ import annotations

from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import CORPUS_ROOT
from gutenberg_kg.export_web import DEFAULT_OUT, scan_corpus, write_catalog


@cli.command("export-web-catalog")
@click.option(
    "--corpus",
    type=click.Path(path_type=Path),
    default=CORPUS_ROOT,
    show_default=True,
    help="Corpus root to scan.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUT,
    show_default=True,
    help="Output directory: the forest's src/game in a knowledge_press checkout "
    "(set KNOWLEDGE_PRESS_DIR to move the default).",
)
@click.option("--dry-run", is_flag=True, help="Report the counts without writing.")
def export_web_catalog(corpus: Path, out: Path, dry_run: bool) -> None:
    """Write the Knowledge Press Forest's book catalog from the per-book graphs.

    Counts each book's chunk nodes the way ForestLayout sizes a tree, takes
    title and author from reference.md, and writes catalog.ts plus its
    catalogPart*.ts files. It does not re-chunk; run `gutenkg ingest` first.
    \f

    :param corpus: Corpus root.
    :param out: Output directory.
    :param dry_run: Report without writing.
    """
    if not corpus.is_dir():
        raise click.ClickException(f"no corpus at {corpus} -- ingest books first")

    books = scan_corpus(corpus)
    if not books:
        raise click.ClickException("no books with graph.sqlite found")

    click.echo(f"{len(books)} books  ·  {sum(b.chunks for b in books):,} chunks")
    hamlet = next((b for b in books if b.slug == "hamlet"), None)
    if hamlet:
        click.echo(f"hamlet: {hamlet.chunks} chunks")
    by_genre: dict[str, int] = {}
    for b in books:
        by_genre[b.genre] = by_genre.get(b.genre, 0) + 1
    for g, n in sorted(by_genre.items()):
        click.echo(f"  {n:3d}  {g}")

    if dry_run:
        return

    n_parts = write_catalog(books, out)
    click.echo(f"wrote {out / 'catalog.ts'} and {n_parts} part(s)")
