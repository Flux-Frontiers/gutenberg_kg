"""Genre registry subcommands."""

import click

from gutenberg_kg import genres as _gr
from gutenberg_kg.cli.main import cli


@cli.group("genres")
def genres_group():
    """Manage the corpus genre registry (corpus/genres.json)."""


@genres_group.command("init")
@click.option("--force", is_flag=True, default=False, help="Overwrite existing registry.")
def genres_init(force: bool) -> None:
    """Seed corpus/genres.json from built-in defaults."""
    written = _gr.seed_registry(force=force)
    if written:
        click.echo(f"Created {_gr._REGISTRY_PATH}")
    else:
        click.echo(f"Already exists: {_gr._REGISTRY_PATH}  (use --force to overwrite)")


@genres_group.command("list")
def genres_list() -> None:
    """List all registered genres."""
    data = _gr._load()
    for source, names in data.items():
        click.echo(f"[{source}]")
        for name in names:
            click.echo(f"  {name}")


@genres_group.command("add")
@click.argument("name")
@click.option(
    "--source",
    type=click.Choice(["gutenberg", "ia"]),
    required=True,
    help="Content source for this genre.",
)
def genres_add(name: str, source: str) -> None:
    """Add NAME to the genre registry under SOURCE."""
    if not _gr._REGISTRY_PATH.exists():
        _gr.seed_registry()
        click.echo(f"Initialized {_gr._REGISTRY_PATH}")
    added = _gr.add_genre(name, source)
    if added:
        click.echo(f"Added '{name}' ({source}) to {_gr._REGISTRY_PATH}")
    else:
        click.echo(f"'{name}' is already registered under '{source}'")
