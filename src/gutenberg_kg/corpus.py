"""corpus.py — Library API for GutenbergKG corpus-level operations.

Provides path-parametrised functions for building corpus status reports and
snapshot dicts.  All functions accept explicit path arguments so they can be
called from any context — CLI, tests, or kgrag adapters — without depending
on package-level path constants.

Author: Eric G. Suchanek, PhD
License: Elastic 2.0
"""

from __future__ import annotations

import importlib.metadata
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kg_utils.snapshots import SnapshotManager as _BaseSnapshotManager

from gutenberg_kg import genres as _gr

# Slugs whose display labels can't be derived by simple hyphen→space+title-case.
_LABEL_OVERRIDES: dict[str, str] = {
    "ancient-classical": "Ancient & Classical",
    "spanish": "Spanish Literature",
    "audel-electric": "Technical Reference (IA)",
}


def _slug_to_label(slug: str) -> str:
    """Return the display label for a genre slug.

    :param slug: Genre slug (e.g. ``"ancient-classical"``).
    :return: Label from ``_LABEL_OVERRIDES``, else title-cased with hyphens as spaces.
    """
    return _LABEL_OVERRIDES.get(slug, slug.replace("-", " ").title())


# Built dynamically from corpus/genres.json via genres._load() — no hardcoding.
GENRE_LABELS: dict[str, str] = {
    f"gutenberg-{slug}": _slug_to_label(slug) for slug in _gr.ALL_GENRES
}
# Diaries are a recognised genre (valid for `download`, present in genres.json)
# but ingest/rebuild route them to the DiaryKG pipeline rather than the standard
# DocKG path, and build_corpus treats "diaries" as a NON_GENRE_DIR.
GENRE_LABELS.setdefault("gutenberg-diaries", "Diaries")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sqlite_counts(path: str | None) -> tuple[int, int]:
    """Return (nodes, edges) from a graph.sqlite, or (0, 0) on any error."""
    if not path:
        return 0, 0
    try:
        with sqlite3.connect(path) as con:
            nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return nodes, edges
    except Exception:  # noqa: BLE001
        return 0, 0


def _count_authors(corpus_root: Path) -> int:
    """Count author subdirectories in ``<corpus_root>/authors/``."""
    authors_dir = corpus_root / "authors"
    if not authors_dir.is_dir():
        return 0
    return sum(1 for p in authors_dir.iterdir() if p.is_dir())


