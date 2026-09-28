# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""stale subcommand -- list books whose index is older than their text."""

from __future__ import annotations

from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import CORPUS_ROOT, REPO_ROOT
from gutenberg_kg.stale import bundle_is_stale, stale_books


@cli.command("stale")
@click.option(
    "--bundle",
    default="gutenberg-all",
    show_default=True,
    help="Bundle under bundles/ to compare against the per-book indices.",
)
def stale(bundle: str) -> None:
    """List prose books whose text is newer than their index, and a stale bundle.

    After a text change (a --force re-download, `gutenkg authors --refresh`, a
    pull), the per-book index keeps the old chunks and `build-corpus --update`
    keeps the old vectors. The last line prints the `make refresh-text` command
    that carries the change to every surface. Exits 1 when anything is stale.
    \f

    :param bundle: Bundle name under ``bundles/``.
    """
    stale = stale_books(CORPUS_ROOT)
    for d, reason in stale:
        click.echo(f"book    {d.relative_to(CORPUS_ROOT)}  ({reason})")

    bundle_dir = REPO_ROOT / "bundles" / bundle
    bundle_stale = bundle_is_stale(CORPUS_ROOT, bundle_dir)
    if bundle_stale:
        click.echo(f"bundle  {Path('bundles') / bundle}  (older than a per-book index)")

    if not stale and not bundle_stale:
        click.echo("Nothing stale.")
        return

    genres = sorted({d.parent.name for d, _ in stale})
    if genres:
        click.echo(f'\nRefresh with: make refresh-text GENRE="{" ".join(genres)}"')
    else:
        click.echo(
            "\nPer-book indices are current; rebuild the bundle and everything "
            'after it with: make refresh-text GENRE=""'
        )
    raise SystemExit(1)
