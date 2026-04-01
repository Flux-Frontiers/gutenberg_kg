"""Rebuild subcommands — reconstruct LanceDB vector indices from graph.sqlite."""
import subprocess

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES, REPO_ROOT


@cli.command("rebuild-lancedb")
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    multiple=True,
    help="Genre to rebuild (repeatable; default: all).",
)
def rebuild_lancedb(genre):
    """Rebuild LanceDB vector indices from graph.sqlite after cloning.

    LanceDB files are not committed to git. Run this once after cloning to
    reconstruct vector indices from the committed graph.sqlite databases.

    :param genre: Tuple of genres to rebuild (empty = all genres).
    """
    genres = list(genre) if genre else ALL_GENRES

    click.echo("=== Gutenberg KG — LanceDB rebuild ===")
    click.echo(f"Genres: {' '.join(genres)}")
    click.echo("")

    total = 0
    failed = 0

    for g in genres:
        genre_dir = REPO_ROOT / g
        if not genre_dir.is_dir():
            click.echo(f"[!] {g}: directory not found — skipping")
            continue

        click.echo(f"--- {g} ---")

        book_dirs = sorted(
            p for p in genre_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )

        for book_dir in book_dirs:
            book_name = book_dir.name
            sqlite = book_dir / ".dockg" / "graph.sqlite"
            lancedb = book_dir / ".dockg" / "lancedb"

            # Skip if sqlite not yet present (book not yet ingested)
            if not sqlite.exists():
                click.echo(f"  [{book_name}] no graph.sqlite — skipping")
                continue

            # Skip if lancedb already exists
            if lancedb.is_dir():
                click.echo(f"  [{book_name}] lancedb already exists — skipping")
                continue

            click.echo(f"  [{book_name}] rebuilding...")
            result = subprocess.run(
                ["dockg", "build", "--repo", str(book_dir)],
                check=False,
                text=True,
            )
            if result.returncode == 0:
                click.echo(f"  [{book_name}] done")
                total += 1
            else:
                click.echo(f"  [{book_name}] FAILED")
                failed += 1

        click.echo("")

    click.echo(f"=== Done: {total} rebuilt, {failed} failed ===")
    if failed:
        click.echo("[!] Re-run to retry failed books.")
        raise SystemExit(failed)
