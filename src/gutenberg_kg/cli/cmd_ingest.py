"""Ingest subcommands — build DocKG indices and register with KGRAG."""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES, CORPUS_ROOT

# ---------------------------------------------------------------------------
# Lazy script import helper
# ---------------------------------------------------------------------------

def _ingest_mod():
    """Import ingest from the scripts directory on first use."""
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import ingest as _mod  # noqa: PLC0415
    return _mod


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@cli.command("ingest")
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    multiple=True,
    help="Genre to process (repeatable; default: all).",
)
@click.option(
    "--force-build",
    is_flag=True,
    default=False,
    help="Rebuild DocKG even if .dockg already exists.",
)
@click.option(
    "--force-register",
    is_flag=True,
    default=False,
    help="Re-register even if KG name already in registry.",
)
@click.option(
    "--push",
    is_flag=True,
    default=False,
    help="git add + commit + push after each genre completes.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print actions without executing anything.",
)
@click.option(
    "--registry",
    default=None,
    metavar="PATH",
    help="Override the KGRAG registry path.",
)
def ingest(genre, force_build, force_register, push, dry_run, registry):
    """Build DocKG indices, register with KGRAG, and optionally push to git.

    :param genre: Tuple of genres to process (empty = all genres).
    :param force_build: Rebuild even if .dockg already exists.
    :param force_register: Re-register even if already in the registry.
    :param push: Push to git after each genre completes.
    :param dry_run: Print what would be done without executing.
    :param registry: Override the KGRAG registry path.
    """
    from kg_rag.corpus_registry import CorpusRegistry
    from kg_rag.registry import KGRegistry, default_registry_path

    ig = _ingest_mod()

    genres = list(genre) if genre else ALL_GENRES
    registry_path = Path(registry).resolve() if registry else default_registry_path()

    unknown = [g for g in genres if g not in ALL_GENRES]
    if unknown:
        click.echo(
            f"ERROR: unknown genre(s): {', '.join(unknown)}", err=True
        )
        click.echo(f"Valid genres: {', '.join(ALL_GENRES)}", err=True)
        raise SystemExit(1)

    opts = ig.IngestOptions(
        force_build=force_build,
        force_register=force_register,
        dry_run=dry_run,
        push=push,
    )

    if opts.dry_run:
        click.echo("[DRY RUN — no changes will be made]\n")

    genre_summaries = []
    wall_start = datetime.now(timezone.utc)
    wall_t0 = time.perf_counter()

    with KGRegistry(db_path=registry_path) as kg_reg, \
         CorpusRegistry(db_path=registry_path) as corp_reg:

        click.echo("--- Ensuring corpora ---")
        for g in genres:
            ig.ensure_corpus(
                corp_reg,
                f"gutenberg-{g}",
                description=f"Project Gutenberg — {g}",
                dry_run=opts.dry_run,
            )
        ig.ensure_corpus(
            corp_reg,
            "gutenberg-all",
            description="Project Gutenberg — complete library",
            dry_run=opts.dry_run,
        )
        click.echo("")

        for g in genres:
            genre_dir = CORPUS_ROOT / g
            if not genre_dir.is_dir():
                click.echo(f"[!] Genre directory not found: {genre_dir} — skipping\n")
                continue

            book_dirs = sorted(
                p for p in genre_dir.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            )
            if not book_dirs:
                click.echo(f"[!] No book directories in {genre_dir} — skipping\n")
                continue

            click.echo(f"=== {g} ({len(book_dirs)} books) ===")
            genre_summary = ig.GenreSummary(genre=g)
            for book_dir in book_dirs:
                result = ig.process_book(
                    book_dir=book_dir,
                    genre=g,
                    kg_reg=kg_reg,
                    corp_reg=corp_reg,
                    opts=opts,
                )
                genre_summary.results.append(result)

            genre_summaries.append(genre_summary)

            if opts.push:
                ig.git_commit_push_genre(genre_dir, g, dry_run=opts.dry_run)
            click.echo("")

    wall_elapsed = time.perf_counter() - wall_t0
    ig.print_summary(genre_summaries, opts, registry_path, wall_start, wall_elapsed)

    report_path = ig.save_summary(
        genre_summaries, opts, registry_path, wall_start, wall_elapsed
    )
    click.echo(f"  Report saved: {report_path}\n")

    if any(g.failed for g in genre_summaries):
        raise SystemExit(1)


@cli.command("list-genres")
def list_genres():
    """Print all known Gutenberg genres."""
    click.echo("Known genres:")
    for g in ALL_GENRES:
        click.echo(f"  {g}")
