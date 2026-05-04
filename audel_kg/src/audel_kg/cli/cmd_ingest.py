"""audelkg ingest command — thin Click wrapper around scripts/ingest.py."""

import sys
from pathlib import Path

import click

_SCRIPTS = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from ingest import ALL_GENRES  # noqa: E402


@click.command("ingest")
@click.option(
    "--genre",
    "genres",
    multiple=True,
    type=click.Choice(ALL_GENRES),
    help="Genre(s) to process (default: all)",
)
@click.option("--force-build", is_flag=True, help="Rebuild even if .dockg exists")
@click.option("--force-register", is_flag=True, help="Re-register even if already registered")
@click.option("--push", is_flag=True, help="git commit + push after each genre")
@click.option("--dry-run", is_flag=True, help="Print actions without executing")
@click.option("--registry", default=None, metavar="PATH", help="Override registry path")
@click.option("--list-genres", is_flag=True, help="Print all genres and exit")
def ingest(
    genres: tuple[str, ...],
    force_build: bool,
    force_register: bool,
    push: bool,
    dry_run: bool,
    registry: str | None,
    list_genres: bool,
) -> None:
    """Build DocKGs, register, and add to KGRAG corpora."""
    # Reconstruct sys.argv so ingest.py's argparse is happy
    argv = ["ingest"]
    if list_genres:
        argv.append("--list-genres")
    for g in genres:
        argv += ["--genre", g]
    if force_build:
        argv.append("--force-build")
    if force_register:
        argv.append("--force-register")
    if push:
        argv.append("--push")
    if dry_run:
        argv.append("--dry-run")
    if registry:
        argv += ["--registry", registry]

    old_argv = sys.argv
    sys.argv = argv
    try:
        from ingest import main

        sys.exit(main())
    finally:
        sys.argv = old_argv