def _git_info(repo_root: Path) -> dict[str, str]:
    """Return branch, short commit, and full commit from git."""

    def _run(*args: str) -> str:
        """Run a git command in *repo_root* and return its stripped stdout, or "unknown" on failure.

        :param args: Command and arguments (e.g. ``"git", "rev-parse", "HEAD"``).
        :return: Stripped stdout, or ``"unknown"`` if the command fails.
        """
        try:
            return subprocess.check_output(
                list(args), cwd=repo_root, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:  # noqa: BLE001
            return "unknown"

    return {
        "branch": _run("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _run("git", "rev-parse", "--short", "HEAD"),
        "commit_full": _run("git", "rev-parse", "HEAD"),
    }


# ---------------------------------------------------------------------------
# Public data functions
# ---------------------------------------------------------------------------


def collect_genre_stats(registry_path: Path) -> list[dict[str, Any]]:
    """Aggregate per-genre stats from the KGRAG registry.

    Returns a list of dicts with keys: ``corpus``, ``label``, ``books``,
    ``nodes``, ``edges``.  Only SQLite files that exist on disk are counted.

    :param registry_path: Path to the KGRAG registry SQLite file.
    :return: Per-genre stat dicts in ``GENRE_LABELS`` order.
    :raises OSError: If the registry cannot be opened.
    """
    results: list[dict[str, Any]] = []
    try:
        reg = sqlite3.connect(str(registry_path))
    except Exception as exc:  # noqa: BLE001
        raise OSError(f"Cannot open registry {registry_path}: {exc}") from exc

    kg_map: dict[str, str | None] = {}
    for row in reg.execute("SELECT id, sqlite_path FROM kg_entries"):
        kg_map[row[0]] = row[1]

    for corpus_key, label in GENRE_LABELS.items():
        row = reg.execute("SELECT kg_ids FROM corpora WHERE name = ?", (corpus_key,)).fetchone()
        if row is None:
            results.append(
                {
                    "corpus": corpus_key,
                    "label": label,
                    "books": 0,
                    "nodes": 0,
                    "edges": 0,
                }
            )
            continue

        kg_ids: list[str] = json.loads(row[0])
        total_nodes = total_edges = live_books = 0
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


def corpus_status(
    registry_path: Path,
    repo_root: Path,
    corpus_root: Path,
) -> dict[str, Any]:
    """Return a live corpus-wide status dict.

    :param registry_path: KGRAG registry SQLite path.
    :param repo_root: Root of the gutenberg_kg repository (for git info).
    :param corpus_root: Corpus data directory (contains ``authors/`` etc.).
    :return: Dict with ``kind``, ``timestamp``, ``version``, ``branch``,
        ``commit``, ``host``, ``platform``, ``totals``, and ``genres``.
    """
    import platform
    import socket

    genre_stats = collect_genre_stats(registry_path)
    git = _git_info(repo_root)

    try:
        version = importlib.metadata.version("gutenberg-kg")
    except Exception:  # noqa: BLE001
        version = "unknown"

    return {
        "kind": "corpus_status",
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": version,
        "branch": git["branch"],
        "commit": git["commit"],
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "totals": {
            "books": sum(g["books"] for g in genre_stats),
            "authors": _count_authors(corpus_root),
            "nodes": sum(g["nodes"] for g in genre_stats),
            "edges": sum(g["edges"] for g in genre_stats),
        },
        "genres": genre_stats,
    }


def snapshot_list(snapshots_dir: Path) -> list[dict[str, Any]]:
    """Load and return all snapshots, oldest first.

    Reads what :class:`GutenbergSnapshotManager` writes: a ``manifest.json``
    listing one ``<tree-hash>.json`` per snapshot.  Each record carries ``key``,
    ``branch``, ``timestamp``, ``version`` and a ``metrics`` dict.

    This used to glob ``snapshot-*.json`` — the filename the retired
    :func:`snapshot_save` produced — which silently returned nothing once
    ``gutenkg snapshot save`` moved to the manager, taking ``gutenkg
    viz-timeline`` with it.  The manifest is authoritative and already ordered;
    the glob is a fallback for a directory whose manifest is missing.

    :param snapshots_dir: Directory containing ``manifest.json`` and the
        per-snapshot files, e.g. ``corpus/.snapshots/``.
    :return: Snapshot dicts oldest first; empty if the directory is absent or
        holds nothing readable.
    """
    if not snapshots_dir.is_dir():
        return []

    manifest = snapshots_dir / "manifest.json"
    records: list[dict[str, Any]] = []
    if manifest.is_file():
        try:
            records = json.loads(manifest.read_text(encoding="utf-8")).get("snapshots", [])
        except Exception:  # noqa: BLE001
            records = []

    if not records:
        # No manifest, or an unreadable one: read the snapshot files directly.
        for p in sorted(snapshots_dir.glob("*.json")):
            if p.name == "manifest.json":
                continue
            try:
                records.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                pass

    # Oldest first, by the field the caller plots against rather than by
    # filename — the files are named for a tree hash, which does not sort.
    return sorted(records, key=lambda s: s.get("timestamp", ""))


# ---------------------------------------------------------------------------
# GutenbergSnapshotManager — manifest-based temporal snapshots
# ---------------------------------------------------------------------------


class GutenbergSnapshotManager(_BaseSnapshotManager):
    """Corpus-aware snapshot manager backed by ``kg_utils.snapshots.SnapshotManager``.

    Snapshots are keyed by git tree hash, stored as ``<key>.json`` alongside a
    ``manifest.json`` index in ``snapshots_dir``.  Use :meth:`capture` to build
    a snapshot from the live corpus, then :meth:`save_snapshot` to persist it.

    :param snapshots_dir: Directory where snapshot JSON files are stored.
    :param registry_path: KGRAG registry SQLite path.
    :param repo_root: Repository root (for git metadata).
    :param corpus_root: Corpus data root (contains ``authors/`` etc.).
    """

    def __init__(
        self,
        snapshots_dir: Path | str,
        *,
        registry_path: Path,
        repo_root: Path,
        corpus_root: Path,
    ) -> None:
        """Initialize the manager and store the paths used to capture snapshots.

        :param snapshots_dir: Directory where snapshot JSON files are stored.
        :param registry_path: KGRAG registry SQLite path.
        :param repo_root: Repository root (for git metadata).
        :param corpus_root: Corpus data root (contains ``authors/`` etc.).
        """
        super().__init__(snapshots_dir, package_name="gutenberg-kg")
        self.registry_path = registry_path
        self.repo_root = repo_root
        self.corpus_root = corpus_root

    def capture(
        self,
        version: str | None = None,
        branch: str | None = None,
        graph_stats_dict: dict[str, Any] | None = None,
        tree_hash: str = "",
        hotspots: list[dict[str, Any]] | None = None,
        issues: list[str] | None = None,
        **extra_metrics: Any,
    ) -> Any:
        """Build a corpus snapshot from the live registry.

        :param version: Version string; auto-detected from package if None.
        :param branch: Git branch name; auto-detected if None.
        :param graph_stats_dict: Ignored; corpus metrics are computed from the registry.
        :param tree_hash: Git tree hash; auto-detected if not provided.
        :param hotspots: Unused; accepted for LSP compatibility.
        :param issues: Unused; accepted for LSP compatibility.
        :param extra_metrics: Passed through to the base ``capture`` call.
        :return: New ``Snapshot`` instance (not yet persisted).
        """
        genre_stats = collect_genre_stats(self.registry_path)
        metrics: dict[str, Any] = {
            "total_nodes": sum(g["nodes"] for g in genre_stats),
            "total_edges": sum(g["edges"] for g in genre_stats),
            "total_books": sum(g["books"] for g in genre_stats),
            "total_authors": _count_authors(self.corpus_root),
            "genres": genre_stats,
        }
        return super().capture(
            version=version,
            branch=branch,
            graph_stats_dict=metrics,
            tree_hash=tree_hash,
            **extra_metrics,
        )

    def save_snapshot(self, snapshot: Any, *, force: bool = False) -> Any:  # type: ignore[override]
        """Persist snapshot, guarding against degenerate (zero-book) state.

        :param snapshot: Snapshot to persist.
        :param force: If True, always create a new history entry.
        :raises ValueError: If the snapshot has 0 books.
        """
        m = snapshot.metrics if isinstance(snapshot.metrics, dict) else {}
        if m.get("total_books", 0) == 0:
            raise ValueError(
                "Refusing to save snapshot with 0 books. "
                "Ensure the corpus has ingested books before capturing a snapshot."
            )
        return super().save_snapshot(snapshot, force=force)

    def _compute_delta_from_metrics(
        self, new_m: dict[str, Any], old_m: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute corpus delta including books and authors.

        :param new_m: Newer metrics dict.
        :param old_m: Older metrics dict.
        :return: Delta dict with nodes, edges, books, authors.
        """
        return {
            "nodes": new_m.get("total_nodes", 0) - old_m.get("total_nodes", 0),
            "edges": new_m.get("total_edges", 0) - old_m.get("total_edges", 0),
            "books": new_m.get("total_books", 0) - old_m.get("total_books", 0),
            "authors": new_m.get("total_authors", 0) - old_m.get("total_authors", 0),
        }

    def _metrics_changed(self, new_metrics: dict[str, Any], old_metrics: dict[str, Any]) -> bool:
        """Return True if any corpus metric changed.

        :param new_metrics: Newer metrics dict.
        :param old_metrics: Older metrics dict.
        """
        return (
            new_metrics.get("total_nodes", 0) != old_metrics.get("total_nodes", 0)
            or new_metrics.get("total_books", 0) != old_metrics.get("total_books", 0)
            or new_metrics.get("total_authors", 0) != old_metrics.get("total_authors", 0)
        )
