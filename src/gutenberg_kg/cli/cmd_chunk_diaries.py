"""chunk-diaries subcommand — rebuild ``.diary/`` chunk corpora from book ``.md``."""

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.diary import chunk as ch


@cli.command("chunk-diaries")
@click.option(
    "--diary",
    "diary_names",
    multiple=True,
    metavar="NAME",
    help=(
        "Diary directory name to chunk (repeatable; default: all diaries). "
        "Must match an exact subdirectory name under corpus/diaries/."
    ),
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Re-chunk even if .diary/ already exists.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the chunking plan without executing.",
)
def chunk_diaries(diary_names, force, dry_run):
    """Rebuild ``.diary/`` chunk corpora from committed book ``.md`` files.

    Stages ①② of the diary pipeline: parse each diary's full-text markdown into
    a dated ``.diary_source.psv`` (Gutenberg-specific parsing, format chosen per
    book via ``.diary_format``), then chunk it into ``.diary/`` via
    ``diary_transformer``.

    Both ``.diary/`` and ``.diary_source.psv`` are git-ignored, so run this once
    after cloning to reconstruct them, then run ``gutenkg build-diaries`` to
    build the ``.diarykg/`` indices.

    Skips diaries that already have a non-empty ``.diary/``; use ``--force`` to
    rebuild.

    :param diary_names: Tuple of diary directory names (empty = all diaries).
    :param force: Re-chunk existing ``.diary/`` corpora.
    :param dry_run: Print the plan without executing.
    """
    opts = ch.ChunkDiariesOptions(force=force, dry_run=dry_run)
    rc = ch.run_chunk_diaries(list(diary_names), opts)
    if rc != 0:
        raise SystemExit(rc)
