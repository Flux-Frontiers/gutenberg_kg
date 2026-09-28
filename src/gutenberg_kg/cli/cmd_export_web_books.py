# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""export-web-books subcommand -- write each book's text for the web forest's reader."""

from __future__ import annotations

from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import CORPUS_ROOT
from gutenberg_kg.export_web_books import DEFAULT_OUT, DEFAULT_PACKS, collect_books, write_books


@cli.command("export-web-books")
@click.option(
    "--corpus",
    type=click.Path(path_type=Path),
    default=CORPUS_ROOT,
    show_default=True,
    help="Corpus root; books and slugs follow export-web-catalog.",
)
@click.option(
    "--packs",
    type=click.Path(path_type=Path),
    default=DEFAULT_PACKS,
    show_default=True,
    help="Directory of the packs `gutenkg export-swift` writes.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=DEFAULT_OUT,
    show_default=True,
    help="Output directory: the forest's public/books in a knowledge_press checkout "
    "(set KNOWLEDGE_PRESS_DIR to move the default).",
)
def export_web_books(corpus: Path, packs: Path, out: Path) -> None:
    """Write every book's chapters as <slug>.json, so the forest can read books without a worker.

    Chapters are rebuilt from the packs the way the worker's get_chapter
    rebuilds them. Run `gutenkg export-swift` first.
    \f

    :param corpus: Corpus root.
    :param packs: Pack directory.
    :param out: Output directory.
    """
    if not corpus.is_dir():
        raise click.ClickException(f"no corpus at {corpus} -- ingest books first")
    for name in ("core.pack", "gutenberg.pack", "diaries.pack"):
        if not (packs / name).is_file():
            raise click.ClickException(f"no {name} in {packs} -- run `gutenkg export-swift` first")

    books, missing = collect_books(corpus, packs)
    if not books:
        raise click.ClickException("no book text found in the packs")
    total = write_books(books, out)
    chapters = sum(len(b.chapters) for b in books)
    click.echo(f"wrote {len(books)} books, {chapters:,} chapters, {total / 1e6:.1f} MB to {out}")
    for key in missing:
        click.echo(f"  no text in the packs: {key}", err=True)
