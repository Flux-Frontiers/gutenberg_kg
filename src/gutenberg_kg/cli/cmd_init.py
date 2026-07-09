"""init subcommand — fetch the local ML models the pipeline needs."""

import click

from gutenberg_kg import model_setup as ms
from gutenberg_kg.cli.main import cli

_STATUS_MARK = {
    "ok": "=",
    "downloaded": "+",
    "missing": "x",
    "failed": "x",
}


@cli.command("init")
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Only report model status; don't download anything missing.",
)
def init(check: bool) -> None:
    """Ensure the spaCy and embedder models used locally are present.

    Run this once after cloning + ``poetry install`` (or ``pip install -e .``),
    before ``gutenkg chunk-diaries`` / ``ingest`` / ``build-corpus`` — those
    fail mid-run if a model is missing, which this catches up front instead.
    Docker builds don't need this: the image pre-downloads the embedder at
    build time and never runs spaCy at runtime.

    :param check: Report status only; skip downloading missing models.
    """
    results = ms.check_models(download=not check)

    failed = False
    for r in results:
        mark = _STATUS_MARK[r.status]
        click.echo(f"  [{mark}] {r.kind:<9} {r.name:<28} {r.status:<10} {r.message}")
        if r.status in ("missing", "failed"):
            failed = True

    if failed:
        raise SystemExit(1)
