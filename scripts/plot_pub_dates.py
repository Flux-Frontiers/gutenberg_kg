"""Write the interactive literary-years page for the docs site.

Reads ``corpus/pub_dates.tsv`` and writes ``docs/assets/literary_years.html``:
summary figures, works by era, each genre's span (one dot per work), the
confidence and source breakdowns, and the years to review. The charts are
Plotly figures built here; the page loads plotly.js from its CDN and follows
the docs site's light or dark scheme. ``docs/PUB_DATES.md`` embeds it.

Usage::

    poetry run python scripts/plot_pub_dates.py [OUT.html]

Rerun after regenerating ``corpus/pub_dates.tsv``. Needs plotly (the ``viz``
extra).
"""

from __future__ import annotations

import csv
import html
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import median

import plotly
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "corpus" / "pub_dates.tsv"
OUT = ROOT / "docs" / "assets" / "literary_years.html"

# Piecewise time axis: the corpus thins out before 1800, so earlier time is
# compressed and the nineteenth century gets the most room.
KNOTS = [(-1000, 0.0), (0, 14.0), (1500, 34.0), (1800, 62.0), (1931, 100.0)]
TICKS = [-1000, 0, 1000, 1500, 1600, 1700, 1800, 1850, 1900]
ERAS = [
    ("< 500 BC", -10_000, -500),
    ("500-1 BC", -500, 1),
    ("1-999", 1, 1000),
    ("1000-1499", 1000, 1500),
    ("1500s", 1500, 1600),
    ("1600s", 1600, 1700),
    ("1700s", 1700, 1800),
    ("1800-1849", 1800, 1850),
    ("1850-1899", 1850, 1900),
    ("1900-1931", 1900, 2000),
]
CONFIDENCE = {
    "high": "Sources agree",
    "medium": "One source",
    "hand": "Hand-dated",
    "conflict": "Conflict",
    "low": "Estimate",
}
SOURCE = {
    "summary+wikidata": "Summary + Wikidata",
    "summary": "Summary only",
    "wikidata": "Wikidata only",
    "override": "Override file",
}
# Plotly validates colors, so figures carry placeholder hexes that the page
# swaps for its CSS variables (per light or dark scheme) before drawing.
VARS = ["--c-high", "--c-medium", "--c-hand", "--c-conflict", "--c-range", "--bg"]
SENTINEL = {v: f"#0000{i + 1:02x}" for i, v in enumerate(VARS)}


def css_var(name: str) -> str:
    """Placeholder color for a CSS variable.

    :param name: Variable name, e.g. ``--c-high``.
    :return: Its sentinel hex.
    """
    return SENTINEL[name]


def unsentinel(x):
    """Replace sentinel hexes with their CSS variable names, recursively.

    :param x: Figure JSON (dicts, lists, scalars).
    :return: The same structure with variable names in place of sentinels.
    """
    back = {h: v for v, h in SENTINEL.items()}
    if isinstance(x, str):
        return back.get(x, x)
    if isinstance(x, list):
        return [unsentinel(i) for i in x]
    if isinstance(x, dict):
        return {k: unsentinel(v) for k, v in x.items()}
    return x


CONF_COLOR = {
    "high": css_var("--c-high"),
    "medium": css_var("--c-medium"),
    "hand": css_var("--c-hand"),
    "conflict": css_var("--c-conflict"),
    "low": css_var("--c-medium"),
}


def year_label(y: int | None) -> str:
    """Format a signed year: ``-440`` -> ``440 BC``.

    :param y: Year, negative for BC, or None.
    :return: Display text, empty for None.
    """
    if y is None:
        return ""
    return f"{-y} BC" if y < 0 else str(y)


def axis_pos(y: float) -> float:
    """Map a year onto the piecewise time axis (0-100).

    :param y: Year, negative for BC.
    :return: Position on the axis.
    """
    if y <= KNOTS[0][0]:
        return KNOTS[0][1]
    for (y0, p0), (y1, p1) in zip(KNOTS, KNOTS[1:], strict=False):
        if y <= y1:
            return p0 + (p1 - p0) * (y - y0) / (y1 - y0)
    return KNOTS[-1][1]


