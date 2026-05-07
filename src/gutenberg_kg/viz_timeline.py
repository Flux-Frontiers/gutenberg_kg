"""viz_timeline.py — Corpus Growth Timeline Visualization for GutenbergKG.

Visualizes corpus expansion across snapshots using interactive 2D or 3D
Plotly charts.  Shows trends in book count, author count, nodes, and edges
over time.

Features:
  - 2D mode: 2×2 subplots for Books, Authors, Nodes, Edges
  - 3D mode: normalized multi-metric scatter stacked by metric type
  - Text summary with first/latest/delta for each metric
  - Hover tooltips with snapshot version and timestamp
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import plotly.subplots as subplots

from gutenberg_kg.corpus import snapshot_list

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_snapshots_timeline(snapshots_dir: Path) -> dict[str, list[Any]]:
    """Load corpus snapshots and return parallel timeline lists.

    :param snapshots_dir: Path to ``corpus/.snapshots/``.
    :return: Dict with keys ``timestamps``, ``versions``, ``commits``,
        ``books``, ``authors``, ``nodes``, ``edges``; empty if no snapshots.
    """
    snaps = snapshot_list(snapshots_dir)
    if not snaps:
        return {}

    timeline: dict[str, list[Any]] = {
        "timestamps": [],
        "versions": [],
        "commits": [],
        "books": [],
        "authors": [],
        "nodes": [],
        "edges": [],
    }
    for snap in snaps:
        t = snap.get("totals", {})
        timeline["timestamps"].append(snap.get("timestamp", ""))
        timeline["versions"].append(snap.get("version", ""))
        timeline["commits"].append(snap.get("commit", "unknown"))
        timeline["books"].append(t.get("books", 0))
        timeline["authors"].append(t.get("authors", 0))
        timeline["nodes"].append(t.get("nodes", 0))
        timeline["edges"].append(t.get("edges", 0))

    return timeline


# ---------------------------------------------------------------------------
# 2D figure
# ---------------------------------------------------------------------------


def create_timeline_figure(snapshots_dir: Path) -> go.Figure:
    """Create a 2×2 interactive subplot figure of corpus growth metrics.

    Panels: Books | Authors | Nodes | Edges, all plotted against snapshot date.

    :param snapshots_dir: Path to ``corpus/.snapshots/``.
    :return: Plotly Figure ready for display.
    """
    timeline = load_snapshots_timeline(snapshots_dir)
    if not timeline:
        return go.Figure().add_annotation(
            text="No snapshots found — run 'gutenkg snapshot save' first."
        )

    x = [ts[:10] for ts in timeline["timestamps"]]  # YYYY-MM-DD
    hover = [
        f"<b>v{v}</b> ({c})<br>{ts}"
        for v, c, ts in zip(timeline["versions"], timeline["commits"], timeline["timestamps"])
    ]

    fig = subplots.make_subplots(
        rows=2,
        cols=2,
        subplot_titles=("Books", "Authors", "Nodes", "Edges"),
        vertical_spacing=0.18,
        horizontal_spacing=0.12,
    )

    def _trace(y: list, name: str, color: str) -> go.Scatter:
        return go.Scatter(
            x=x,
            y=y,
            mode="lines+markers",
            name=name,
            line=dict(color=color, width=3),
            marker=dict(size=8),
            hovertemplate=f"<b>{name}:</b> %{{y:,}}<br>%{{customdata}}<extra></extra>",
            customdata=hover,
        )

    fig.add_trace(_trace(timeline["books"], "Books", "#f59e0b"), row=1, col=1)
    fig.add_trace(_trace(timeline["authors"], "Authors", "#8b5cf6"), row=1, col=2)
    fig.add_trace(_trace(timeline["nodes"], "Nodes", "#22c55e"), row=2, col=1)
    fig.add_trace(_trace(timeline["edges"], "Edges", "#3b82f6"), row=2, col=2)

    fig.update_layout(
        title_text=("<b>GutenbergKG Corpus Growth</b><br><sub>Snapshots over time</sub>"),
        title_font_size=20,
        height=800,
        width=1400,
        hovermode="x unified",
        template="plotly_dark",
        showlegend=False,
    )

    for row, col, ylabel in [(1, 1, "Books"), (1, 2, "Authors"), (2, 1, "Nodes"), (2, 2, "Edges")]:
        fig.update_xaxes(title_text="Snapshot date", row=row, col=col, tickangle=-30)
        fig.update_yaxes(title_text=ylabel, row=row, col=col)

    return fig


# ---------------------------------------------------------------------------
# 3D figure
# ---------------------------------------------------------------------------


def create_3d_timeline_figure(snapshots_dir: Path) -> go.Figure:
    """Create a 3D scatter plot showing normalized corpus growth metrics.

    X: snapshot index  |  Y: normalized value (0–100 %)  |  Z: metric type

    :param snapshots_dir: Path to ``corpus/.snapshots/``.
    :return: Plotly 3D Figure.
    """
    timeline = load_snapshots_timeline(snapshots_dir)
    if not timeline:
        return go.Figure().add_annotation(
            text="No snapshots found — run 'gutenkg snapshot save' first."
        )

    idx = list(range(len(timeline["timestamps"])))
    commits = timeline["commits"]

    def _norm(vals: list[int]) -> list[float]:
        mx = max(vals) if vals else 1
        return [v / mx * 100 if mx else 0.0 for v in vals]

    metrics = [
        ("Books", _norm(timeline["books"]), "#f59e0b", 0),
        ("Nodes", _norm(timeline["nodes"]), "#22c55e", 1),
        ("Edges", _norm(timeline["edges"]), "#3b82f6", 2),
        ("Authors", _norm(timeline["authors"]), "#8b5cf6", 3),
    ]

    fig = go.Figure()
    for name, y, color, z_level in metrics:
        fig.add_trace(
            go.Scatter3d(
                x=idx,
                y=y,
                z=[z_level] * len(idx),
                mode="lines+markers",
                name=name,
                line=dict(color=color, width=4),
                marker=dict(size=6),
                hovertemplate=(
                    f"<b>{name}:</b> %{{y:.0f}}%<br><b>Snapshot:</b> %{{customdata}}<extra></extra>"
                ),
                customdata=commits,
            )
        )

    fig.update_layout(
        title="<b>GutenbergKG 3D Corpus Timeline</b><br><sub>Normalized growth across snapshots</sub>",
        scene=dict(
            xaxis_title="Snapshot index",
            yaxis_title="Metric (0–100 %)",
            zaxis=dict(
                title="Metric",
                tickvals=[0, 1, 2, 3],
                ticktext=["Books", "Nodes", "Edges", "Authors"],
            ),
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.3)),
        ),
        width=1200,
        height=800,
        template="plotly_dark",
        hovermode="closest",
    )

    return fig


# ---------------------------------------------------------------------------
# Text summary
# ---------------------------------------------------------------------------

_W = 64  # Inner width of the summary box


def _row(label: str, value: str) -> str:
    body = f"{label:<12}{value}"
    return f"| {body:<{_W}} |"


def display_timeline_summary(snapshots_dir: Path) -> str:
    """Return an ASCII-boxed summary of corpus growth across snapshots.

    :param snapshots_dir: Path to ``corpus/.snapshots/``.
    :return: Multi-line formatted string.
    """
    timeline = load_snapshots_timeline(snapshots_dir)
    if not timeline:
        return "No snapshots found — run 'gutenkg snapshot save' first."

    n = len(timeline["timestamps"])
    sep = "+" + "=" * (_W + 2) + "+"
    title = f"{'GutenbergKG Corpus Growth Summary':^{_W}}"

    def _section(name: str, first: int, last: int) -> list[str]:
        delta = last - first
        sign = "+" if delta >= 0 else ""
        return [
            sep,
            f"| {f'  {name}:':<{_W}} |",
            _row("  First:  ", f"{first:,}"),
            _row("  Latest: ", f"{last:,}"),
            _row("  Δ:      ", f"{sign}{delta:,}"),
        ]

    lines = [
        sep,
        f"| {title} |",
        sep,
        _row("Snapshots:", str(n)),
        _row(
            "Time range:", f"{timeline['timestamps'][0][:10]} → {timeline['timestamps'][-1][:10]}"
        ),
        _row("Versions:", f"{timeline['versions'][0]} → {timeline['versions'][-1]}"),
    ]

    for metric, key in [
        ("BOOKS", "books"),
        ("AUTHORS", "authors"),
        ("NODES", "nodes"),
        ("EDGES", "edges"),
    ]:
        lines += _section(metric, timeline[key][0], timeline[key][-1])

    lines.append(sep)
    return "\n".join(lines)
