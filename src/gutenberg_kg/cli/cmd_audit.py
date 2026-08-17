"""audit subcommand — verify Project Gutenberg corpus integrity."""

import click

from gutenberg_kg import audit as au
from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES


@cli.command("audit")
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    multiple=True,
    help="Genre to audit (repeatable; default: all).",
)
@click.option(
    "--json", "as_json", is_flag=True, default=False, help="Emit JSON instead of a table."
)
@click.option(
    "--registry",
    type=click.Path(),
    default=None,
    help="Override the KGRAG registry path.",
)
def audit(genre, as_json, registry):
    """Verify corpus integrity and report problems.

    Checks every book for a present, parseable full-text ``.md`` and
    ``reference.md``; that diaries parse with their ``.diary_format`` and carry a
    ``.diarykg/`` (never a stray ``.dockg/``); that no Gutenberg ID is shared by
    two books; and that registered KGs point at an existing index of the right
    type.  "Not built" / "not registered" are warnings (expected before a
    rebuild); anything else is an error.

    Exits non-zero when any error is found, so it is safe to run in CI.
    \f

    :param genre: Tuple of genres to audit (empty = all).
    :param as_json: Emit machine-readable JSON.
    :param registry: Override the KGRAG registry path.
    """
    rc = au.run_audit(list(genre), registry=registry, as_json=as_json)
    if rc != 0:
        raise SystemExit(rc)