def read_table(path: Path) -> list[dict]:
    """Read the resolved year table, skipping its comment lines.

    :param path: ``corpus/pub_dates.tsv``.
    :return: One dict per work, with ``genre``, ``title`` and int ``year``.
    """
    lines = [
        ln for ln in path.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")
    ]
    rows = []
    for r in csv.DictReader(lines, delimiter="\t"):
        if not r.get("year"):
            continue
        genre, title = r["entry"].split("/", 1)
        rows.append(
            {
                **r,
                "genre": genre,
                "title": title,
                "year": int(r["year"]),
                "flags": r.get("flags") or "",
            }
        )
    return rows


def era_figure(rows: list[dict]) -> go.Figure:
    """Bar chart of works per era.

    :param rows: Works.
    :return: Figure.
    """
    counts = [sum(lo <= r["year"] < hi for r in rows) for _, lo, hi in ERAS]
    fig = go.Figure(
        go.Bar(
            x=[e for e, _, _ in ERAS],
            y=counts,
            text=counts,
            textposition="outside",
            cliponaxis=False,
            marker={"color": css_var("--c-high")},
            hovertemplate="<b>%{x}</b><br>%{y} works<extra></extra>",
        )
    )
    fig.update_layout(height=320, yaxis={"visible": False}, xaxis={"showgrid": False}, bargap=0.25)
    return fig


def genre_figure(rows: list[dict]) -> go.Figure:
    """Strip chart: one row per genre, one dot per work, on the piecewise axis.

    :param rows: Works.
    :return: Figure.
    """
    by_genre: dict[str, list[dict]] = {}
    for r in rows:
        by_genre.setdefault(r["genre"], []).append(r)
    order = sorted(by_genre, key=lambda g: median(w["year"] for w in by_genre[g]), reverse=True)
    fig = go.Figure()
    for g in order:
        ys = [w["year"] for w in by_genre[g]]
        fig.add_trace(
            go.Scatter(
                x=[axis_pos(min(ys)), axis_pos(max(ys))],
                y=[g, g],
                mode="lines",
                line={"color": css_var("--c-range"), "width": 6},
                hoverinfo="skip",
                showlegend=False,
            )
        )
    for conf in CONFIDENCE:
        pts = [r for r in rows if r["confidence"] == conf]
        if not pts:
            continue
        fig.add_trace(
            go.Scatter(
                x=[axis_pos(r["year"]) for r in pts],
                y=[r["genre"] for r in pts],
                mode="markers",
                name=CONFIDENCE[conf],
                marker={
                    "color": CONF_COLOR[conf],
                    "size": 10 if conf == "conflict" else 8,
                    "opacity": 0.85,
                    "line": {"width": 1, "color": css_var("--bg")},
                    "symbol": "diamond" if conf == "conflict" else "circle",
                },
                customdata=[
                    [r["title"], year_label(r["year"]), SOURCE.get(r["source"], r["source"])]
                    for r in pts
                ],
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>%{customdata[1]} · %{y}<br>"
                    + CONFIDENCE[conf]
                    + " · %{customdata[2]}<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        height=36 * len(order) + 110,
        xaxis={
            "range": [-2, 102],
            "tickvals": [axis_pos(t) for t in TICKS],
            "ticktext": [year_label(t) if t else "1 AD" for t in TICKS],
            "showgrid": True,
            "zeroline": False,
            "tickangle": 0,
        },
        yaxis={"categoryorder": "array", "categoryarray": order[::-1], "showgrid": False},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 0},
    )
    return fig


