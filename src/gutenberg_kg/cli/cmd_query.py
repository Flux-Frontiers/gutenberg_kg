"""gutenkg query — search the locally ingested GutenbergKG corpus."""

from __future__ import annotations

import subprocess

import click

from gutenberg_kg.cli.main import cli


def _run_query(query: str, corpus: str, k: int, registry: str | None, as_json: bool) -> int:
    """Run a local federated KGRAG query.

    :param query: Natural-language search query.
    :param corpus: Local KGRAG corpus name.
    :param k: Number of results per knowledge graph.
    :param registry: Optional KGRAG registry path override.
    :param as_json: Request JSON output.
    :returns: The KGRAG process exit status.
    :raises click.ClickException: If KGRAG is not installed.
    """
    command = ["kgrag", "corpus", "query", corpus, query, "-k", str(k)]
    if registry:
        command.extend(("--registry", registry))
    if as_json:
        command.append("--json")

    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError as exc:
        raise click.ClickException(
            "Query support requires KGRAG. Install the project's full dependencies first."
        ) from exc


@cli.command("query")
@click.argument("query")
@click.option(
    "--corpus",
    default="gutenberg-all",
    show_default=True,
    help="Locally registered corpus to search.",
)
@click.option(
    "--k",
    default=8,
    show_default=True,
    type=click.IntRange(min=1),
    help="Number of results per knowledge graph.",
)
@click.option("--registry", metavar="PATH", help="Override the local KGRAG registry path.")
@click.option("--json", "as_json", is_flag=True, help="Emit KGRAG results as JSON.")
def query_cmd(query: str, corpus: str, k: int, registry: str | None, as_json: bool) -> None:
    """Search the locally ingested corpus; Docker is not required.

    Run ``gutenkg ingest`` first to build the per-book indices and register them
    in the local KGRAG registry.

    \b
    Examples:
      gutenkg query "the nature of justice"
      gutenkg query "characters who seek revenge" --corpus gutenberg-russian-literature

    :param query: Natural-language search query.
    :param corpus: Local KGRAG corpus name.
    :param k: Number of results per knowledge graph.
    :param registry: Optional KGRAG registry path override.
    :param as_json: Emit KGRAG results as JSON.
    """
    raise SystemExit(_run_query(query, corpus, k, registry, as_json))
