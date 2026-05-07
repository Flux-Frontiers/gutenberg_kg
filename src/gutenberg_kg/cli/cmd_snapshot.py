"""Snapshot subcommands — capture and review point-in-time corpus metrics."""

from __future__ import annotations

import json
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import CORPUS_ROOT, REPO_ROOT
from gutenberg_kg.corpus import snapshot_diff as _snapshot_diff
from gutenberg_kg.corpus import snapshot_list as _snapshot_list
from gutenberg_kg.corpus import snapshot_save as _snapshot_save
from gutenberg_kg.corpus import snapshot_show as _snapshot_show

_REGISTRY_DEFAULT = Path.home() / ".kgrag" / "registry.sqlite"
SNAPSHOTS_DIR = CORPUS_ROOT / ".snapshots"


# ---------------------------------------------------------------------------
# Private helpers (thin wrappers; kept here for testability)
# ---------------------------------------------------------------------------


def _snapshot_filename(ts: str) -> str:
    """Return a safe snapshot filename for a given ISO timestamp."""
    safe = ts.replace(":", "-").replace("+", "").split(".")[0]
    return f"snapshot-{safe}.json"


def _load_snapshot(path: Path) -> dict:
    """Load and return a snapshot dict from *path*."""
    return json.loads(path.read_text(encoding="utf-8"))


def _list_snapshots() -> list[Path]:
    """Return snapshot Paths from SNAPSHOTS_DIR, sorted ascending."""
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

    out_path, snap = _snapshot_save(
        registry_path,
        REPO_ROOT,
        CORPUS_ROOT,
        Path(output) if output else None,
    )

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
    snaps = _snapshot_list(SNAPSHOTS_DIR)
    if not snaps:
        click.echo("No snapshots found in corpus/.snapshots/")
        return

    header = (
        f"  {'Timestamp':<26} {'Version':<8} {'Branch':<20} "
        f"{'Commit':<8} {'Books':>6} {'Nodes':>10} {'Edges':>12}"
    )
    click.echo(header)
    click.echo("  " + "-" * (len(header) - 2))

    for snap in snaps:
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


@snapshot.command("show")
@click.argument("snapshot_name", metavar="SNAPSHOT", required=False)
def snapshot_show(snapshot_name: str | None) -> None:
    """Show full JSON for a snapshot (default: most recent).

    :param snapshot_name: Filename or timestamp prefix of the snapshot.
    """
    snap = _snapshot_show(SNAPSHOTS_DIR, snapshot_name)
    if not snap:
        msg = f"No snapshot matching {snapshot_name!r}" if snapshot_name else "No snapshots found"
        raise click.ClickException(msg)
    click.echo(json.dumps(snap, indent=2))


@snapshot.command("diff")
@click.argument("a", metavar="SNAPSHOT_A", required=False)
@click.argument("b", metavar="SNAPSHOT_B", required=False)
def snapshot_diff(a: str | None, b: str | None) -> None:
    """Compare two snapshots (default: second-to-last vs last).

    :param a: First snapshot filename or prefix.
    :param b: Second snapshot filename or prefix.
    """
    result = _snapshot_diff(SNAPSHOTS_DIR, a, b)
    if "error" in result:
        raise click.ClickException(result["error"])

    sa, sb = result["a"], result["b"]
    click.echo(f"  A: {sa['timestamp']}  v{sa['version']}  {sa['commit']}")
    click.echo(f"  B: {sb['timestamp']}  v{sb['version']}  {sb['commit']}")
    click.echo("")

    def _fmt(d: dict) -> str:
        sign = "+" if d["delta"] >= 0 else ""
        return f"{d['after']:,} ({sign}{d['delta']:,})"

    totals = result["totals"]
    click.echo(f"  Books:  {_fmt(totals['books'])}")
    click.echo(f"  Nodes:  {_fmt(totals['nodes'])}")
    click.echo(f"  Edges:  {_fmt(totals['edges'])}")

    changed = result.get("changed_genres", [])
    if changed:
        click.echo("\n  Changed genres:")
        for g in changed:
            dn = g["nodes"]["delta"]
            sign = "+" if dn >= 0 else ""
            label = g["corpus"].replace("gutenberg-", "")
            click.echo(
                f"    {label:<32}  books {g['books']['before']}→{g['books']['after']}  "
                f"nodes {g['nodes']['before']:,}→{g['nodes']['after']:,} ({sign}{dn:,})"
            )