def share_figure(counts: Counter, labels: dict[str, str], colors: dict[str, str]) -> go.Figure:
    """Horizontal bars with count and share.

    :param counts: Works per key.
    :param labels: Display label per key.
    :param colors: CSS color variable per key.
    :return: Figure.
    """
    keys = [k for k in labels if counts.get(k)][::-1]
    total = sum(counts.values())
    fig = go.Figure(
        go.Bar(
            y=[labels[k] for k in keys],
            x=[counts[k] for k in keys],
            orientation="h",
            text=[f"{counts[k]}  ({round(100 * counts[k] / total)}%)" for k in keys],
            textposition="outside",
            cliponaxis=False,
            marker={"color": [colors.get(k, css_var("--c-high")) for k in keys]},
            hovertemplate="<b>%{y}</b><br>%{x} works<extra></extra>",
        )
    )
    fig.update_layout(
        height=16 + 44 * len(keys),
        # Fixed margins: automargin let Safari push one chart down into the next section.
        margin={"l": 16 + 7 * max(len(labels[k]) for k in keys), "r": 84, "t": 8, "b": 8},
        xaxis={"visible": False, "range": [0, max(counts[k] for k in keys) * 1.02]},
        yaxis={"automargin": False},
        bargap=0.35,
    )
    return fig


def review_rows(rows: list[dict]) -> list[dict]:
    """Works whose year needs a look: conflicts, approximate and clamped years.

    :param rows: Works.
    :return: Rows for the review table, conflicts first.
    """
    out = []
    for r in rows:
        if r["confidence"] != "conflict" and not r["flags"]:
            continue
        status = (
            "conflict"
            if r["confidence"] == "conflict"
            else "clamped to death year"
            if r["flags"].startswith("clamped")
            else r["flags"]
        )
        to_int = lambda v: int(v) if v not in (None, "") else None  # noqa: E731
        out.append(
            {
                "title": r["title"],
                "genre": r["genre"],
                "year": year_label(r["year"]),
                "summary": year_label(to_int(r.get("summary_year"))),
                "wikidata": year_label(to_int(r.get("wd_year"))),
                "status": status,
            }
        )
    return sorted(out, key=lambda r: (r["status"] != "conflict", r["genre"], r["title"]))


