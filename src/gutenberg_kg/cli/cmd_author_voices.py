# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""author-voices subcommand -- each author's gender and accent for moot voices."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import click

from gutenberg_kg.author_voices import VOICES_PATH, author_pages, look_up, merge_voices, read_voices
from gutenberg_kg.authors import AUTHORS_DIR
from gutenberg_kg.cli.main import cli


@cli.command("author-voices")
@click.option(
    "--authors",
    "authors_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=AUTHORS_DIR,
    show_default=True,
    help="The author pages directory.",
)
@click.option(
    "--refresh",
    is_flag=True,
    help="Look up every author again; entries marked manual are still kept.",
)
@click.option("--dry-run", is_flag=True, help="Print the table instead of writing it.")
def author_voices(authors_dir: Path, refresh: bool, dry_run: bool) -> None:
    """Look up each author's gender and accent on Wikidata for moot voices.

    Writes corpus/authors/voices.json beside the author pages. Ingestion does
    not use it; `gutenkg export-web-moots` reads it. Existing entries are
    kept unless --refresh, and an entry whose source you set to "manual" is
    never overwritten, so corrections survive.
    \f

    :param authors_dir: The author pages directory.
    :param refresh: Look up existing entries again.
    :param dry_run: Print instead of writing.
    """
    pages = author_pages(authors_dir)
    if not pages:
        raise click.ClickException(f"no author pages in {authors_dir}")
    path = authors_dir / VOICES_PATH.name
    old = read_voices(path)
    todo = pages if refresh else {s: p for s, p in pages.items() if s not in old}
    voices = merge_voices(old, look_up(todo) if todo else {}, refresh)
    if dry_run:
        click.echo(json.dumps(voices, indent=1, ensure_ascii=False))
        return
    path.write_text(json.dumps(voices, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    genders = Counter(v["gender"] for v in voices.values())
    accents = Counter(v["accent"] for v in voices.values())
    click.echo(f"looked up {len(todo)} author(s); {len(voices)} in {path}")
    click.echo(f"  gender: {dict(genders)}")
    click.echo(f"  accent: {dict(accents)}")
    review = [s for s, v in voices.items() if v["source"] in ("wikidata-search", "not found")]
    for slug in review:
        click.echo(f"  review: {slug} ({voices[slug]['source']})")
