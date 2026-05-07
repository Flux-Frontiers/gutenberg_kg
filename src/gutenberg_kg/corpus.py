"""corpus.py — Library API for GutenbergKG corpus-level operations.

Provides path-parametrised functions for building corpus status reports and
snapshot dicts.  All functions accept explicit path arguments so they can be
called from any context — CLI, tests, or kgrag adapters — without depending
on package-level path constants.
"""

from __future__ import annotations

import importlib.metadata
import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Maps corpus slug → display label (order determines table row order).
GENRE_LABELS: dict[str, str] = {
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
    except Exception:  # pylint: disable=broad-exception-caught
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
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise OSError(f"Cannot open registry {registry_path}: {exc}") from exc

    kg_map: dict[str, str | None] = {}
    for row in reg.execute("SELECT id, sqlite_path FROM kg_entries"):
        kg_map[row[0]] = row[1]

    for corpus_key, label in GENRE_LABELS.items():
        row = reg.execute("SELECT kg_ids FROM corpora WHERE name = ?", (corpus_key,)).fetchone()
        if row is None:
            results.append(
                {"corpus": corpus_key, "label": label, "books": 0, "nodes": 0, "edges": 0}
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
    import platform  # pylint: disable=import-outside-toplevel
    import socket  # pylint: disable=import-outside-toplevel

    genre_stats = collect_genre_stats(registry_path)
    git = _git_info(repo_root)

    try:
        version = importlib.metadata.version("gutenberg-kg")
    except Exception:  # pylint: disable=broad-exception-caught
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


def snapshot_build(
    registry_path: Path,
    repo_root: Path,
    corpus_root: Path,
) -> dict[str, Any]:
    """Build a corpus snapshot dict without writing it to disk.

    :param registry_path: KGRAG registry SQLite path.
    :param repo_root: Root of the gutenberg_kg repository.
    :param corpus_root: Corpus data directory.
    :return: Snapshot dict ready for JSON serialisation.
    """
    genre_stats = collect_genre_stats(registry_path)
    git = _git_info(repo_root)

    try:
        version = importlib.metadata.version("gutenberg-kg")
    except Exception:  # pylint: disable=broad-exception-caught
        version = "unknown"

    return {
        "kind": "corpus_snapshot",
        "schema_version": 1,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": version,
        "branch": git["branch"],
        "commit": git["commit"],
        "commit_full": git["commit_full"],
        "totals": {
            "books": sum(g["books"] for g in genre_stats),
            "authors": _count_authors(corpus_root),
            "nodes": sum(g["nodes"] for g in genre_stats),
            "edges": sum(g["edges"] for g in genre_stats),
        },
        "genres": genre_stats,
    }


def snapshot_save(
    registry_path: Path,
    repo_root: Path,
    corpus_root: Path,
    output: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Build and persist a corpus snapshot.

    :param registry_path: KGRAG registry SQLite path.
    :param repo_root: Root of the gutenberg_kg repository.
    :param corpus_root: Corpus data directory.
    :param output: Override output file path
        (default: ``<corpus_root>/.snapshots/snapshot-<ts>.json``).
    :return: Tuple of ``(saved_path, snapshot_dict)``.
    """
    snap = snapshot_build(registry_path, repo_root, corpus_root)
    safe_ts = snap["timestamp"].replace(":", "-").replace("+", "").split(".")[0]

    if output is not None:
        out_path = output
    else:
        snapshots_dir = corpus_root / ".snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        out_path = snapshots_dir / f"snapshot-{safe_ts}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return out_path, snap


def snapshot_list(snapshots_dir: Path) -> list[dict[str, Any]]:
    """Load and return all snapshots, oldest first.

    :param snapshots_dir: Directory containing ``snapshot-*.json`` files.
    :return: List of snapshot dicts; empty if directory not found or empty.
    """
    if not snapshots_dir.is_dir():
        return []
    result = []
    for p in sorted(snapshots_dir.glob("snapshot-*.json")):
        try:
            result.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    return result


def snapshot_show(snapshots_dir: Path, snapshot: str | None = None) -> dict[str, Any]:
    """Return the full dict for a snapshot.

    :param snapshots_dir: Directory containing ``snapshot-*.json`` files.
    :param snapshot: Filename or timestamp prefix to match
        (default: most recent).
    :return: Snapshot dict, or ``{}`` if not found.
    """
    if not snapshots_dir.is_dir():
        return {}
    paths = sorted(snapshots_dir.glob("snapshot-*.json"))
    if not paths:
        return {}
    if snapshot:
        matches = [p for p in paths if snapshot in p.name]
        if not matches:
            return {}
        path = matches[-1]
    else:
        path = paths[-1]
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # pylint: disable=broad-exception-caught
        return {}


def snapshot_diff(
    snapshots_dir: Path,
    a: str | None = None,
    b: str | None = None,
) -> dict[str, Any]:
    """Return a structured diff between two snapshots.

    :param snapshots_dir: Directory containing ``snapshot-*.json`` files.
    :param a: First snapshot filename or prefix (default: second-to-last).
    :param b: Second snapshot filename or prefix (default: most recent).
    :return: Diff dict with ``a``, ``b``, ``totals``, ``changed_genres``; or
        ``{"error": ...}`` if fewer than two snapshots exist.
    """
    if not snapshots_dir.is_dir():
        return {"error": "No snapshots directory found."}
    paths = sorted(snapshots_dir.glob("snapshot-*.json"))
    if len(paths) < 2:
        return {"error": "Need at least two snapshots to diff."}

    def _resolve(name: str | None, fallback: Path) -> dict:
        if name is None:
            try:
                return json.loads(fallback.read_text(encoding="utf-8"))
            except Exception:  # pylint: disable=broad-exception-caught
                return {}
        matches = [p for p in paths if name in p.name]
        if not matches:
            return {}
        try:
            return json.loads(matches[-1].read_text(encoding="utf-8"))
        except Exception:  # pylint: disable=broad-exception-caught
            return {}

    snap_a = _resolve(a, paths[-2])
    snap_b = _resolve(b, paths[-1])
    ta, tb = snap_a.get("totals", {}), snap_b.get("totals", {})

    def _delta(key: str) -> dict[str, int]:
        va, vb = ta.get(key, 0), tb.get(key, 0)
        return {"before": va, "after": vb, "delta": vb - va}

    genre_a = {g["corpus"]: g for g in snap_a.get("genres", [])}
    genre_b = {g["corpus"]: g for g in snap_b.get("genres", [])}
    changed = []
    for corpus_key in sorted(set(genre_a) | set(genre_b)):
        ga = genre_a.get(corpus_key, {"books": 0, "nodes": 0, "edges": 0})
        gb = genre_b.get(corpus_key, {"books": 0, "nodes": 0, "edges": 0})
        if ga["books"] != gb["books"] or ga["nodes"] != gb["nodes"]:
            changed.append(
                {
                    "corpus": corpus_key,
                    "books": {"before": ga["books"], "after": gb["books"]},
                    "nodes": {
                        "before": ga["nodes"],
                        "after": gb["nodes"],
                        "delta": gb["nodes"] - ga["nodes"],
                    },
                    "edges": {
                        "before": ga["edges"],
                        "after": gb["edges"],
                        "delta": gb["edges"] - ga["edges"],
                    },
                }
            )

    return {
        "a": {
            "timestamp": snap_a.get("timestamp"),
            "version": snap_a.get("version"),
            "commit": snap_a.get("commit"),
        },
        "b": {
            "timestamp": snap_b.get("timestamp"),
            "version": snap_b.get("version"),
            "commit": snap_b.get("commit"),
        },
        "totals": {
            "books": _delta("books"),
            "nodes": _delta("nodes"),
            "edges": _delta("edges"),
        },
        "changed_genres": changed,
    }
