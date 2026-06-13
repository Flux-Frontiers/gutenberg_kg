"""build-diaries subcommand — build .diarykg/ DocKG indices for diary corpora."""

import click

from gutenberg_kg import build_diaries as bd
from gutenberg_kg.cli.main import cli


@cli.command("build-diaries")
@click.option(
    "--diary",
    "diary_names",
    multiple=True,
    metavar="NAME",
    help=(
        "Diary directory name to build (repeatable; default: all diaries). "
        "Must match an exact subdirectory name under corpus/diaries/."
    ),
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Rebuild even if .diarykg/graph.sqlite already exists.",
)
@click.option(
    "--workers",
    type=int,
    default=4,
    show_default=True,
    help="Embedding worker processes.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the build plan without executing.",
)
@click.option(
    "--quiet",
    is_flag=True,
    default=False,
    help="Suppress per-stage DocKG progress output.",
)
def build_diaries(diary_names, force, workers, dry_run, quiet):
    """Build .diarykg/ DocKG indices for diary corpora under corpus/diaries/.

    Each diary must have a pre-built .diary/ directory of chunked entry files
    (produced by 'gutenkg chunk-diaries' from the committed <book>.md).  This
    command runs the DocKG build over those chunks and writes the resulting
    graph.sqlite + lancedb index into .diarykg/ — the prerequisite for
    'build-corpus', which copies these indices verbatim into the bundle.

    Uses sentence_group chunking and disables SIMILAR_TO edges, matching the
    temporal structure of diary entries (see docs/ingestion-pipeline.md).

    Build flags applied to all diaries:

    \b
      --chunk-strategy sentence_group
      --no-similar
      --model BAAI/bge-small-en-v1.5

    Skips diaries that already have a .diarykg/graph.sqlite; use --force to
    rebuild.

    :param diary_names: Tuple of diary directory names (empty = all diaries).
    :param force: Rebuild existing indices.
    :param workers: Embedding worker processes.
    :param dry_run: Print the plan without building.
    :param quiet: Suppress per-stage progress output.
    """
    opts = bd.BuildDiariesOptions(
        force=force,
        n_workers=workers,
        dry_run=dry_run,
        quiet=quiet,
    )
    rc = bd.run_build_diaries(list(diary_names), opts)
    if rc != 0:
        raise SystemExit(rc)
