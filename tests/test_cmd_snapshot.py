"""Tests for gutenberg_kg.cli.cmd_snapshot — pure helpers and CLI."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("kg_rag", reason="kg_rag not installed — integration test skipped")

from click.testing import CliRunner

from gutenberg_kg.cli.cmd_snapshot import (
    _list_snapshots,
    _load_snapshot,
    _snapshot_filename,
)
from gutenberg_kg.cli.main import cli

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_registry(tmp_path: Path) -> Path:
    """Minimal KGRAG registry with one live book in english-literature."""
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


@pytest.fixture()
def snap_dir(tmp_path: Path) -> Path:
    d = tmp_path / ".snapshots"
    d.mkdir()
    return d


def _write_snapshot(
    directory: Path, timestamp: str, books: int = 10, version: str = "1.0.0"
) -> Path:
    """Write a minimal snapshot JSON file and return its path."""
    safe = timestamp.replace(":", "-").replace("+", "").split(".")[0]
    snap = {
        "kind": "corpus_snapshot",
        "schema_version": 1,
        "timestamp": timestamp,
        "version": version,
        "branch": "develop",
        "commit": "abc1234",
        "commit_full": "abc1234abc1234abc1234",
        "totals": {
            "books": books,
            "authors": 5,
            "nodes": books * 100,
            "edges": books * 200,
        },
        "genres": [],
    }
    path = directory / f"snapshot-{safe}.json"
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _snapshot_filename
# ---------------------------------------------------------------------------


def test_snapshot_filename_starts_with_prefix():
    assert _snapshot_filename("2026-05-06T14:30:00+00:00").startswith("snapshot-")


def test_snapshot_filename_ends_with_json():
    assert _snapshot_filename("2026-05-06T14:30:00+00:00").endswith(".json")


def test_snapshot_filename_no_colons():
    assert ":" not in _snapshot_filename("2026-05-06T14:30:00+00:00")


def test_snapshot_filename_no_plus():
    assert "+" not in _snapshot_filename("2026-05-06T14:30:00+00:00")


def test_snapshot_filename_no_fractional_seconds():
    name = _snapshot_filename("2026-05-06T12:00:00.123456+00:00")
    assert ".123456" not in name


def test_snapshot_filename_deterministic():
    ts = "2026-05-06T10:00:00+00:00"
    assert _snapshot_filename(ts) == _snapshot_filename(ts)


# ---------------------------------------------------------------------------
# _load_snapshot
# ---------------------------------------------------------------------------


def test_load_snapshot_returns_dict(tmp_path: Path):
    snap = {"kind": "corpus_snapshot", "totals": {"books": 5}}
    f = tmp_path / "snap.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    assert _load_snapshot(f) == snap


def test_load_snapshot_preserves_nested_keys(tmp_path: Path):
    snap = {
        "kind": "corpus_snapshot",
        "timestamp": "2026-05-06T00:00:00+00:00",
        "version": "1.2.3",
        "totals": {"books": 100, "nodes": 5000, "edges": 10000},
        "genres": [{"corpus": "gutenberg-shakespeare", "books": 37}],
    }
    f = tmp_path / "snap.json"
    f.write_text(json.dumps(snap), encoding="utf-8")
    assert _load_snapshot(f) == snap


# ---------------------------------------------------------------------------
# _list_snapshots
# ---------------------------------------------------------------------------


def test_list_snapshots_no_dir(monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", Path("/tmp/definitely_no_snapshots_xyz_abc"))
    assert _list_snapshots() == []


def test_list_snapshots_empty_dir(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    assert _list_snapshots() == []


def test_list_snapshots_returns_two(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00")
    _write_snapshot(snap_dir, "2026-05-06T00:00:00+00:00")
    assert len(_list_snapshots()) == 2


def test_list_snapshots_sorted_ascending(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-06T00:00:00+00:00")
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00")
    paths = _list_snapshots()
    assert paths[0].name < paths[1].name


def test_list_snapshots_ignores_non_matching(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00")
    (snap_dir / "other.json").write_text("{}")
    (snap_dir / "unrelated.txt").write_text("x")
    assert len(_list_snapshots()) == 1


# ---------------------------------------------------------------------------
# CLI: snapshot group and subcommand help
# ---------------------------------------------------------------------------


def test_snapshot_group_help_exit_zero():
    result = CliRunner().invoke(cli, ["snapshot", "--help"])
    assert result.exit_code == 0


def test_snapshot_group_shows_subcommands():
    result = CliRunner().invoke(cli, ["snapshot", "--help"])
    for sub in ("save", "list", "show", "diff"):
        assert sub in result.output, f"expected subcommand {sub!r} in snapshot --help"


def test_snapshot_save_help():
    result = CliRunner().invoke(cli, ["snapshot", "save", "--help"])
    assert result.exit_code == 0
    for flag in ("--registry", "--output", "--print"):
        assert flag in result.output


def test_snapshot_list_help():
    result = CliRunner().invoke(cli, ["snapshot", "list", "--help"])
    assert result.exit_code == 0


def test_snapshot_show_help():
    result = CliRunner().invoke(cli, ["snapshot", "show", "--help"])
    assert result.exit_code == 0


def test_snapshot_diff_help():
    result = CliRunner().invoke(cli, ["snapshot", "diff", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# CLI: snapshot list
# ---------------------------------------------------------------------------


def test_snapshot_list_no_snapshots_message(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    result = CliRunner().invoke(cli, ["snapshot", "list"])
    assert result.exit_code == 0
    assert "No snapshots" in result.output


def test_snapshot_list_shows_timestamp(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00", books=42)
    result = CliRunner().invoke(cli, ["snapshot", "list"])
    assert result.exit_code == 0
    assert "2026-05-01" in result.output


def test_snapshot_list_shows_book_count(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00", books=42)
    result = CliRunner().invoke(cli, ["snapshot", "list"])
    assert "42" in result.output


def test_snapshot_list_shows_multiple(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00")
    _write_snapshot(snap_dir, "2026-05-06T00:00:00+00:00")
    result = CliRunner().invoke(cli, ["snapshot", "list"])
    assert result.output.count("2026-05-") == 2


# ---------------------------------------------------------------------------
# CLI: snapshot show
# ---------------------------------------------------------------------------


def test_snapshot_show_no_snapshots_error(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    result = CliRunner().invoke(cli, ["snapshot", "show"])
    assert result.exit_code != 0
    assert "No snapshots" in result.output


def test_snapshot_show_no_match_error(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00")
    result = CliRunner().invoke(cli, ["snapshot", "show", "nonexistent"])
    assert result.exit_code != 0
    assert "No snapshot matching" in result.output


def test_snapshot_show_default_is_most_recent(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00", version="1.0.0")
    _write_snapshot(snap_dir, "2026-05-06T00:00:00+00:00", version="1.1.0")
    result = CliRunner().invoke(cli, ["snapshot", "show"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["version"] == "1.1.0"


def test_snapshot_show_by_prefix(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00", version="1.0.0")
    _write_snapshot(snap_dir, "2026-05-06T00:00:00+00:00", version="1.1.0")
    result = CliRunner().invoke(cli, ["snapshot", "show", "2026-05-01"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["version"] == "1.0.0"


def test_snapshot_show_output_is_valid_json(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00")
    result = CliRunner().invoke(cli, ["snapshot", "show"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["kind"] == "corpus_snapshot"


# ---------------------------------------------------------------------------
# CLI: snapshot diff
# ---------------------------------------------------------------------------


def test_snapshot_diff_too_few_error(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00")
    result = CliRunner().invoke(cli, ["snapshot", "diff"])
    assert result.exit_code != 0
    assert "two snapshots" in result.output.lower()


def test_snapshot_diff_shows_book_delta(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00", books=10)
    _write_snapshot(snap_dir, "2026-05-06T00:00:00+00:00", books=20)
    result = CliRunner().invoke(cli, ["snapshot", "diff"])
    assert result.exit_code == 0
    assert "Books:" in result.output
    assert "+10" in result.output


def test_snapshot_diff_default_is_last_two(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00")
    _write_snapshot(snap_dir, "2026-05-06T00:00:00+00:00")
    result = CliRunner().invoke(cli, ["snapshot", "diff"])
    assert result.exit_code == 0
    # Both timestamps in header lines
    assert "2026-05-01" in result.output
    assert "2026-05-06" in result.output


def test_snapshot_diff_named_args(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00", books=5)
    _write_snapshot(snap_dir, "2026-05-06T00:00:00+00:00", books=15)
    result = CliRunner().invoke(cli, ["snapshot", "diff", "2026-05-01", "2026-05-06"])
    assert result.exit_code == 0
    assert "+10" in result.output


def test_snapshot_diff_shows_node_and_edge_lines(snap_dir: Path, monkeypatch):
    import gutenberg_kg.cli.cmd_snapshot as mod

    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    _write_snapshot(snap_dir, "2026-05-01T00:00:00+00:00", books=10)
    _write_snapshot(snap_dir, "2026-05-06T00:00:00+00:00", books=20)
    result = CliRunner().invoke(cli, ["snapshot", "diff"])
    assert "Nodes:" in result.output
    assert "Edges:" in result.output


# ---------------------------------------------------------------------------
# CLI: snapshot save
# ---------------------------------------------------------------------------


def test_snapshot_save_missing_registry(tmp_path: Path):
    result = CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(tmp_path / "no_registry.sqlite"),
            "--output",
            str(tmp_path / "out.json"),
        ],
    )
    assert result.exit_code != 0
    assert "Registry not found" in result.output


def test_snapshot_save_writes_file(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_snapshot as mod
    import gutenberg_kg.cli.cmd_status as status_mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    monkeypatch.setattr(status_mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    out = tmp_path / "snap.json"

    result = CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()


def test_snapshot_save_output_is_valid_snapshot(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_snapshot as mod
    import gutenberg_kg.cli.cmd_status as status_mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    monkeypatch.setattr(status_mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    out = tmp_path / "snap.json"

    CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--output",
            str(out),
        ],
    )
    data = json.loads(out.read_text())
    assert data["kind"] == "corpus_snapshot"
    assert data["schema_version"] == 1
    assert "totals" in data
    assert "genres" in data


def test_snapshot_save_correct_book_count(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_snapshot as mod
    import gutenberg_kg.cli.cmd_status as status_mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    monkeypatch.setattr(status_mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    out = tmp_path / "snap.json"

    CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--output",
            str(out),
        ],
    )
    data = json.loads(out.read_text())
    assert data["totals"]["books"] == 1


def test_snapshot_save_print_flag_emits_json(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_snapshot as mod
    import gutenberg_kg.cli.cmd_status as status_mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    monkeypatch.setattr(status_mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    out = tmp_path / "snap.json"

    result = CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--output",
            str(out),
            "--print",
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"kind"' in result.output
    assert '"corpus_snapshot"' in result.output


def test_snapshot_save_success_message(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_snapshot as mod
    import gutenberg_kg.cli.cmd_status as status_mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    monkeypatch.setattr(status_mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    out = tmp_path / "snap.json"

    result = CliRunner().invoke(
        cli,
        [
            "snapshot",
            "save",
            "--registry",
            str(fake_registry),
            "--output",
            str(out),
        ],
    )
    assert "snap.json" in result.output


# ---------------------------------------------------------------------------
# Round-trip: save → list → show → diff
# ---------------------------------------------------------------------------


def test_round_trip_save_then_list(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_snapshot as mod
    import gutenberg_kg.cli.cmd_status as status_mod

    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    monkeypatch.setattr(status_mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()

    # Save two snapshots via --output to control filenames
    out1 = snap_dir / "snapshot-2026-05-01T00-00-00.json"
    out2 = snap_dir / "snapshot-2026-05-06T00-00-00.json"

    for out in (out1, out2):
        r = CliRunner().invoke(
            cli,
            [
                "snapshot",
                "save",
                "--registry",
                str(fake_registry),
                "--output",
                str(out),
            ],
        )
        assert r.exit_code == 0, r.output

    list_result = CliRunner().invoke(cli, ["snapshot", "list"])
    assert list_result.exit_code == 0
    assert "No snapshots" not in list_result.output


def test_round_trip_save_then_diff(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_snapshot as mod
    import gutenberg_kg.cli.cmd_status as status_mod

    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    monkeypatch.setattr(mod, "SNAPSHOTS_DIR", snap_dir)
    monkeypatch.setattr(status_mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()

    out1 = snap_dir / "snapshot-2026-05-01T00-00-00.json"
    out2 = snap_dir / "snapshot-2026-05-06T00-00-00.json"
    for out in (out1, out2):
        r = CliRunner().invoke(
            cli,
            [
                "snapshot",
                "save",
                "--registry",
                str(fake_registry),
                "--output",
                str(out),
            ],
        )
        assert r.exit_code == 0, r.output

    diff_result = CliRunner().invoke(cli, ["snapshot", "diff"])
    assert diff_result.exit_code == 0
    assert "Books:" in diff_result.output