def render(rows: list[dict]) -> str:
    """Build the page.

    :param rows: Works.
    :return: HTML text.
    """
    conf = Counter(r["confidence"] for r in rows)
    src = Counter(r["source"] for r in rows)
    ys = [r["year"] for r in rows]
    figs = {
        "era": era_figure(rows),
        "genre": genre_figure(rows),
        "conf": share_figure(conf, CONFIDENCE, CONF_COLOR),
        "source": share_figure(src, SOURCE, {k: css_var("--c-high") for k in SOURCE}),
    }
    payload = {k: unsentinel(json.loads(f.to_json())) for k, f in figs.items()}
    for fig in payload.values():
        fig["layout"].pop("template", None)
    stats = {
        "works": len(rows),
        "earliest": year_label(min(ys)),
        "latest": year_label(max(ys)),
        "modern": sum(y >= 1800 for y in ys),
        "bc": sum(y < 0 for y in ys),
        "genres": len({r["genre"] for r in rows}),
    }
    review = "\n".join(
        "<tr>"
        f"<td>{html.escape(r['title'])}</td><td>{html.escape(r['genre'])}</td>"
        f"<td class='num'>{r['year']}</td><td class='num'>{r['summary'] or '—'}</td>"
        f"<td class='num'>{r['wikidata'] or '—'}</td>"
        f"<td><span class='pill{' warn' if r['status'] == 'conflict' else ''}'>{html.escape(r['status'])}</span></td>"
        "</tr>"
        for r in review_rows(rows)
    )
    tiles = [
        ("Works dated", stats["works"], f"across {stats['genres']} genres", ""),
        ("Sources agree", conf["high"], "summary and Wikidata within two years", "good"),
        ("Hand-dated", conf["hand"], "from the overrides file", ""),
        ("Conflicts", conf["conflict"], "sources disagree; earlier year kept", "warn"),
    ]
    tile_html = "\n".join(
        f"<div class='tile'><span class='k'>{k}</span><span class='v {c}'>{v}</span><span class='s'>{s}</span></div>"
        for k, v, s, c in tiles
    )
    return (
        TEMPLATE.replace("{{PLOTLY}}", plotly.offline.get_plotlyjs_version())
        .replace("{{TILES}}", tile_html)
        .replace("{{WORKS}}", str(stats["works"]))
        .replace("{{EARLIEST}}", stats["earliest"])
        .replace("{{LATEST}}", stats["latest"])
        .replace("{{MODERN}}", str(stats["modern"]))
        .replace("{{BC}}", str(stats["bc"]))
        .replace("{{REVIEW}}", review)
        .replace("{{FIGS}}", json.dumps(payload, separators=(",", ":")))
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Corpus Literary Years</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500&family=Roboto+Mono:wght@400;500&family=Roboto+Slab:wght@300;400&display=swap">
<script src="https://cdn.plot.ly/plotly-{{PLOTLY}}.min.js" charset="utf-8"></script>
<style>
/* Layout: one column of sections; tiles in a wrapping row; two share charts side by side. */
:root {
  --bg: #ffffff; --fg: #1f2330; --muted: #5d6273; --line: #e3e5ee; --panel: #f6f7fb;
  --c-high: #3f51b5; --c-medium: #8c9ae0; --c-hand: #607d8b; --c-conflict: #e08a00; --c-range: #e1e4f2;
  --good: #2e7d32; --warn: #b26a00; --grid: #eceef5;
  --sans: Roboto, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  --mono: "Roboto Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --slab: "Roboto Slab", Georgia, serif;
}
:root[data-scheme="slate"] {
  --bg: #1e2129; --fg: #e3e6f0; --muted: #a2a8bb; --line: #343947; --panel: #262a35;
  --c-high: #8c9eff; --c-medium: #5562a8; --c-hand: #90a4ae; --c-conflict: #ffb74d; --c-range: #343a52;
  --good: #81c784; --warn: #ffb74d; --grid: #2c303c;
  color-scheme: dark;
}
html, body { margin: 0; background: var(--bg); color: var(--fg); font-family: var(--sans); font-size: 15px; line-height: 1.5; }
.page { display: grid; gap: 2.25rem; padding: 4px 2px 24px; }
.lede { margin: 0; max-width: 64ch; color: var(--muted); font-size: 1.05rem; }
.lede b { color: var(--fg); font-weight: 500; font-variant-numeric: tabular-nums; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.tile { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; display: grid; gap: 2px; }
.tile .k { font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.tile .v { font-family: var(--slab); font-weight: 300; font-size: 2.3rem; line-height: 1.15; font-variant-numeric: tabular-nums; }
.tile .v.good { color: var(--good); } .tile .v.warn { color: var(--warn); }
.tile .s { font-size: .8rem; color: var(--muted); }
section { display: grid; gap: .35rem; min-width: 0; }
h3 { margin: 0; font-weight: 500; font-size: 1.1rem; text-wrap: balance; }
.note { margin: 0; color: var(--muted); font-size: .85rem; max-width: 70ch; }
.pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 2rem; align-items: start; }
.chart { width: 100%; min-width: 0; overflow: hidden; }
.tablewrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); font-weight: 500; }
td.num { font-family: var(--mono); font-size: .85rem; white-space: nowrap; }
.pill { display: inline-block; font-size: .75rem; padding: 0 8px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); white-space: nowrap; }
.pill.warn { color: var(--warn); border-color: var(--warn); }
code { font-family: var(--mono); font-size: .85em; }
</style>
</head>
<body>
<div class="page">
  <p class="lede">The <b>{{WORKS}}</b> works in the corpus run from <b>{{EARLIEST}}</b> to <b>{{LATEST}}</b>.
  <b>{{MODERN}}</b> of them date from 1800 on, and <b>{{BC}}</b> are BC.</p>
  <div class="tiles">{{TILES}}</div>
  <section>
    <h3>Works by era</h3>
    <p class="note">Eras are uneven on purpose: the corpus thins out before 1700, so early centuries are pooled.</p>
    <div class="chart" id="era"></div>
  </section>
  <section>
    <h3>Each genre's span</h3>
    <p class="note">One dot per work; hover for its title. The axis is compressed before 1800, where few works sit. Genres are ordered by their median year.</p>
    <div class="chart" id="genre"></div>
  </section>
  <div class="pair">
    <section><h3>How sure each year is</h3><div class="chart" id="conf"></div></section>
    <section><h3>Where each year came from</h3><div class="chart" id="source"></div></section>
  </div>
  <section>
    <h3>Years to review</h3>
    <p class="note">Conflicts, approximate Wikidata years and years clamped to the author's death. To settle one, add it to <code>corpus/pub_dates_overrides.tsv</code>.</p>
    <div class="tablewrap"><table>
      <thead><tr><th>Work</th><th>Genre</th><th>Year kept</th><th>Summary says</th><th>Wikidata says</th><th>Status</th></tr></thead>
      <tbody>{{REVIEW}}</tbody>
    </table></div>
  </section>
