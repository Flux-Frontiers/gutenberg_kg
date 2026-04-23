"""Shared Click options and constants for the GutenbergKG CLI."""
from pathlib import Path

import click

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_GENRES = [
    "ancient-classical",
    "shakespeare",
    "english-literature",
    "american-literature",
    "french-literature",
    "russian-literature",
    "philosophy",
    "spanish",
    "science-fiction",
]

# src/gutenberg_kg/cli/options.py
#   .parents[0] = src/gutenberg_kg/cli/
#   .parents[1] = src/gutenberg_kg/
#   .parents[2] = src/
#   .parents[3] = repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
CORPUS_ROOT = REPO_ROOT / "corpus"


# ---------------------------------------------------------------------------
# Reusable option factories
# ---------------------------------------------------------------------------

def genre_option(multiple: bool = False):
    """Return a --genre Click option decorator.

    :param multiple: If True, allow repeated ``--genre`` flags.
    :return: A Click option decorator.
    """
    if multiple:
        return click.option(
            "--genre",
            type=click.Choice(ALL_GENRES),
            multiple=True,
            help="Genre to process (repeatable; default: all).",
        )
    return click.option(
        "--genre",
        type=click.Choice(ALL_GENRES),
        default=None,
        help="Genre subdirectory for the book.",
    )


def dry_run_option():
    """Return a --dry-run Click flag decorator."""
    return click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Print actions without executing anything.",
    )


def force_option():
    """Return a --force Click flag decorator."""
    return click.option(
        "--force",
        is_flag=True,
        default=False,
        help="Overwrite existing files.",
    )


def push_option():
    """Return a --push Click flag decorator."""
    return click.option(
        "--push",
        is_flag=True,
        default=False,
        help="git add + commit + push after completion.",
    )


def force_build_option():
    """Return a --force-build Click flag decorator."""
    return click.option(
        "--force-build",
        is_flag=True,
        default=False,
        help="Rebuild DocKG even if .dockg already exists.",
    )


def force_register_option():
    """Return a --force-register Click flag decorator."""
    return click.option(
        "--force-register",
        is_flag=True,
        default=False,
        help="Re-register even if KG name already in registry.",
    )
