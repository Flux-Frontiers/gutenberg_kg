"""Status subcommand — corpus-level stats from the KGRAG registry."""

from __future__ import annotations

import json
import re
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import CORPUS_ROOT, REPO_ROOT
from gutenberg_kg.corpus import (
    GENRE_LABELS,
    collect_genre_stats,
    corpus_status,
)
from gutenberg_kg.corpus import (
    _sqlite_counts as _corpus_sqlite_counts,
)

_REGISTRY_DEFAULT = Path.home() / ".kgrag" / "registry.sqlite"

# Aliases and thin wrappers kept here so tests can import them from this module.
_GENRE_LABELS: dict[str, str] = GENRE_LABELS


def _genre_corpus_name(slug: str) -> str:
    """Return the gutenberg corpus name for a genre slug."""
    if slug.startswith("gutenberg-"):
        return slug
    return f"gutenberg-{slug}"


def _count_book_dirs(directory: Path) -> int:
    """Count non-hidden subdirectories in *directory*."""
    if not directory.is_dir():
        return 0
    return sum(1 for p in directory.iterdir() if p.is_dir() and not p.name.startswith("."))


def _collect_genre_stats(registry_path: Path) -> list[dict]:
    """Aggregate per-genre stats from the KGRAG registry."""
    return collect_genre_stats(registry_path)


def _sqlite_counts(path: str | None) -> tuple[int, int]:
    """Return (nodes, edges) from a graph.sqlite, or (0, 0) on any error."""
    return _corpus_sqlite_counts(path)


# ---------------------------------------------------------------------------
# README badge helpers (CLI/presentation concern — stays here)
# ---------------------------------------------------------------------------

_BADGE_PATTERNS = {
    "corpus": re.compile(r"corpus-\d+%20books"),
    "nodes": re.compile(r"nodes-[\d\.]+[KM]?"),
    "edges": re.compile(r"edges-[\d\.]+[KM]?"),
}


def _fmt_badge_nodes(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n // 1_000}K"
    return str(n)


def _update_readme_badges(
    readme: Path, total_books: int, total_nodes: int, total_edges: int
) -> bool:
    """Patch badge lines in README.md. Returns True if file was modified."""
    text = readme.read_text(encoding="utf-8")
    new_text = text
    new_text = _BADGE_PATTERNS["corpus"].sub(f"corpus-{total_books}%20books", new_text)
    new_text = _BADGE_PATTERNS["nodes"].sub(f"nodes-{_fmt_badge_nodes(total_nodes)}", new_text)
    new_text = _BADGE_PATTERNS["edges"].sub(f"edges-{_fmt_badge_nodes(total_edges)}", new_text)
    if new_text == text:
        return False
    readme.write_text(new_text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@cli.command("status")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit machine-readable JSON.")
@click.option(
    "--update-readme",
    is_flag=True,
    default=False,
    help="Patch corpus/node/edge badges in README.md.",
)
@click.option(
    "--registry",
    default=None,
    metavar="PATH",
    help="Override the KGRAG registry path.",
)
def status(as_json: bool, update_readme: bool, registry: str | None) -> None:
    """Show live corpus statistics from the KGRAG registry.

    Reads per-book SQLite databases directly — no rebuild required. Suitable
    for CI health checks and badge maintenance.

    :param as_json: Emit JSON instead of a Rich table.
    :param update_readme: Patch badge URLs in README.md after displaying stats.
    :param registry: Override the KGRAG registry path.
    """
    registry_path = Path(registry) if registry else _REGISTRY_DEFAULT
    if not registry_path.exists():
        raise click.ClickException(f"Registry not found: {registry_path}")

    result = corpus_status(registry_path, REPO_ROOT, CORPUS_ROOT)
    totals = result["totals"]

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        _print_rich_table(
            result["genres"],
            totals["books"],
            totals["nodes"],
            totals["edges"],
            totals["authors"],
            result["version"],
        )

    if update_readme:
        readme = REPO_ROOT / "README.md"
        changed = _update_readme_badges(readme, totals["books"], totals["nodes"], totals["edges"])
        if changed:
            click.echo(
                f"\n[✓] README.md badges updated ({totals['books']} books, "
                f"{_fmt_badge_nodes(totals['nodes'])} nodes, "
                f"{_fmt_badge_nodes(totals['edges'])} edges)"
            )
        else:
            click.echo("\n[=] README.md badges already up-to-date")


def _print_rich_table(
    genre_stats: list[dict],
    total_books: int,
    total_nodes: int,
    total_edges: int,
    total_authors: int,
    version: str,
) -> None:
    try:
        from rich.console import Console  # pylint: disable=import-outside-toplevel
        from rich.table import Table  # pylint: disable=import-outside-toplevel

        console = Console()
        table = Table(title=f"GutenbergKG Corpus Status  v{version}", show_footer=True)

        table.add_column("Genre", style="cyan", footer="Total")
        table.add_column("Books", justify="right", footer=str(total_books))
        table.add_column("Nodes", justify="right", footer=f"{total_nodes:,}")
        table.add_column("Edges", justify="right", footer=f"{total_edges:,}")

        for g in genre_stats:
            table.add_row(g["label"], str(g["books"]), f"{g['nodes']:,}", f"{g['edges']:,}")

        console.print(table)
        console.print(f"  Authors: {total_authors}  |  Registry: {_REGISTRY_DEFAULT}")

    except ImportError:
        header = f"{'Genre':<32} {'Books':>6} {'Nodes':>10} {'Edges':>12}"
        sep = "-" * len(header)
        click.echo(f"\nGutenbergKG Corpus Status  v{version}")
        click.echo(sep)
        click.echo(header)
        click.echo(sep)
        for g in genre_stats:
            click.echo(f"{g['label']:<32} {g['books']:>6} {g['nodes']:>10,} {g['edges']:>12,}")
        click.echo(sep)
        click.echo(f"{'Total':<32} {total_books:>6} {total_nodes:>10,} {total_edges:>12,}")
        click.echo(f"\nAuthors: {total_authors}")
