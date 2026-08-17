"""Tests for the corpus growth timeline and the snapshot reader behind it.

``gutenkg viz-timeline`` was silently empty for months.  ``snapshot_list``
globbed ``snapshot-*.json`` — the filename the retired ``snapshot_save`` wrote —
while ``gutenkg snapshot save`` had moved to ``GutenbergSnapshotManager``, which
writes ``<tree-hash>.json`` plus a ``manifest.json``.  Nothing raised: the glob
matched nothing, the loader returned ``{}``, and the command reported no
snapshots while four sat on disk.

Nothing covered either function, which is why a severed pipeline could sit there
looking healthy.  These tests pin the format actually written, so the next time
the writer moves the reader fails loudly instead of quietly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gutenberg_kg.corpus import snapshot_list

# ---------------------------------------------------------------------------
# Fixtures — the shape GutenbergSnapshotManager writes
# ---------------------------------------------------------------------------


def _record(key: str, timestamp: str, *, books: int, authors: int, nodes: int, edges: int) -> dict:
    """Build one snapshot record in the manager's format."""
    return {
        "key": key,
        "branch": "main",
        "timestamp": timestamp,
        "version": "1.14.0",
        "metrics": {
            "total_books": books,
            "total_authors": authors,
            "total_nodes": nodes,
            "total_edges": edges,
            "genres": [],
        },
    }


@pytest.fixture
def snapshots_dir(tmp_path: Path) -> Path:
    """A snapshots directory with a manifest and two out-of-order snapshots."""
    d = tmp_path / ".snapshots"
    d.mkdir()
    newer = _record(
        "bbb2222", "2026-07-11T02:37:37+00:00", books=241, authors=153, nodes=9, edges=8
    )
    older = _record(
        "aaa1111", "2026-05-17T01:47:54+00:00", books=203, authors=103, nodes=5, edges=4
    )
    # Manifest deliberately lists newest first, so ordering cannot come for free.
    (d / "manifest.json").write_text(json.dumps({"format": "1.0", "snapshots": [newer, older]}))
    for rec in (newer, older):
        (d / f"{rec['key']}.json").write_text(json.dumps(rec))
    return d


class TestSnapshotList:
    def test_reads_the_manifest(self, snapshots_dir):
        assert len(snapshot_list(snapshots_dir)) == 2

    def test_returns_oldest_first(self, snapshots_dir):
        keys = [s["key"] for s in snapshot_list(snapshots_dir)]
        assert keys == ["aaa1111", "bbb2222"], "manifest order is not chronological order"

    def test_falls_back_to_the_files_without_a_manifest(self, snapshots_dir):
        (snapshots_dir / "manifest.json").unlink()
        assert len(snapshot_list(snapshots_dir)) == 2

    def test_falls_back_when_the_manifest_is_corrupt(self, snapshots_dir):
        (snapshots_dir / "manifest.json").write_text("{ not json")
        assert len(snapshot_list(snapshots_dir)) == 2

    def test_the_manifest_is_not_itself_a_snapshot(self, snapshots_dir):
        """The glob fallback must not read manifest.json back in as a record."""
        (snapshots_dir / "manifest.json").write_text("{}")
        assert all("key" in s for s in snapshot_list(snapshots_dir))

    def test_a_missing_directory_is_empty_not_an_error(self, tmp_path):
        assert snapshot_list(tmp_path / "nope") == []

    def test_an_empty_directory_is_empty(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert snapshot_list(d) == []

    def test_an_unreadable_snapshot_is_skipped_not_fatal(self, snapshots_dir):
        (snapshots_dir / "manifest.json").unlink()
        (snapshots_dir / "aaa1111.json").write_text("{ truncated")
        assert len(snapshot_list(snapshots_dir)) == 1


class TestTimelineLoading:
    """The regression: manager-format snapshots must produce a timeline."""

    @pytest.fixture(autouse=True)
    def _needs_plotly(self):
        pytest.importorskip("plotly", reason="viz extra not installed")

    def test_manager_format_is_not_empty(self, snapshots_dir):
        from gutenberg_kg.viz_timeline import load_snapshots_timeline

        assert load_snapshots_timeline(snapshots_dir), "the bug this file exists for"

    def test_metrics_are_read_from_the_metrics_dict(self, snapshots_dir):
        from gutenberg_kg.viz_timeline import load_snapshots_timeline

        t = load_snapshots_timeline(snapshots_dir)
        assert t["books"] == [203, 241]
        assert t["authors"] == [103, 153]
        assert t["nodes"] == [5, 9]
        assert t["edges"] == [4, 8]

    def test_zeroes_would_mean_the_field_names_drifted(self, snapshots_dir):
        """`total_books` vs `books` reads as 0, not as an error — so assert it."""
        from gutenberg_kg.viz_timeline import load_snapshots_timeline

        t = load_snapshots_timeline(snapshots_dir)
        assert all(v > 0 for v in t["books"] + t["authors"] + t["nodes"] + t["edges"])

    def test_the_tree_hash_stands_in_for_a_commit(self, snapshots_dir):
        from gutenberg_kg.viz_timeline import load_snapshots_timeline

        assert load_snapshots_timeline(snapshots_dir)["commits"] == ["aaa1111", "bbb2222"]

    def test_no_snapshots_yields_an_empty_dict(self, tmp_path):
        from gutenberg_kg.viz_timeline import load_snapshots_timeline

        assert load_snapshots_timeline(tmp_path / "nope") == {}

    def test_the_charts_build_from_it(self, snapshots_dir):
        """A timeline that loads but cannot be drawn is no better than empty."""
        from gutenberg_kg.viz_timeline import create_3d_timeline_figure, create_timeline_figure

        assert create_timeline_figure(snapshots_dir) is not None
        assert create_3d_timeline_figure(snapshots_dir) is not None

    def test_the_summary_reports_real_numbers(self, snapshots_dir):
        from gutenberg_kg.viz_timeline import display_timeline_summary

        assert "241" in display_timeline_summary(snapshots_dir)