</div>
<script>
const FIGS = {{FIGS}};
const root = document.documentElement;

// Follow the docs site's scheme toggle when embedded; else the OS setting.
function parentScheme() {
  try { return window.parent.document.body.getAttribute('data-md-color-scheme'); } catch (e) { return null; }
}
function applyScheme() {
  const s = parentScheme() || (matchMedia('(prefers-color-scheme: dark)').matches ? 'slate' : 'default');
  root.dataset.scheme = s;
}

// Replace "--name" color strings in a figure with the current CSS values.
function resolve(v) {
  const css = getComputedStyle(root);
  const walk = (x) => {
    if (typeof x === 'string' && x.startsWith('--')) return css.getPropertyValue(x).trim() || x;
    if (Array.isArray(x)) return x.map(walk);
    if (x && typeof x === 'object') { const o = {}; for (const k in x) o[k] = walk(x[k]); return o; }
    return x;
  };
  return walk(v);
}

function baseLayout(extra) {
  const css = getComputedStyle(root), c = (n) => css.getPropertyValue(n).trim();
  const axis = { color: c('--muted'), gridcolor: c('--grid'), linecolor: c('--line'), zerolinecolor: c('--line'),
                 tickfont: { size: 12 }, automargin: true, fixedrange: true };
  const l = Object.assign({}, extra);
  l.paper_bgcolor = 'rgba(0,0,0,0)'; l.plot_bgcolor = 'rgba(0,0,0,0)';
  l.font = { family: c('--sans'), color: c('--fg'), size: 13 };
  l.margin = Object.assign({ l: 8, r: 24, t: 28, b: 36 }, extra.margin || {});
  l.hoverlabel = { bgcolor: c('--panel'), bordercolor: c('--line'), font: { color: c('--fg'), family: c('--sans') } };
  l.xaxis = Object.assign({}, axis, extra.xaxis || {});
  l.yaxis = Object.assign({}, axis, extra.yaxis || {});
  if (l.legend) l.legend.font = { color: c('--muted') };
  delete l.template;
  return l;
}

function draw() {
  applyScheme();
  for (const [id, fig] of Object.entries(FIGS)) {
    const f = resolve(fig);
    document.getElementById(id).style.height = f.layout.height + 'px';
    Plotly.react(id, f.data, baseLayout(f.layout), { displayModeBar: false, responsive: true });
  }
  fitFrame();
}

// Grow the docs iframe to fit, so the page scrolls as one.
function fitFrame() {
  if (window.frameElement) window.frameElement.style.height = document.documentElement.scrollHeight + 'px';
}

draw();
if (document.fonts) document.fonts.ready.then(draw);
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', draw);
try {
  new MutationObserver(draw).observe(window.parent.document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });
} catch (e) {}
new ResizeObserver(fitFrame).observe(document.body);
</script>
</body>
</html>
"""


def main() -> None:
    """Write the page."""
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(read_table(TABLE)), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


if __name__ == "__main__":
    main()
