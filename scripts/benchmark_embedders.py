#!/usr/bin/env python3
"""Benchmark candidate embedding models for DocKG query quality on literary text.

For each model, rebuilds the LanceDB index in an isolated subdirectory (leaving
the production index untouched), runs a fixed literary query suite, and writes
machine-readable JSON and analyst-friendly Markdown reports to analysis/.

Usage:

    python scripts/benchmark_embedders.py \\
        --books "american-literature/Adventures of Huckleberry Finn" \\
                "ancient-classical/The Odyssey" \\
                "english-literature/Pride and Prejudice" \\
        --models "all-mpnet-base-v2,BAAI/bge-small-en-v1.5,all-MiniLM-L6-v2"

    # Run against all books in a genre:
    python scripts/benchmark_embedders.py --genre american-literature

    # Full cross-genre sample (fast — one book per genre):
    python scripts/benchmark_embedders.py --sample
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Allow running without installation
_SRC = REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from doc_kg.kg import DocKG  # noqa: E402


# ---------------------------------------------------------------------------
# Query suite
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QueryCase:
    """A benchmark query specification.

    :param name: Short human-readable label.
    :param text: Natural-language query.
    :param k: Semantic seeds.
    :param hop: Graph expansion hops.
    :param max_nodes: Maximum returned nodes.
    """

    name: str
    text: str
    k: int = 8
    hop: int = 1
    max_nodes: int = 15


DEFAULT_QUERIES: list[QueryCase] = [
    QueryCase(
        name="justice and morality",
        text="what does the text say about justice and moral responsibility",
        k=8, hop=1, max_nodes=15,
    ),
    QueryCase(
        name="revenge and obsession",
        text="revenge obsession and the consequences of hatred",
        k=8, hop=1, max_nodes=15,
    ),
    QueryCase(
        name="love and social class",
        text="love across social class and marriage in society",
        k=8, hop=1, max_nodes=15,
    ),
    QueryCase(
        name="fate and hubris",
        text="hubris fate and the downfall of heroes",
        k=8, hop=1, max_nodes=15,
    ),
    QueryCase(
        name="identity and freedom",
        text="personal identity freedom and self-determination",
        k=8, hop=1, max_nodes=15,
    ),
]


# One representative book per genre for --sample mode
SAMPLE_BOOKS: list[str] = [
    "american-literature/Adventures of Huckleberry Finn",
    "ancient-classical/The Odyssey",
    "english-literature/Pride and Prejudice",
    "french-literature/Les Miserables",
    "russian-literature/Crime and Punishment",
    "philosophy/Beyond Good and Evil",
    "shakespeare/Hamlet",
    "spanish/Don Quixote",
]

DEFAULT_MODELS: list[str] = [
    "all-mpnet-base-v2",
    "BAAI/bge-small-en-v1.5",
    "all-MiniLM-L6-v2",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_")


def _node_metrics(nodes: list[dict], top_n: int) -> dict:
    top = nodes[:top_n]
    if not top:
        return {"returned": 0, "mean_score": 0.0, "mean_dist": 0.0, "mean_hop": 0.0}
    scores, dists, hops = [], [], []
    for n in top:
        rel = n.get("relevance") or {}
        scores.append(float(rel.get("score", 0.0)))
        dists.append(float(rel.get("dist", 0.0)))
        hops.append(float(rel.get("hop", 0)))
    return {
        "returned": len(nodes),
        "mean_score": statistics.fmean(scores),
        "mean_dist": statistics.fmean(dists),
        "mean_hop": statistics.fmean(hops),
    }


# ---------------------------------------------------------------------------
# Core benchmark
# ---------------------------------------------------------------------------

def _benchmark_book(
    book_dir: Path,
    models: list[str],
    queries: list[QueryCase],
    top_n: int,
) -> dict:
    """Run the full model × query matrix for one book.

    :param book_dir: Path to the book directory (must have .dockg/graph.sqlite).
    :param models: Model ids to evaluate.
    :param queries: Query suite.
    :param top_n: Top-N nodes to capture per query.
    :return: Per-book result dict.
    """
    sqlite = book_dir / ".dockg" / "graph.sqlite"
    if not sqlite.exists():
        print(f"  [!] No graph.sqlite at {sqlite} — skipping")
        return {}

    book_result: dict = {
        "book": book_dir.name,
        "book_path": str(book_dir),
        "sqlite": str(sqlite),
        "models": [],
    }

    for model in models:
        slug = _slugify(model)
        lancedb_dir = book_dir / ".dockg" / f"lancedb-bench-{slug}"
        print(f"  model={model}  lancedb={lancedb_dir.name}")

        t0 = time.perf_counter()
        kg = DocKG(
            corpus_root=str(book_dir),
            db_path=str(sqlite),
            lancedb_dir=str(lancedb_dir),
            model=model,
        )
        stats = kg.build_index(wipe=True)
        build_s = time.perf_counter() - t0
        dim = getattr(stats, "index_dim", "?")
        rows = getattr(stats, "indexed_rows", "?")
        print(f"    built {rows} rows, dim={dim}, {build_s:.1f}s")

        model_result: dict = {
            "model": model,
            "model_slug": slug,
            "lancedb_dir": str(lancedb_dir),
            "build": {"seconds": build_s, "indexed_rows": rows, "dim": dim},
            "queries": [],
        }

        for qc in queries:
            t1 = time.perf_counter()
            qr = kg.query(qc.text, k=qc.k, hop=qc.hop, max_nodes=qc.max_nodes)
            q_s = time.perf_counter() - t1

            top_nodes = []
            for rank, node in enumerate(qr.nodes[:top_n], start=1):
                rel = node.get("relevance") or {}
                top_nodes.append({
                    "rank": rank,
                    "id": node.get("id", ""),
                    "kind": node.get("kind", ""),
                    "name": node.get("name") or node.get("title") or node.get("id", ""),
                    "text_preview": (node.get("text") or "")[:120],
                    "score": float(rel.get("score", 0.0)),
                    "dist": float(rel.get("dist", 0.0)),
                    "hop": int(rel.get("hop", 0)),
                    "semantic_boost": float(rel.get("semantic_boost", 0.0)),
                })

            model_result["queries"].append({
                "name": qc.name,
                "query": qc.text,
                "k": qc.k,
                "hop": qc.hop,
                "max_nodes": qc.max_nodes,
                "seconds": q_s,
                "summary": _node_metrics(qr.nodes, top_n),
                "top_nodes": top_nodes,
            })

        book_result["models"].append(model_result)

    return book_result


def _run_benchmark(
    books: list[Path],
    models: list[str],
    queries: list[QueryCase],
    top_n: int,
) -> dict:
    started = datetime.now(UTC).isoformat()
    report: dict = {
        "started_utc": started,
        "models": models,
        "top_n": top_n,
        "query_cases": [qc.__dict__ for qc in queries],
        "books": [],
    }

    for book_dir in books:
        print(f"\n=== {book_dir.name} ===")
        result = _benchmark_book(book_dir, models, queries, top_n)
        if result:
            report["books"].append(result)

    report["completed_utc"] = datetime.now(UTC).isoformat()
    return report


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _to_markdown(report: dict) -> str:
    lines: list[str] = [
        "# DocKG Embedder Benchmark Report",
        "",
        f"- Started (UTC): {report['started_utc']}",
        f"- Completed (UTC): {report.get('completed_utc', 'n/a')}",
        f"- Models: {', '.join(f'`{m}`' for m in report['models'])}",
        f"- Top-N captured: {report['top_n']}",
        "",
    ]

    # Cross-book summary table: mean_score per model × query
    query_names = [qc["name"] for qc in report["query_cases"]]
    if report["books"]:
        lines += ["## Cross-Book Score Summary (mean cosine similarity)", ""]
        header = "| Model | Book | " + " | ".join(query_names) + " |"
        sep = "|---|---|" + "---:|" * len(query_names)
        lines += [header, sep]

        for book in report["books"]:
            for mr in book["models"]:
                scores_by_query = {
                    qr["name"]: qr["summary"]["mean_score"]
                    for qr in mr["queries"]
                }
                cols = " | ".join(
                    f"{scores_by_query.get(qn, 0.0):.3f}" for qn in query_names
                )
                lines.append(f"| `{mr['model']}` | {book['book']} | {cols} |")

        lines.append("")

    # Per-book detail
    for book in report["books"]:
        lines += [f"## Book: {book['book']}", ""]

        for mr in book["models"]:
            b = mr["build"]
            lines += [
                f"### Model: `{mr['model']}`",
                f"- Build: {b['seconds']:.1f}s, {b['indexed_rows']} rows, dim={b['dim']}",
                "",
            ]

            for qr in mr["queries"]:
                s = qr["summary"]
                lines += [
                    f"#### Query: *{qr['query']}*",
                    f"- k={qr['k']}, hop={qr['hop']}, {qr['seconds']*1000:.0f}ms",
                    f"- mean_score={s['mean_score']:.4f}  mean_dist={s['mean_dist']:.4f}"
                    f"  returned={s['returned']}",
                    "",
                    "| Rank | Kind | Name | Score | Dist | Hop |",
                    "|---:|---|---|---:|---:|---:|",
                ]
                for n in qr["top_nodes"]:
                    name = n["name"][:50]
                    lines.append(
                        f"| {n['rank']} | {n['kind']} | {name} "
                        f"| {n['score']:.4f} | {n['dist']:.4f} | {n['hop']} |"
                    )
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--books", nargs="+", metavar="REL_PATH",
        help="Relative paths from repo root to book directories (e.g. 'american-literature/Huck Finn').",
    )
    p.add_argument(
        "--genre", metavar="NAME",
        help="Run on every book in a genre directory (e.g. 'american-literature').",
    )
    p.add_argument(
        "--sample", action="store_true",
        help="Run on the built-in one-per-genre sample set.",
    )
    p.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated model ids (default: all-mpnet-base-v2, bge-small, MiniLM-L6).",
    )
    p.add_argument(
        "--top-n", type=int, default=5,
        help="Top nodes to capture per query (default: 5).",
    )
    p.add_argument(
        "--out-json", default="",
        help="Output JSON path (default: analysis/embedder_benchmark_<ts>.json).",
    )
    p.add_argument(
        "--out-md", default="",
        help="Output Markdown path (default: analysis/embedder_benchmark_<ts>.md).",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    # Resolve book list
    books: list[Path] = []
    if args.sample:
        books = [REPO_ROOT / b for b in SAMPLE_BOOKS]
    elif args.genre:
        genre_dir = REPO_ROOT / args.genre
        if not genre_dir.is_dir():
            print(f"ERROR: genre directory not found: {genre_dir}")
            return 2
        books = sorted(d for d in genre_dir.iterdir() if d.is_dir())
    elif args.books:
        books = [REPO_ROOT / b for b in args.books]
    else:
        print("ERROR: specify --books, --genre, or --sample")
        return 2

    # Filter to books that have a built sqlite
    valid = [b for b in books if (b / ".dockg" / "graph.sqlite").exists()]
    skipped = [b for b in books if b not in valid]
    if skipped:
        print(f"[!] Skipping {len(skipped)} books without graph.sqlite:")
        for b in skipped:
            print(f"    {b}")
    if not valid:
        print("ERROR: no books with graph.sqlite found")
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()]

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    analysis_dir = REPO_ROOT / "analysis"
    analysis_dir.mkdir(exist_ok=True)

    out_json = Path(args.out_json) if args.out_json else analysis_dir / f"embedder_benchmark_{ts}.json"
    out_md = Path(args.out_md) if args.out_md else analysis_dir / f"embedder_benchmark_{ts}.md"

    print(f"DocKG Embedder Benchmark")
    print(f"  Books:  {len(valid)}")
    print(f"  Models: {models}")
    print(f"  Queries: {len(DEFAULT_QUERIES)}")

    report = _run_benchmark(valid, models, DEFAULT_QUERIES, args.top_n)

    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out_md.write_text(_to_markdown(report), encoding="utf-8")

    print(f"\nWrote: {out_json}")
    print(f"Wrote: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
