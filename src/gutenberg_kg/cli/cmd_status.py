"""Status subcommand — corpus-level stats from the KGRAG registry."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import re
import socket
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import CORPUS_ROOT, REPO_ROOT

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

_REGISTRY_DEFAULT = Path.home() / ".kgrag" / "registry.sqlite"

# Maps corpus slug → display label (order determines table row order)
_GENRE_LABELS: dict[str, str] = {
    "gutenberg-english-literature": "English Literature",
    "gutenberg-ancient-classical": "Ancient & Classical",
    "gutenberg-philosophy": "Philosophy",
    "gutenberg-russian-literature": "Russian Literature",
    "gutenberg-american-literature": "American Literature",
    "gutenberg-french-literature": "French Literature",
    "gutenberg-science-fiction": "Science Fiction",
    "gutenberg-world-literature": "World Literature",
    "gutenberg-sacred-texts": "Sacred Texts",
    "gutenberg-german-literature": "German Literature",
    "gutenberg-spanish": "Spanish Literature",
    "gutenberg-shakespeare": "Shakespeare",
    "gutenberg-audel-electric": "Technical Reference (IA)",
}


def _genre_corpus_name(genre_slug: str) -> str:
    return f"gutenberg-{genre_slug}"


def _count_book_dirs(genre_dir: Path) -> int:
    if not genre_dir.is_dir():
        return 0
    return sum(1 for p in genre_dir.iterdir() if p.is_dir() and not p.name.startswith("."))


def _count_authors() -> int:
    authors_dir = CORPUS_ROOT / "authors"
    if not authors_dir.is_dir():
        return 0
    return sum(1 for p in authors_dir.iterdir() if p.is_dir())


def _sqlite_counts(path: str | None) -> tuple[int, int]:
    """Return (nodes, edges) from a graph.sqlite, or (0, 0) on any error."""
    if not path:
        return 0, 0
    try:
        with sqlite3.connect(path) as con:
            nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return nodes, edges
    except Exception:  # pylint: disable=broad-exception-caught
        return 0, 0


def _collect_genre_stats(registry_path: Path) -> list[dict]:
    """Aggregate per-genre stats from the KGRAG registry.

    Returns a list of dicts with keys: corpus, label, books, nodes, edges.
    Only corpora whose sqlite files exist on disk are counted.
    """
    results = []
    try:
        reg = sqlite3.connect(str(registry_path))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise click.ClickException(f"Cannot open registry {registry_path}: {exc}") from exc

    # Build id → sqlite_path lookup once
    kg_map: dict[str, str | None] = {}
    for row in reg.execute("SELECT id, sqlite_path FROM kg_entries"):
        kg_map[row[0]] = row[1]

    for corpus_key, label in _GENRE_LABELS.items():
        row = reg.execute("SELECT kg_ids FROM corpora WHERE name = ?", (corpus_key,)).fetchone()
        if row is None:
            results.append(
                {"corpus": corpus_key, "label": label, "books": 0, "nodes": 0, "edges": 0}
            )
            continue

        kg_ids: list[str] = json.loads(row[0])
        total_nodes = total_edges = 0
        live_books = 0
        for kid in kg_ids:
            sqlite_path = kg_map.get(kid)
            if sqlite_path and Path(sqlite_path).exists():
                n, e = _sqlite_counts(sqlite_path)
                total_nodes += n
                total_edges += e
                live_books += 1

        results.append(
            {
                "corpus": corpus_key,
                "label": label,
                "books": live_books,
                "nodes": total_nodes,
                "edges": total_edges,
            }
        )

    reg.close()
    return results


def _git_branch(repo_root: Path) -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown"


def _git_commit(repo_root: Path) -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown"


# ---------------------------------------------------------------------------
# README badge update
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

    genre_stats = _collect_genre_stats(registry_path)

    total_books = sum(g["books"] for g in genre_stats)
    total_nodes = sum(g["nodes"] for g in genre_stats)
    total_edges = sum(g["edges"] for g in genre_stats)
    total_authors = _count_authors()
    version = importlib.metadata.version("gutenberg-kg")
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    branch = _git_branch(REPO_ROOT)
    commit = _git_commit(REPO_ROOT)

    if as_json:
        payload = {
            "kind": "corpus_status",
            "timestamp": timestamp,
            "version": version,
            "branch": branch,
            "commit": commit,
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "totals": {
                "books": total_books,
                "authors": total_authors,
                "nodes": total_nodes,
                "edges": total_edges,
            },
            "genres": genre_stats,
        }
        click.echo(json.dumps(payload, indent=2))
    else:
        _print_rich_table(
            genre_stats, total_books, total_nodes, total_edges, total_authors, version
        )

    if update_readme:
        readme = REPO_ROOT / "README.md"
        changed = _update_readme_badges(readme, total_books, total_nodes, total_edges)
        if changed:
            click.echo(
                f"\n[✓] README.md badges updated ({total_books} books, "
                f"{_fmt_badge_nodes(total_nodes)} nodes, {_fmt_badge_nodes(total_edges)} edges)"
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
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"GutenbergKG Corpus Status  v{version}", show_footer=True)

        table.add_column("Genre", style="cyan", footer="Total")
        table.add_column("Books", justify="right", footer=str(total_books))
        table.add_column("Nodes", justify="right", footer=f"{total_nodes:,}")
        table.add_column("Edges", justify="right", footer=f"{total_edges:,}")

        for g in genre_stats:
            table.add_row(
                g["label"],
                str(g["books"]),
                f"{g['nodes']:,}",
                f"{g['edges']:,}",
            )

        console.print(table)
        console.print(f"  Authors: {total_authors}  |  Registry: {_REGISTRY_DEFAULT}")

    except ImportError:
        # Fallback: plain text
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
