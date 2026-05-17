"""Snapshot subcommands — capture and review point-in-time corpus metrics.

Commands
--------
save   Capture current corpus metrics and save as a temporal snapshot.
list   List all temporal snapshots in reverse chronological order.
show   Display full details for a single snapshot by key (tree hash).
diff   Compare two snapshots side-by-side.
prune  Remove vestigial snapshots that carry no new metric information.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import CORPUS_ROOT, REPO_ROOT
from gutenberg_kg.corpus import GutenbergSnapshotManager

_REGISTRY_DEFAULT = Path.home() / ".kgrag" / "registry.sqlite"
SNAPSHOTS_DIR = CORPUS_ROOT / ".snapshots"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_manager(
    snapshots_dir: Path,
    registry_path: Path,
    corpus_root: Path,
    repo_root: Path = REPO_ROOT,
) -> GutenbergSnapshotManager:
    """Construct a manager from resolved paths."""
    return GutenbergSnapshotManager(
        snapshots_dir,
        registry_path=registry_path,
        repo_root=repo_root,
        corpus_root=corpus_root,
    )


def _resolve_two_keys(mgr: GutenbergSnapshotManager) -> tuple[str, str]:
    """Return the keys of the second-to-last and last snapshots.

    :raises click.ClickException: If fewer than two snapshots exist.
    """
    entries = mgr.list_snapshots()
    if len(entries) < 2:
        raise click.ClickException("Need at least two snapshots to diff.")
    return entries[1]["key"], entries[0]["key"]


def _fmt_delta(val: int | float, *, pct: bool = False) -> str:
    sign = "+" if val >= 0 else ""
    if pct:
        return f"{sign}{val:.1%}"
    return f"{sign}{val:,}"


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@cli.group("snapshot")
def snapshot() -> None:
    """Capture and review point-in-time corpus metrics."""


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


@snapshot.command("save")
@click.option(
    "--registry",
    default=None,
    metavar="PATH",
    help="Override the KGRAG registry path.",
)
@click.option(
    "--snapshots-dir",
    default=None,
    metavar="PATH",
    help="Override the snapshots directory (default: corpus/.snapshots).",
)
@click.option(
    "--corpus-root",
    default=None,
    metavar="PATH",
    help="Override the corpus root directory.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Force a new snapshot entry even if metrics are unchanged.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Print the full snapshot JSON to stdout after saving.",
)
def snapshot_save(
    registry: str | None,
    snapshots_dir: str | None,
    corpus_root: str | None,
    force: bool,
    output_json: bool,
) -> None:
    """Capture current corpus metrics and save as a temporal snapshot.

    Snapshots are stored in ``corpus/.snapshots/<tree-hash>.json`` alongside a
    ``manifest.json`` index.  Each entry records total and per-genre book /
    node / edge counts, the git tree hash, branch, and version.

    :param registry: Override the KGRAG registry path.
    :param snapshots_dir: Override the snapshots directory.
    :param corpus_root: Override the corpus root directory.
    :param force: Always create a new manifest entry.
    :param output_json: Print the full snapshot JSON to stdout.
    """
    registry_path = Path(registry) if registry else _REGISTRY_DEFAULT
    if not registry_path.exists():
        raise click.ClickException(f"Registry not found: {registry_path}")

    snap_dir = Path(snapshots_dir) if snapshots_dir else SNAPSHOTS_DIR
    c_root = Path(corpus_root) if corpus_root else CORPUS_ROOT

    mgr = _make_manager(snap_dir, registry_path, c_root)
    snap = mgr.capture()

    try:
        snap_file = mgr.save_snapshot(snap, force=force)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    m = snap.metrics
    click.echo(
        f"[✓] Snapshot saved: {snap_file.name}\n"
        f"    key={snap.key[:12]}  "
        f"books={m.get('total_books', 0)}  "
        f"nodes={m.get('total_nodes', 0):,}  "
        f"edges={m.get('total_edges', 0):,}  "
        f"(v{snap.version}, {snap.branch})"
    )

    if output_json:
        click.echo(json.dumps(snap.to_dict(), indent=2))


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@snapshot.command("list")
@click.option(
    "--snapshots-dir",
    default=None,
    metavar="PATH",
    help="Override the snapshots directory.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Maximum number of snapshots to show.",
)
@click.option(
    "--branch",
    default=None,
    metavar="BRANCH",
    help="Filter by branch name.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output as JSON.",
)
def snapshot_list(
    snapshots_dir: str | None,
    limit: int | None,
    branch: str | None,
    output_json: bool,
) -> None:
    """List all temporal snapshots in reverse chronological order.

    :param snapshots_dir: Override the snapshots directory.
    :param limit: Maximum snapshots to display.
    :param branch: Filter by branch name.
    :param output_json: Emit raw JSON instead of a table.
    """
    snap_dir = Path(snapshots_dir) if snapshots_dir else SNAPSHOTS_DIR
    mgr = GutenbergSnapshotManager(
        snap_dir,
        registry_path=_REGISTRY_DEFAULT,
        repo_root=REPO_ROOT,
        corpus_root=CORPUS_ROOT,
    )
    entries = mgr.list_snapshots(limit=limit, branch=branch)

    if not entries:
        click.echo("No snapshots found.")
        return

    if output_json:
        click.echo(json.dumps(entries, indent=2))
        return

    header = (
        f"  {'Key':<14} {'Timestamp':<20} {'Branch':<16} "
        f"{'Version':<8} {'Books':>6} {'Nodes':>10} {'Edges':>12}"
    )
    click.echo(header)
    click.echo("  " + "-" * (len(header) - 2))

    for e in entries:
        m = e.get("metrics", {})
        ts = e.get("timestamp", "")
        ts_display = ts[:16].replace("T", " ") if ts else ""
        click.echo(
            f"  {e.get('key', '')[:14]:<14} "
            f"{ts_display:<20} "
            f"{e.get('branch', '')[:16]:<16} "
            f"{e.get('version', '')[:8]:<8} "
            f"{m.get('total_books', 0):>6} "
            f"{m.get('total_nodes', 0):>10,} "
            f"{m.get('total_edges', 0):>12,}"
        )


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@snapshot.command("show")
@click.argument("key", metavar="KEY", default="latest", required=False)
@click.option(
    "--snapshots-dir",
    default=None,
    metavar="PATH",
    help="Override the snapshots directory.",
)
def snapshot_show(key: str, snapshots_dir: str | None) -> None:
    """Display full details for a snapshot.

    KEY is a tree-hash key or prefix (default: ``latest``).

    :param key: Tree-hash key or ``latest``.
    :param snapshots_dir: Override the snapshots directory.
    """
    snap_dir = Path(snapshots_dir) if snapshots_dir else SNAPSHOTS_DIR
    mgr = GutenbergSnapshotManager(
        snap_dir,
        registry_path=_REGISTRY_DEFAULT,
        repo_root=REPO_ROOT,
        corpus_root=CORPUS_ROOT,
    )
    snap = mgr.load_snapshot(key)
    if snap is None:
        msg = "No snapshots found." if key == "latest" else f"Snapshot not found: {key!r}"
        raise click.ClickException(msg)

    m = snap.metrics
    click.echo(f"Key:       {snap.key}")
    click.echo(f"Timestamp: {snap.timestamp}")
    click.echo(f"Version:   {snap.version}")
    click.echo(f"Branch:    {snap.branch}")
    click.echo("")
    click.echo("Metrics:")
    click.echo(f"  Books:   {m.get('total_books', 0):,}")
    click.echo(f"  Authors: {m.get('total_authors', 0):,}")
    click.echo(f"  Nodes:   {m.get('total_nodes', 0):,}")
    click.echo(f"  Edges:   {m.get('total_edges', 0):,}")

    genres = m.get("genres", [])
    if genres:
        click.echo("")
        click.echo(f"  {'Genre':<40} {'Books':>6} {'Nodes':>10} {'Edges':>12}")
        click.echo("  " + "-" * 72)
        for g in genres:
            if g.get("books", 0) > 0:
                click.echo(
                    f"  {g.get('label', g.get('corpus', '')):<40} "
                    f"{g.get('books', 0):>6} "
                    f"{g.get('nodes', 0):>10,} "
                    f"{g.get('edges', 0):>12,}"
                )

    if snap.vs_previous:
        d = snap.vs_previous
        click.echo("")
        click.echo("Delta vs. Previous:")
        click.echo(f"  Books:  {_fmt_delta(d.get('books', 0))}")
        click.echo(f"  Nodes:  {_fmt_delta(d.get('nodes', 0))}")
        click.echo(f"  Edges:  {_fmt_delta(d.get('edges', 0))}")

    if snap.vs_baseline:
        d = snap.vs_baseline
        click.echo("")
        click.echo("Delta vs. Baseline:")
        click.echo(f"  Books:  {_fmt_delta(d.get('books', 0))}")
        click.echo(f"  Nodes:  {_fmt_delta(d.get('nodes', 0))}")
        click.echo(f"  Edges:  {_fmt_delta(d.get('edges', 0))}")


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


@snapshot.command("diff")
@click.argument("key_a", metavar="KEY_A", default=None, required=False)
@click.argument("key_b", metavar="KEY_B", default=None, required=False)
@click.option(
    "--snapshots-dir",
    default=None,
    metavar="PATH",
    help="Override the snapshots directory.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output as JSON.",
)
def snapshot_diff(
    key_a: str | None,
    key_b: str | None,
    snapshots_dir: str | None,
    output_json: bool,
) -> None:
    """Compare two snapshots side-by-side (default: second-to-last vs last).

    :param key_a: First snapshot key (tree hash); omit to use second-to-last.
    :param key_b: Second snapshot key (tree hash); omit to use last.
    :param snapshots_dir: Override the snapshots directory.
    :param output_json: Emit raw JSON diff instead of a table.
    """
    snap_dir = Path(snapshots_dir) if snapshots_dir else SNAPSHOTS_DIR
    mgr = GutenbergSnapshotManager(
        snap_dir,
        registry_path=_REGISTRY_DEFAULT,
        repo_root=REPO_ROOT,
        corpus_root=CORPUS_ROOT,
    )

    if key_a is None or key_b is None:
        try:
            key_a, key_b = _resolve_two_keys(mgr)
        except click.ClickException:
            raise

    result = mgr.diff_snapshots(key_a, key_b)
    if "error" in result:
        raise click.ClickException(result["error"])

    if output_json:
        click.echo(json.dumps(result, indent=2))
        return

    sa, sb = result["a"], result["b"]
    click.echo(f"  A: {sa['key'][:12]}  {sa.get('timestamp', '')[:16]}")
    click.echo(f"  B: {sb['key'][:12]}  {sb.get('timestamp', '')[:16]}")
    click.echo("")

    def _line(label: str, key: str) -> None:
        ma = sa.get("metrics", {}).get(key, 0)
        mb = sb.get("metrics", {}).get(key, 0)
        click.echo(f"  {label:<10} {ma:>10,}  →  {mb:>10,}  ({_fmt_delta(mb - ma)})")

    click.echo(f"  {'Metric':<10} {'A':>10}     {'B':>10}    Delta")
    click.echo("  " + "-" * 52)
    _line("Books:", "total_books")
    _line("Authors:", "total_authors")
    _line("Nodes:", "total_nodes")
    _line("Edges:", "total_edges")

    # Per-genre breakdown from the snapshots themselves
    snap_a = mgr.load_snapshot(key_a)
    snap_b = mgr.load_snapshot(key_b)
    if snap_a and snap_b:
        ga_map = {g["corpus"]: g for g in snap_a.metrics.get("genres", [])}
        gb_map = {g["corpus"]: g for g in snap_b.metrics.get("genres", [])}
        changed = [
            (k, ga_map.get(k, {}), gb_map.get(k, {}))
            for k in sorted(set(ga_map) | set(gb_map))
            if ga_map.get(k, {}).get("books", 0) != gb_map.get(k, {}).get("books", 0)
            or ga_map.get(k, {}).get("nodes", 0) != gb_map.get(k, {}).get("nodes", 0)
        ]
        if changed:
            click.echo("")
            click.echo("  Changed genres:")
            for corpus_key, ga, gb in changed:
                label = gb.get("label", ga.get("label", corpus_key.replace("gutenberg-", "")))
                dn = gb.get("nodes", 0) - ga.get("nodes", 0)
                click.echo(
                    f"    {label:<36}  "
                    f"books {ga.get('books', 0)}→{gb.get('books', 0)}  "
                    f"nodes {ga.get('nodes', 0):,}→{gb.get('nodes', 0):,} ({_fmt_delta(dn)})"
                )


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------


@snapshot.command("prune")
@click.option(
    "--snapshots-dir",
    default=None,
    metavar="PATH",
    help="Override the snapshots directory.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be removed without deleting anything.",
)
def snapshot_prune(snapshots_dir: str | None, dry_run: bool) -> None:
    """Remove vestigial snapshots that carry no new metric information.

    Cleans up three categories:

    \b
    1. Metric-duplicates — interior snapshots with unchanged metrics.
    2. Broken entries    — manifest entries whose JSON file is missing.
    3. Orphaned files    — JSON files on disk not referenced by the manifest.

    The oldest (baseline) and newest (latest) snapshots are always kept.

    :param snapshots_dir: Override the snapshots directory.
    :param dry_run: Report what would be removed without deleting.
    """
    snap_dir = Path(snapshots_dir) if snapshots_dir else SNAPSHOTS_DIR
    mgr = GutenbergSnapshotManager(
        snap_dir,
        registry_path=_REGISTRY_DEFAULT,
        repo_root=REPO_ROOT,
        corpus_root=CORPUS_ROOT,
    )
    result = mgr.prune_snapshots(dry_run=dry_run)

    prefix = "[dry-run] " if dry_run else ""
    if result.total_cleaned == 0:
        click.echo("Nothing to prune.")
        return

    if result.removed:
        click.echo(f"{prefix}Metric-duplicates removed: {len(result.removed)}")
        for key in result.removed:
            click.echo(f"  - {key[:14]}")
    if result.broken_entries:
        click.echo(f"{prefix}Broken manifest entries removed: {len(result.broken_entries)}")
        for key in result.broken_entries:
            click.echo(f"  - {key[:14]}")
    if result.orphaned_files:
        click.echo(f"{prefix}Orphaned JSON files removed: {len(result.orphaned_files)}")
        for fname in result.orphaned_files:
            click.echo(f"  - {fname}")

    action = "would be" if dry_run else "were"
    click.echo(f"\nTotal: {result.total_cleaned} item(s) {action} cleaned.")
