"""Snapshot subcommands — capture and review point-in-time corpus metrics."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import CORPUS_ROOT, REPO_ROOT

# Snapshots are stored in corpus/.snapshots/ — gitignored alongside .dockg/
SNAPSHOTS_DIR = CORPUS_ROOT / ".snapshots"

# Mirrors cmd_status._REGISTRY_DEFAULT — kept local to avoid a circular import
# (main.py imports both cmd_status and cmd_snapshot at startup).
_REGISTRY_DEFAULT = Path.home() / ".kgrag" / "registry.sqlite"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_info(repo_root: Path) -> dict[str, str]:
    def _run(*args: str) -> str:
        try:
            return subprocess.check_output(
                list(args), cwd=repo_root, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:  # pylint: disable=broad-exception-caught
            return "unknown"

    return {
        "branch": _run("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _run("git", "rev-parse", "--short", "HEAD"),
        "commit_full": _run("git", "rev-parse", "HEAD"),
    }


def _build_snapshot(registry_path: Path) -> dict:
    """Collect corpus metrics and return a snapshot dict."""
    from gutenberg_kg.cli.cmd_status import _collect_genre_stats  # lazy — avoids circular import

    genre_stats = _collect_genre_stats(registry_path)
    total_books = sum(g["books"] for g in genre_stats)
    total_nodes = sum(g["nodes"] for g in genre_stats)
    total_edges = sum(g["edges"] for g in genre_stats)

    authors_dir = CORPUS_ROOT / "authors"
    total_authors = (
        sum(1 for p in authors_dir.iterdir() if p.is_dir()) if authors_dir.is_dir() else 0
    )

    git = _git_info(REPO_ROOT)
    version = importlib.metadata.version("gutenberg-kg")
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")

    return {
        "kind": "corpus_snapshot",
        "schema_version": 1,
        "timestamp": timestamp,
        "version": version,
        "branch": git["branch"],
        "commit": git["commit"],
        "commit_full": git["commit_full"],
        "totals": {
            "books": total_books,
            "authors": total_authors,
            "nodes": total_nodes,
            "edges": total_edges,
        },
        "genres": genre_stats,
    }


def _snapshot_filename(timestamp: str) -> str:
    # timestamp is ISO-8601; make it filename-safe
    safe = timestamp.replace(":", "-").replace("+", "").split(".")[0]
    return f"snapshot-{safe}.json"


def _load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _list_snapshots() -> list[Path]:
    if not SNAPSHOTS_DIR.is_dir():
        return []
    return sorted(SNAPSHOTS_DIR.glob("snapshot-*.json"))


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@cli.group("snapshot")
def snapshot() -> None:
    """Capture and review point-in-time corpus metrics."""


@snapshot.command("save")
@click.option(
    "--registry",
    default=None,
    metavar="PATH",
    help="Override the KGRAG registry path.",
)
@click.option(
    "--output",
    default=None,
    metavar="PATH",
    help="Output path (default: corpus/.snapshots/snapshot-<timestamp>.json).",
)
@click.option(
    "--print", "print_snapshot", is_flag=True, default=False, help="Also print JSON to stdout."
)
def snapshot_save(registry: str | None, output: str | None, print_snapshot: bool) -> None:
    """Capture current corpus metrics and save as a timestamped snapshot.

    Snapshots are stored in ``corpus/.snapshots/`` alongside the .dockg
    directories. They capture total/per-genre book counts, node counts,
    and edge counts at a point in time, keyed by timestamp, version, and
    git commit.

    :param registry: Override the KGRAG registry path.
    :param output: Override the output file path.
    :param print_snapshot: Print the snapshot JSON to stdout as well.
    """
    registry_path = Path(registry) if registry else _REGISTRY_DEFAULT
    if not registry_path.exists():
        raise click.ClickException(f"Registry not found: {registry_path}")

    snap = _build_snapshot(registry_path)

    if output:
        out_path = Path(output)
    else:
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = SNAPSHOTS_DIR / _snapshot_filename(snap["timestamp"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")

    t = snap["totals"]
    click.echo(
        f"[✓] Snapshot saved: {out_path.name}\n"
        f"    {t['books']} books  {t['nodes']:,} nodes  {t['edges']:,} edges  "
        f"(v{snap['version']}, {snap['commit']})"
    )

    if print_snapshot:
        click.echo(json.dumps(snap, indent=2))


@snapshot.command("list")
def snapshot_list() -> None:
    """List all saved corpus snapshots."""
    paths = _list_snapshots()
    if not paths:
        click.echo("No snapshots found in corpus/.snapshots/")
        return

    header = f"  {'Timestamp':<26} {'Version':<8} {'Branch':<20} {'Commit':<8} {'Books':>6} {'Nodes':>10} {'Edges':>12}"
    click.echo(header)
    click.echo("  " + "-" * (len(header) - 2))

    for p in paths:
        try:
            snap = _load_snapshot(p)
            t = snap.get("totals", {})
            click.echo(
                f"  {snap.get('timestamp', ''):<26} "
                f"{snap.get('version', ''):<8} "
                f"{snap.get('branch', ''):<20} "
                f"{snap.get('commit', ''):<8} "
                f"{t.get('books', 0):>6} "
                f"{t.get('nodes', 0):>10,} "
                f"{t.get('edges', 0):>12,}"
            )
        except Exception:  # pylint: disable=broad-exception-caught
            click.echo(f"  {p.name}  [unreadable]")


@snapshot.command("show")
@click.argument("snapshot_name", metavar="SNAPSHOT", required=False)
def snapshot_show(snapshot_name: str | None) -> None:
    """Show full JSON for a snapshot (default: most recent).

    :param snapshot_name: Filename or timestamp prefix of the snapshot.
    """
    paths = _list_snapshots()
    if not paths:
        raise click.ClickException("No snapshots found in corpus/.snapshots/")

    if snapshot_name:
        matches = [p for p in paths if snapshot_name in p.name]
        if not matches:
            raise click.ClickException(f"No snapshot matching {snapshot_name!r}")
        path = matches[-1]
    else:
        path = paths[-1]

    click.echo(path.read_text(encoding="utf-8"))


@snapshot.command("diff")
@click.argument("a", metavar="SNAPSHOT_A", required=False)
@click.argument("b", metavar="SNAPSHOT_B", required=False)
def snapshot_diff(a: str | None, b: str | None) -> None:
    """Compare two snapshots (default: second-to-last vs last).

    :param a: First snapshot filename or prefix.
    :param b: Second snapshot filename or prefix.
    """
    paths = _list_snapshots()
    if len(paths) < 2:
        raise click.ClickException("Need at least two snapshots to diff.")

    def _resolve(name: str | None, fallback: Path) -> dict:
        if name is None:
            return _load_snapshot(fallback)
        matches = [p for p in paths if name in p.name]
        if not matches:
            raise click.ClickException(f"No snapshot matching {name!r}")
        return _load_snapshot(matches[-1])

    snap_a = _resolve(a, paths[-2])
    snap_b = _resolve(b, paths[-1])

    ta, tb = snap_a.get("totals", {}), snap_b.get("totals", {})

    def _delta(key: str) -> str:
        va, vb = ta.get(key, 0), tb.get(key, 0)
        diff = vb - va
        sign = "+" if diff >= 0 else ""
        return f"{vb:,} ({sign}{diff:,})"

    click.echo(f"  A: {snap_a.get('timestamp')}  v{snap_a.get('version')}  {snap_a.get('commit')}")
    click.echo(f"  B: {snap_b.get('timestamp')}  v{snap_b.get('version')}  {snap_b.get('commit')}")
    click.echo("")
    click.echo(f"  Books:  {_delta('books')}")
    click.echo(f"  Nodes:  {_delta('nodes')}")
    click.echo(f"  Edges:  {_delta('edges')}")

    # Per-genre diff
    genre_a = {g["corpus"]: g for g in snap_a.get("genres", [])}
    genre_b = {g["corpus"]: g for g in snap_b.get("genres", [])}
    all_corpora = sorted(set(genre_a) | set(genre_b))

    changed = []
    for corpus in all_corpora:
        ga = genre_a.get(corpus, {"books": 0, "nodes": 0, "edges": 0})
        gb = genre_b.get(corpus, {"books": 0, "nodes": 0, "edges": 0})
        if ga["books"] != gb["books"] or ga["nodes"] != gb["nodes"]:
            changed.append((corpus, ga, gb))

    if changed:
        click.echo("\n  Changed genres:")
        for corpus, ga, gb in changed:
            dn = gb["nodes"] - ga["nodes"]
            sign = "+" if dn >= 0 else ""
            label = corpus.replace("gutenberg-", "")
            click.echo(
                f"    {label:<32}  books {ga['books']}→{gb['books']}  "
                f"nodes {ga['nodes']:,}→{gb['nodes']:,} ({sign}{dn:,})"
            )
