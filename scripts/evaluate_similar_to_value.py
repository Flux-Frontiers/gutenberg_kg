#!/usr/bin/env python3
"""Evaluate whether SIMILAR_TO is worth enabling by default.

This script runs labeled retrieval evaluation across three conditions:

1. none: no SIMILAR_TO edge discovery, SIMILAR_TO excluded from traversal.
2. cap8: SIMILAR_TO enabled with similar_max_degree=8.
3. cap15: SIMILAR_TO enabled with similar_max_degree=15.

It reads labeled queries from analysis/similar_to_query_template.csv where both
query_text and expected_node_ids are filled, then computes:

1. Recall@k
2. MRR@k
3. nDCG@k

It also tracks edge/build costs and outputs recommendation signals.

Usage:

    poetry run python scripts/evaluate_similar_to_value.py

    poetry run python scripts/evaluate_similar_to_value.py \
      --conditions none,8,15 \
      --k 8 --hop 1 --max-nodes 15
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BookSpec:
    """Book selection entry loaded from the manifest."""

    genre: str
    book_name: str
    book_relpath: str
    size_tier: str


@dataclass(frozen=True)
class LabeledQuery:
    """One labeled query from the template.

    :param query_id: Stable query id.
    :param query_type: Query category.
    :param genre: Genre label.
    :param book_relpath: Book path relative to repo root.
    :param query_text: Query text.
    :param expected_ids: Relevant node ids.
    """

    query_id: str
    query_type: str
    genre: str
    book_relpath: str
    query_text: str
    expected_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvalRow:
    """Per-query evaluation output row."""

    condition: str
    genre: str
    size_tier: str
    book_name: str
    book_relpath: str
    query_id: str
    query_type: str
    query_text: str
    expected_count: int
    returned_count: int
    hits_at_k: int
    recall_at_k: float
    mrr_at_k: float
    ndcg_at_k: float
    query_seconds: float


@dataclass(frozen=True)
class ConditionBookRow:
    """Per-book condition cost row."""

    condition: str
    genre: str
    size_tier: str
    book_name: str
    book_relpath: str
    build_seconds: float
    similar_edges: int


@dataclass(frozen=True)
class ConditionSummary:
    """Aggregated condition metrics."""

    condition: str
    n_queries: int
    mean_recall_at_k: float
    mean_mrr_at_k: float
    mean_ndcg_at_k: float
    mean_query_seconds: float
    mean_build_seconds: float
    mean_similar_edges: float


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--manifest",
        default="analysis/similar_to_book_manifest.csv",
        help="Book manifest CSV path relative to repo root.",
    )
    p.add_argument(
        "--queries",
        default="analysis/similar_to_query_template.csv",
        help="Labeled query CSV path relative to repo root.",
    )
    p.add_argument(
        "--conditions",
        default="none,8,15",
        help="Comma-separated conditions. Use 'none' for no SIMILAR_TO, or integer caps.",
    )
    p.add_argument("--k", type=int, default=8, help="Semantic seed count.")
    p.add_argument("--hop", type=int, default=1, help="Expansion hop count.")
    p.add_argument(
        "--max-nodes",
        type=int,
        default=15,
        help="Max nodes returned and metric cutoff k.",
    )
    p.add_argument("--similar-k", type=int, default=5, help="similar_k for edge build.")
    p.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="similarity_edge_threshold for edge build.",
    )
    p.add_argument("--n-workers", type=int, default=4, help="Embedding cache worker count.")
    p.add_argument(
        "--limit-books",
        type=int,
        default=0,
        help="Limit number of books for quick runs (0=all).",
    )
    p.add_argument(
        "--out-prefix",
        default="analysis/similar_to_value_eval",
        help="Output file prefix relative to repo root.",
    )
    return p.parse_args()


def parse_conditions(raw: str) -> list[str]:
    """Parse condition list into canonical labels."""
    vals = [x.strip().lower() for x in raw.split(",") if x.strip()]
    if not vals:
        raise ValueError("No conditions provided")

    out: list[str] = []
    for v in vals:
        if v == "none":
            out.append("none")
        else:
            cap = int(v)
            if cap < 0:
                raise ValueError("Caps must be >= 0")
            out.append(str(cap))
    return out


def load_manifest(path: Path) -> list[BookSpec]:
    """Load books from manifest CSV."""
    books: list[BookSpec] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            books.append(
                BookSpec(
                    genre=(r.get("genre") or "").strip(),
                    book_name=(r.get("book_name") or "").strip(),
                    book_relpath=(r.get("book_relpath") or "").strip(),
                    size_tier=(r.get("size_tier") or "").strip(),
                )
            )
    return books


def _split_expected_ids(raw: str) -> tuple[str, ...]:
    """Split expected node ids from CSV cell.

    Accepts comma, semicolon, pipe, or newline delimiters.
    """
    seps = ["|", ";", "\n"]
    tmp = raw
    for s in seps:
        tmp = tmp.replace(s, ",")
    parts = [x.strip() for x in tmp.split(",") if x.strip()]
    return tuple(parts)


def load_labeled_queries(path: Path) -> dict[str, list[LabeledQuery]]:
    """Load labeled queries grouped by book path.

    A row is considered labeled if both query_text and expected_node_ids are set.
    """
    grouped: dict[str, list[LabeledQuery]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            book_relpath = (r.get("book_relpath") or "").strip()
            qtext = (r.get("query_text") or "").strip()
            expected = (r.get("expected_node_ids") or "").strip()
            if not book_relpath or not qtext or not expected:
                continue

            expected_ids = _split_expected_ids(expected)
            if not expected_ids:
                continue

            grouped[book_relpath].append(
                LabeledQuery(
                    query_id=(r.get("query_id") or "").strip() or "",
                    query_type=(r.get("query_type") or "").strip() or "unknown",
                    genre=(r.get("genre") or "").strip() or "",
                    book_relpath=book_relpath,
                    query_text=qtext,
                    expected_ids=expected_ids,
                )
            )
    return grouped


def clear_similar_edges(kg: object) -> None:
    """Delete SIMILAR_TO edges via active store connection."""
    con = getattr(getattr(kg, "store"), "con")
    con.execute("DELETE FROM edges WHERE rel='SIMILAR_TO'")
    con.commit()


def count_similar_edges(db_path: Path) -> int:
    """Count SIMILAR_TO edges in graph DB."""
    con = sqlite3.connect(db_path)
    (n,) = con.execute("SELECT COUNT(*) FROM edges WHERE rel='SIMILAR_TO'").fetchone()
    con.close()
    return int(n)


def eval_metrics(
    retrieved_ids: list[str], expected_ids: tuple[str, ...], k: int
) -> tuple[int, float, float, float]:
    """Compute hits, Recall@k, MRR@k, nDCG@k for binary relevance."""
    rel = set(expected_ids)
    top = retrieved_ids[:k]

    hits = sum(1 for nid in top if nid in rel)
    recall = hits / max(len(rel), 1)

    rr = 0.0
    for idx, nid in enumerate(top, start=1):
        if nid in rel:
            rr = 1.0 / idx
            break

    dcg = 0.0
    for idx, nid in enumerate(top, start=1):
        if nid in rel:
            dcg += 1.0 / math.log2(idx + 1)

    ideal_hits = min(len(rel), len(top))
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    ndcg = (dcg / idcg) if idcg > 0 else 0.0

    return (hits, recall, rr, ndcg)


def write_outputs(
    out_prefix: Path,
    eval_rows: list[EvalRow],
    book_rows: list[ConditionBookRow],
    summaries: list[ConditionSummary],
    recommendation: dict,
    meta: dict,
) -> tuple[Path, Path, Path, Path]:
    """Write evaluation outputs."""
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    eval_csv = out_prefix.parent / f"{out_prefix.name}_queries_{stamp}.csv"
    cost_csv = out_prefix.parent / f"{out_prefix.name}_costs_{stamp}.csv"
    summary_csv = out_prefix.parent / f"{out_prefix.name}_summary_{stamp}.csv"
    payload_json = out_prefix.parent / f"{out_prefix.name}_{stamp}.json"

    with eval_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(eval_rows[0]).keys()))
        w.writeheader()
        for row in eval_rows:
            w.writerow(asdict(row))

    with cost_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(book_rows[0]).keys()))
        w.writeheader()
        for row in book_rows:
            w.writerow(asdict(row))

    with summary_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(summaries[0]).keys()))
        w.writeheader()
        for row in summaries:
            w.writerow(asdict(row))

    with payload_json.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": meta,
                "recommendation": recommendation,
                "condition_summaries": [asdict(s) for s in summaries],
                "condition_book_rows": [asdict(r) for r in book_rows],
                "query_rows": [asdict(r) for r in eval_rows],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    return (eval_csv, cost_csv, summary_csv, payload_json)


def main() -> None:
    """Run labeled value evaluation across conditions."""
    args = parse_args()
    conditions = parse_conditions(args.conditions)

    manifest_path = (REPO_ROOT / args.manifest).resolve()
    queries_path = (REPO_ROOT / args.queries).resolve()
    out_prefix = (REPO_ROOT / args.out_prefix).resolve()

    books = load_manifest(manifest_path)
    if args.limit_books > 0:
        books = books[: args.limit_books]

    labeled = load_labeled_queries(queries_path)
    labeled_count = sum(len(v) for v in labeled.values())
    if labeled_count == 0:
        raise SystemExit(
            "No labeled queries found. Fill query_text and expected_node_ids in the query template first."
        )

    from doc_kg.kg import DocKG  # pylint: disable=import-outside-toplevel
    from doc_kg.store import DEFAULT_RELS  # pylint: disable=import-outside-toplevel

    rels_without = tuple(r for r in DEFAULT_RELS if r != "SIMILAR_TO")
    rels_with = tuple(DEFAULT_RELS)

    eval_rows: list[EvalRow] = []
    book_rows: list[ConditionBookRow] = []

    print(f"Books (manifest): {len(books)}")
    print(f"Conditions      : {conditions}")
    print(f"Labeled queries : {labeled_count}")

    for idx, b in enumerate(books, start=1):
        qset = labeled.get(b.book_relpath, [])
        if not qset:
            continue

        book_dir = (REPO_ROOT / b.book_relpath).resolve()
        if not book_dir.is_dir():
            print(f"[{idx}/{len(books)}] SKIP missing {b.book_relpath}")
            continue

        print(f"[{idx}/{len(books)}] {b.genre} :: {b.book_name} ({len(qset)} labeled queries)")
        kg = DocKG(book_dir)
        db = kg.db_path
        if not db.exists():
            print("  SKIP no graph DB")
            kg.close()
            continue

        cache = db.parent / "embeddings_value_eval.json"
        t_cache = time.perf_counter()
        kg.build_embeddings(out=cache, n_workers=args.n_workers)
        print(f"  cache built in {time.perf_counter() - t_cache:.1f}s")

        for cond in conditions:
            clear_similar_edges(kg)

            if cond == "none":
                rels = rels_without
                t_build = time.perf_counter()
                kg.build_index_from_cache(
                    cache,
                    wipe=True,
                    discover_similar=False,
                    similar_k=args.similar_k,
                    similarity_edge_threshold=args.threshold,
                    similar_max_degree=0,
                )
                build_s = time.perf_counter() - t_build
                sim_edges = count_similar_edges(db)
            else:
                cap = int(cond)
                rels = rels_with
                t_build = time.perf_counter()
                kg.build_index_from_cache(
                    cache,
                    wipe=True,
                    discover_similar=True,
                    similar_k=args.similar_k,
                    similarity_edge_threshold=args.threshold,
                    similar_max_degree=cap,
                )
                build_s = time.perf_counter() - t_build
                sim_edges = count_similar_edges(db)

            book_rows.append(
                ConditionBookRow(
                    condition=cond,
                    genre=b.genre,
                    size_tier=b.size_tier,
                    book_name=b.book_name,
                    book_relpath=b.book_relpath,
                    build_seconds=round(build_s, 6),
                    similar_edges=sim_edges,
                )
            )
            print(f"  cond={cond:<5} build={build_s:.2f}s sim_edges={sim_edges:,}")

            for q in qset:
                t_q = time.perf_counter()
                qr = kg.query(
                    q.query_text,
                    k=args.k,
                    hop=args.hop,
                    rels=rels,
                    max_nodes=args.max_nodes,
                )
                q_s = time.perf_counter() - t_q

                retrieved = [str(n.get("id", "")) for n in getattr(qr, "nodes", [])]
                hits, recall, rr, ndcg = eval_metrics(retrieved, q.expected_ids, args.max_nodes)

                eval_rows.append(
                    EvalRow(
                        condition=cond,
                        genre=b.genre,
                        size_tier=b.size_tier,
                        book_name=b.book_name,
                        book_relpath=b.book_relpath,
                        query_id=q.query_id,
                        query_type=q.query_type,
                        query_text=q.query_text,
                        expected_count=len(q.expected_ids),
                        returned_count=len(retrieved),
                        hits_at_k=hits,
                        recall_at_k=round(recall, 6),
                        mrr_at_k=round(rr, 6),
                        ndcg_at_k=round(ndcg, 6),
                        query_seconds=round(q_s, 6),
                    )
                )

        cache.unlink(missing_ok=True)
        kg.close()

    if not eval_rows:
        raise SystemExit("No evaluation rows generated. Ensure books have labeled queries.")

    by_cond: dict[str, list[EvalRow]] = defaultdict(list)
    for r in eval_rows:
        by_cond[r.condition].append(r)

    cost_by_cond: dict[str, list[ConditionBookRow]] = defaultdict(list)
    for r in book_rows:
        cost_by_cond[r.condition].append(r)

    summaries: list[ConditionSummary] = []
    for cond in conditions:
        rr = by_cond.get(cond, [])
        cc = cost_by_cond.get(cond, [])
        if not rr:
            continue
        n = len(rr)
        summaries.append(
            ConditionSummary(
                condition=cond,
                n_queries=n,
                mean_recall_at_k=round(sum(x.recall_at_k for x in rr) / n, 6),
                mean_mrr_at_k=round(sum(x.mrr_at_k for x in rr) / n, 6),
                mean_ndcg_at_k=round(sum(x.ndcg_at_k for x in rr) / n, 6),
                mean_query_seconds=round(sum(x.query_seconds for x in rr) / n, 6),
                mean_build_seconds=round(
                    (sum(x.build_seconds for x in cc) / len(cc)) if cc else 0.0,
                    6,
                ),
                mean_similar_edges=round(
                    (sum(x.similar_edges for x in cc) / len(cc)) if cc else 0.0,
                    6,
                ),
            )
        )

    smap = {s.condition: s for s in summaries}
    baseline = smap.get("none")
    recommendation: dict[str, object] = {
        "baseline": "none",
        "best_condition": None,
        "notes": [],
    }

    if baseline is not None:
        best = None
        best_score = -1e9
        for s in summaries:
            if s.condition == "none":
                continue
            delta_mrr = s.mean_mrr_at_k - baseline.mean_mrr_at_k
            delta_ndcg = s.mean_ndcg_at_k - baseline.mean_ndcg_at_k
            edge_cost = max(s.mean_similar_edges, 1.0)
            utility = (delta_mrr + delta_ndcg) / edge_cost
            score = utility
            if score > best_score:
                best_score = score
                best = (s, delta_mrr, delta_ndcg, utility)

        if best is not None:
            s, delta_mrr, delta_ndcg, utility = best
            recommendation["best_condition"] = s.condition
            recommendation["best_delta_mrr"] = round(delta_mrr, 6)
            recommendation["best_delta_ndcg"] = round(delta_ndcg, 6)
            recommendation["best_utility_per_edge"] = round(utility, 10)

            # Simple adoption heuristic; tighten once you have larger labeled sets.
            rel_gain_mrr = (
                (s.mean_mrr_at_k / baseline.mean_mrr_at_k - 1.0)
                if baseline.mean_mrr_at_k > 0
                else 0.0
            )
            rel_gain_ndcg = (
                (s.mean_ndcg_at_k / baseline.mean_ndcg_at_k - 1.0)
                if baseline.mean_ndcg_at_k > 0
                else 0.0
            )
            recommendation["relative_gain_mrr"] = round(rel_gain_mrr, 6)
            recommendation["relative_gain_ndcg"] = round(rel_gain_ndcg, 6)

            if rel_gain_mrr >= 0.05 or rel_gain_ndcg >= 0.05:
                recommendation["adopt_default"] = True
                recommendation["notes"].append(
                    "Quality gain threshold met against no-SIMILAR baseline."
                )
            else:
                recommendation["adopt_default"] = False
                recommendation["notes"].append(
                    "No strong quality gain vs baseline; keep SIMILAR optional."
                )

    meta = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "queries": str(queries_path),
        "conditions": conditions,
        "k": args.k,
        "hop": args.hop,
        "max_nodes": args.max_nodes,
        "similar_k": args.similar_k,
        "threshold": args.threshold,
        "books_with_labels": len({r.book_relpath for r in eval_rows}),
        "query_rows": len(eval_rows),
    }

    eval_csv, cost_csv, summary_csv, payload_json = write_outputs(
        out_prefix,
        eval_rows,
        book_rows,
        summaries,
        recommendation,
        meta,
    )

    print("\nCondition summary:")
    for s in summaries:
        print(
            f"  {s.condition:<5} MRR={s.mean_mrr_at_k:.4f} nDCG={s.mean_ndcg_at_k:.4f} "
            f"Recall={s.mean_recall_at_k:.4f} build={s.mean_build_seconds:.2f}s "
            f"edges={s.mean_similar_edges:,.0f}"
        )

    print("\nRecommendation:")
    print(json.dumps(recommendation, indent=2))

    print("\nWrote:")
    print(f"  - {eval_csv}")
    print(f"  - {cost_csv}")
    print(f"  - {summary_csv}")
    print(f"  - {payload_json}")


if __name__ == "__main__":
    main()
