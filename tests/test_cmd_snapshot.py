"""Tests for gutenberg_kg.cli.cmd_snapshot — GutenbergSnapshotManager + CLI."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from gutenberg_kg.cli.main import cli

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_registry(tmp_path: Path) -> Path:
    """Minimal KGRAG registry with one live book (5 nodes, 3 edges)."""
    db = tmp_path / "book1.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE edges (a INTEGER, b INTEGER)")
        con.executemany("INSERT INTO nodes VALUES (?)", [(i,) for i in range(5)])
        con.executemany("INSERT INTO edges VALUES (?,?)", [(i, i + 1) for i in range(3)])

    reg = tmp_path / "registry.sqlite"
    with sqlite3.connect(reg) as con:
        con.execute("CREATE TABLE kg_entries (id TEXT, sqlite_path TEXT)")
        con.execute("CREATE TABLE corpora (name TEXT, kg_ids TEXT)")
        con.execute("INSERT INTO kg_entries VALUES (?,?)", ("kg-1", str(db)))
        con.execute(
            "INSERT INTO corpora VALUES (?,?)",
            ("gutenberg-english-literature", json.dumps(["kg-1"])),
        )
    return reg


def _write_managed_snapshot(
    snapshots_dir: Path,
    key: str,
    timestamp: str,
    *,
    books: int = 10,
    nodes: int = 1000,
    edges: int = 2000,
    version: str = "1.0.0",
    branch: str = "develop",
) -> Path:
    """Write a snapshot in SnapshotManager format and update manifest."""
    metrics = {
        "total_nodes": nodes,
        "total_edges": edges,
        "total_books": books,
        "total_authors": 5,
        "genres": [],
    }
    snap_data = {
        "key": key,
        "branch": branch,
        "timestamp": timestamp,
        "version": version,
        "metrics": metrics,
        "hotspots": [],
        "issues": [],
        "vs_previous": None,
        "vs_baseline": None,
    }
    snap_file = snapshots_dir / f"{key}.json"
    snap_file.write_text(json.dumps(snap_data, indent=2) + "\n", encoding="utf-8")

    manifest_path = snapshots_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"format": "1.0", "last_update": "", "snapshots": []}

    manifest["snapshots"].append(
        {
            "key": key,
            "branch": branch,
            "timestamp": timestamp,
            "version": version,
            "file": snap_file.name,
            "metrics": metrics,
            "deltas": {"vs_previous": None, "vs_baseline": None},
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return snap_file


# ---------------------------------------------------------------------------
# CLI: snapshot group / subcommand help
# ---------------------------------------------------------------------------


def test_snapshot_group_help_exit_zero():
    result = CliRunner().invoke(cli, ["snapshot", "--help"])
    assert result.exit_code == 0


def test_snapshot_group_shows_all_subcommands():
    result = CliRunner().invoke(cli, ["snapshot", "--help"])
    for sub in ("save", "list", "show", "diff", "prune"):
        assert sub in result.output, f"expected subcommand {sub!r} in snapshot --help"


def test_snapshot_save_help():
    result = CliRunner().invoke(cli, ["snapshot", "save", "--help"])
    assert result.exit_code == 0
    for flag in ("--registry", "--snapshots-dir", "--force", "--json"):
        assert flag in result.output


def test_snapshot_list_help():
    result = CliRunner().invoke(cli, ["snapshot", "list", "--help"])
    assert result.exit_code == 0
    for flag in ("--snapshots-dir", "--limit", "--branch", "--json"):
        assert flag in result.output


def test_snapshot_show_help():
    result = CliRunner().invoke(cli, ["snapshot", "show", "--help"])
    assert result.exit_code == 0


def test_snapshot_diff_help():
    result = CliRunner().invoke(cli, ["snapshot", "diff", "--help"])
    assert result.exit_code == 0


def test_snapshot_prune_help():
    result = CliRunner().invoke(cli, ["snapshot", "prune", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


# ---------------------------------------------------------------------------
# CLI: snapshot list
# ---------------------------------------------------------------------------


def test_snapshot_list_no_snapshots_message(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    result = CliRunner().invoke(cli, ["snapshot", "list", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code == 0
    assert "No snapshots" in result.output


def test_snapshot_list_shows_timestamp(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=42)
    result = CliRunner().invoke(cli, ["snapshot", "list", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code == 0
    assert "2026-05-01" in result.output


def test_snapshot_list_shows_book_count(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=42)
    result = CliRunner().invoke(cli, ["snapshot", "list", "--snapshots-dir", str(snap_dir)])
    assert "42" in result.output


def test_snapshot_list_shows_multiple(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00")
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00")
    result = CliRunner().invoke(cli, ["snapshot", "list", "--snapshots-dir", str(snap_dir)])
    assert result.output.count("2026-05-") == 2


def test_snapshot_list_reverse_chronological(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00")
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00")
    result = CliRunner().invoke(cli, ["snapshot", "list", "--snapshots-dir", str(snap_dir)])
    idx1 = result.output.index("2026-05-06")
    idx2 = result.output.index("2026-05-01")
    assert idx1 < idx2, "newest snapshot should appear first"


def test_snapshot_list_limit(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    for i, ts in enumerate(
        ["2026-05-01T00:00:00+00:00", "2026-05-02T00:00:00+00:00", "2026-05-03T00:00:00+00:00"]
    ):
        _write_managed_snapshot(snap_dir, f"abc{i:03d}", ts)
    result = CliRunner().invoke(
        cli, ["snapshot", "list", "--snapshots-dir", str(snap_dir), "--limit", "2"]
    )
    assert result.output.count("2026-05-") == 2


def test_snapshot_list_json_output(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=7)
    result = CliRunner().invoke(
        cli, ["snapshot", "list", "--snapshots-dir", str(snap_dir), "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["metrics"]["total_books"] == 7


# ---------------------------------------------------------------------------
# CLI: snapshot show
# ---------------------------------------------------------------------------


def test_snapshot_show_no_snapshots_error(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    result = CliRunner().invoke(cli, ["snapshot", "show", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code != 0
    assert "No snapshots" in result.output


def test_snapshot_show_not_found_error(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00")
    result = CliRunner().invoke(
        cli, ["snapshot", "show", "deadbeef", "--snapshots-dir", str(snap_dir)]
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_snapshot_show_latest_default(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", version="1.0.0")
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00", version="1.1.0")
    result = CliRunner().invoke(cli, ["snapshot", "show", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code == 0
    assert "1.1.0" in result.output


def test_snapshot_show_by_key(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", version="1.0.0")
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00", version="1.1.0")
    result = CliRunner().invoke(
        cli, ["snapshot", "show", "abc001", "--snapshots-dir", str(snap_dir)]
    )
    assert result.exit_code == 0
    assert "1.0.0" in result.output


def test_snapshot_show_displays_metrics(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=99)
    result = CliRunner().invoke(cli, ["snapshot", "show", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code == 0
    assert "99" in result.output
    assert "Books:" in result.output
    assert "Nodes:" in result.output
    assert "Edges:" in result.output


# ---------------------------------------------------------------------------
# CLI: snapshot diff
# ---------------------------------------------------------------------------


def test_snapshot_diff_too_few_error(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00")
    result = CliRunner().invoke(cli, ["snapshot", "diff", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code != 0
    assert "two snapshots" in result.output.lower()


def test_snapshot_diff_default_is_last_two(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00")
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00")
    result = CliRunner().invoke(cli, ["snapshot", "diff", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code == 0
    assert "abc001" in result.output
    assert "abc002" in result.output


def test_snapshot_diff_shows_book_and_node_lines(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=10, nodes=100)
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00", books=20, nodes=200)
    result = CliRunner().invoke(cli, ["snapshot", "diff", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code == 0
    assert "Books:" in result.output
    assert "Nodes:" in result.output
    assert "Edges:" in result.output


def test_snapshot_diff_shows_positive_delta(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=10)
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00", books=20)
    result = CliRunner().invoke(cli, ["snapshot", "diff", "--snapshots-dir", str(snap_dir)])
    assert "+10" in result.output


def test_snapshot_diff_explicit_keys(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=5)
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00", books=15)
    result = CliRunner().invoke(
        cli, ["snapshot", "diff", "abc001", "abc002", "--snapshots-dir", str(snap_dir)]
    )
    assert result.exit_code == 0
    assert "+10" in result.output


def test_snapshot_diff_json_output(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=10)
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00", books=20)
    result = CliRunner().invoke(
        cli, ["snapshot", "diff", "--snapshots-dir", str(snap_dir), "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "a" in data and "b" in data and "delta" in data


# ---------------------------------------------------------------------------
# CLI: snapshot prune
# ---------------------------------------------------------------------------


def test_snapshot_prune_nothing_to_prune(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=10)
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00", books=20)
    result = CliRunner().invoke(cli, ["snapshot", "prune", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code == 0
    assert "Nothing to prune" in result.output


def test_snapshot_prune_removes_metric_duplicate(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    # Three snapshots with identical metrics — the interior one is pruned.
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=10)
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00", books=10)
    _write_managed_snapshot(snap_dir, "abc003", "2026-05-07T00:00:00+00:00", books=10)
    result = CliRunner().invoke(cli, ["snapshot", "prune", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code == 0
    assert "1 item" in result.output


def test_snapshot_prune_dry_run_does_not_delete(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=10)
    _write_managed_snapshot(snap_dir, "abc002", "2026-05-06T00:00:00+00:00", books=10)
    _write_managed_snapshot(snap_dir, "abc003", "2026-05-07T00:00:00+00:00", books=10)
    result = CliRunner().invoke(
        cli, ["snapshot", "prune", "--snapshots-dir", str(snap_dir), "--dry-run"]
    )
    assert result.exit_code == 0
    assert "[dry-run]" in result.output
    # File should still exist
    assert (snap_dir / "abc002.json").exists()


def test_snapshot_prune_removes_orphaned_file(tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    _write_managed_snapshot(snap_dir, "abc001", "2026-05-01T00:00:00+00:00", books=10)
    # Orphaned file not in manifest
    (snap_dir / "orphan.json").write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(cli, ["snapshot", "prune", "--snapshots-dir", str(snap_dir)])
    assert result.exit_code == 0
    assert not (snap_dir / "orphan.json").exists()


# ---------------------------------------------------------------------------
# CLI: snapshot save (requires fake_registry)
# ---------------------------------------------------------------------------


def test_snapshot_save_missing_registry(tmp_path: Path):
    result = CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(tmp_path / "no_registry.sqlite"),
            "--snapshots-dir",
            str(tmp_path / ".snapshots"),
        ],
    )
    assert result.exit_code != 0
    assert "Registry not found" in result.output


def test_snapshot_save_writes_snapshot_file(fake_registry: Path, tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    (tmp_path / "authors").mkdir()
    result = CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--snapshots-dir",
            str(snap_dir),
            "--corpus-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert snap_dir.exists()
    jsons = list(snap_dir.glob("*.json"))
    # At least the snapshot file (and manifest)
    assert any(f.name != "manifest.json" for f in jsons)


def test_snapshot_save_creates_manifest(fake_registry: Path, tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    (tmp_path / "authors").mkdir()
    CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--snapshots-dir",
            str(snap_dir),
            "--corpus-root",
            str(tmp_path),
        ],
    )
    assert (snap_dir / "manifest.json").exists()


def test_snapshot_save_snapshot_has_correct_book_count(fake_registry: Path, tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    (tmp_path / "authors").mkdir()
    CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--snapshots-dir",
            str(snap_dir),
            "--corpus-root",
            str(tmp_path),
        ],
    )
    snaps = [f for f in snap_dir.glob("*.json") if f.name != "manifest.json"]
    data = json.loads(snaps[0].read_text(encoding="utf-8"))
    assert data["metrics"]["total_books"] == 1


def test_snapshot_save_success_message(fake_registry: Path, tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    (tmp_path / "authors").mkdir()
    result = CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--snapshots-dir",
            str(snap_dir),
            "--corpus-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "[✓]" in result.output or "Snapshot saved" in result.output


def test_snapshot_save_json_flag(fake_registry: Path, tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    (tmp_path / "authors").mkdir()
    result = CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--snapshots-dir",
            str(snap_dir),
            "--corpus-root",
            str(tmp_path),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"key"' in result.output


# ---------------------------------------------------------------------------
# Round-trip: save → list → show → diff
# ---------------------------------------------------------------------------


def test_round_trip_save_list(fake_registry: Path, tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    (tmp_path / "authors").mkdir()

    for _ in range(2):
        r = CliRunner().invoke(
            cli,
            [
                "snapshot",
                "save",
                "--registry",
                str(fake_registry),
                "--snapshots-dir",
                str(snap_dir),
                "--corpus-root",
                str(tmp_path),
                "--force",
            ],
        )
        assert r.exit_code == 0, r.output

    list_result = CliRunner().invoke(cli, ["snapshot", "list", "--snapshots-dir", str(snap_dir)])
    assert list_result.exit_code == 0
    assert "No snapshots" not in list_result.output


def test_round_trip_save_show(fake_registry: Path, tmp_path: Path):
    snap_dir = tmp_path / ".snapshots"
    (tmp_path / "authors").mkdir()

    CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--snapshots-dir",
            str(snap_dir),
            "--corpus-root",
            str(tmp_path),
        ],
    )
    show_result = CliRunner().invoke(cli, ["snapshot", "show", "--snapshots-dir", str(snap_dir)])
    assert show_result.exit_code == 0
    assert "Books:" in show_result.output
