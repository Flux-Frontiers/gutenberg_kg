#!/usr/bin/env python3
"""Run retrieval A/B comparisons for SIMILAR_TO caps.

Compares retrieval behavior for selected caps (default: 8 and 15) with:

1. SIMILAR_TO traversal disabled in query expansion rels.
2. SIMILAR_TO traversal enabled in query expansion rels.

Per book workflow:

1. Build one embedding cache.
2. Rebuild SIMILAR_TO edges for each cap.
3. Execute per-book query set in both traversal modes.
4. Emit summary and per-query results under analysis/.

Usage:

    poetry run python scripts/run_retrieval_cap_ab.py

    poetry run python scripts/run_retrieval_cap_ab.py \
      --caps 8,15 \
      --limit-books 4 \
      --k 8 --hop 1 --max-nodes 15
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


FALLBACK_BY_TYPE: dict[str, str] = {
    "factual_entity": "Identify the main people, places, or entities and their roles.",
    "thematic_semantic": "What major themes and ideas are developed in this text?",
    "cross_chunk_context": "Connect early events to later outcomes and explain their relationship.",
}


@dataclass(frozen=True)
class BookSpec:
    """Book selection entry loaded from the manifest."""

    genre: str
    book_name: str
    book_relpath: str
    size_tier: str


@dataclass(frozen=True)
class QuerySpec:
    """One query case tied to a specific book."""

    query_id: str
    query_type: str
    book_relpath: str
    query_text: str


@dataclass(frozen=True)
class QueryRow:
    """Per-query A/B metric row."""

    genre: str
    size_tier: str
    book_name: str
    book_relpath: str
    cap: int
    mode: str
    query_id: str
    query_type: str
    query_text: str
    k: int
    hop: int
    max_nodes: int
    query_seconds: float
    returned_nodes: int
    unique_node_ratio: float
    unique_file_ratio: float
    similar_edge_fraction: float


@dataclass(frozen=True)
class SummaryRow:
    """Aggregated metrics by book × cap × mode."""

    genre: str
    size_tier: str
    book_name: str
    book_relpath: str
    cap: int
    mode: str
    n_queries: int
    mean_query_seconds: float
    mean_returned_nodes: float
    mean_unique_node_ratio: float
    mean_unique_file_ratio: float
    mean_similar_edge_fraction: float


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--manifest",
        default="analysis/similar_to_book_manifest.csv",
        help="Book manifest CSV relative to repo root.",
    )
    p.add_argument(
        "--queries",
        default="analysis/similar_to_query_template.csv",
        help="Query template CSV relative to repo root.",
    )
    p.add_argument(
        "--caps",
        default="8,15",
        help="Comma-separated cap values for A/B comparison.",
    )
    p.add_argument("--similar-k", type=int, default=5, help="similar_k for edge build.")
    p.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="similarity_edge_threshold for edge build.",
    )
    p.add_argument("--k", type=int, default=8, help="Query seed count.")
    p.add_argument("--hop", type=int, default=1, help="Query expansion hop count.")
    p.add_argument("--max-nodes", type=int, default=15, help="Max nodes returned per query.")
    p.add_argument("--n-workers", type=int, default=4, help="Embedding cache worker count.")
    p.add_argument(
        "--limit-books",
        type=int,
        default=0,
        help="Limit number of books for quick runs (0=all).",
    )
    p.add_argument(
        "--out-prefix",
        default="analysis/similar_to_retrieval_ab",
        help="Output file prefix relative to repo root.",
    )
    return p.parse_args()


def parse_caps(raw: str) -> list[int]:
    """Parse and validate cap list."""
    vals = [int(x.strip()) for x in raw.split(",") if x.strip()]
    if not vals:
        raise ValueError("No cap values provided")
    if any(v < 0 for v in vals):
        raise ValueError("Cap values must be >= 0")
    return sorted(set(vals))


def load_manifest(path: Path) -> list[BookSpec]:
    """Load books from manifest."""
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


def load_queries(path: Path) -> dict[str, list[QuerySpec]]:
    """Load query specs grouped by book path.

    If query_text is blank, uses fallback text based on query_type.
    """
    grouped: dict[str, list[QuerySpec]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            relpath = (r.get("book_relpath") or "").strip()
            if not relpath:
                continue
            qtype = (r.get("query_type") or "").strip() or "thematic_semantic"
            qtext = (r.get("query_text") or "").strip()
            if not qtext:
                qtext = FALLBACK_BY_TYPE.get(qtype, FALLBACK_BY_TYPE["thematic_semantic"])
            qid = (r.get("query_id") or "").strip() or f"{relpath}:{qtype}"
            grouped[relpath].append(
                QuerySpec(
                    query_id=qid,
                    query_type=qtype,
                    book_relpath=relpath,
                    query_text=qtext,
                )
            )
    return grouped


def clear_similar_edges(kg: object) -> None:
    """Remove all SIMILAR_TO edges for fair cap rebuild.

    Uses the active GraphStore connection to avoid cross-connection lock churn.
    """
    store = getattr(kg, "store")
    con = store.con
    con.execute("DELETE FROM edges WHERE rel='SIMILAR_TO'")
    con.commit()


def compute_query_metrics(
    qr: object, elapsed: float, max_nodes: int
) -> tuple[int, float, float, float]:
    """Compute query-level proxy metrics from a QueryResult.

    Returns:
    1. returned_nodes
    2. unique_node_ratio
    3. unique_file_ratio
    4. similar_edge_fraction
    """
    nodes = list(getattr(qr, "nodes", []))
    edges = list(getattr(qr, "edges", []))
    top = nodes[:max_nodes]

    if not top:
        return (0, 0.0, 0.0, 0.0)

    ids = [str(n.get("id", "")) for n in top]
    files = [str(n.get("file_path", "")) for n in top if n.get("file_path")]

    unique_node_ratio = len(set(ids)) / max(len(ids), 1)
    unique_file_ratio = len(set(files)) / max(len(ids), 1)

    if not edges:
        similar_edge_fraction = 0.0
    else:
        similar = sum(1 for e in edges if str(e.get("rel", "")) == "SIMILAR_TO")
        similar_edge_fraction = similar / len(edges)

    _ = elapsed  # kept in signature for clarity
    return (len(nodes), unique_node_ratio, unique_file_ratio, similar_edge_fraction)


def write_outputs(
    out_prefix: Path,
    summary_rows: list[SummaryRow],
    query_rows: list[QueryRow],
    meta: dict,
) -> tuple[Path, Path, Path]:
    """Write summary CSV, query CSV, and JSON bundle."""
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    summary_csv = out_prefix.parent / f"{out_prefix.name}_summary_{stamp}.csv"
    query_csv = out_prefix.parent / f"{out_prefix.name}_queries_{stamp}.csv"
    payload_json = out_prefix.parent / f"{out_prefix.name}_{stamp}.json"

    with summary_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(summary_rows[0]).keys()))
        w.writeheader()
        for row in summary_rows:
            w.writerow(asdict(row))

    with query_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(query_rows[0]).keys()))
        w.writeheader()
        for row in query_rows:
            w.writerow(asdict(row))

    with payload_json.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": meta,
                "summary_rows": [asdict(r) for r in summary_rows],
                "query_rows": [asdict(r) for r in query_rows],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    return (summary_csv, query_csv, payload_json)


def main() -> None:
    """Run retrieval A/B for selected caps and write outputs."""
    args = parse_args()
    caps = parse_caps(args.caps)

    manifest_path = (REPO_ROOT / args.manifest).resolve()
    queries_path = (REPO_ROOT / args.queries).resolve()
    out_prefix = (REPO_ROOT / args.out_prefix).resolve()

    books = load_manifest(manifest_path)
    if args.limit_books > 0:
        books = books[: args.limit_books]
    if not books:
        raise SystemExit("No books selected")

    queries_by_book = load_queries(queries_path)

    from doc_kg.kg import DocKG  # pylint: disable=import-outside-toplevel
    from doc_kg.store import DEFAULT_RELS  # pylint: disable=import-outside-toplevel

    rels_with = tuple(DEFAULT_RELS)
    rels_without = tuple(r for r in DEFAULT_RELS if r != "SIMILAR_TO")

    print(f"Books    : {len(books)}")
    print(f"Caps     : {caps}")
    print(f"Manifest : {manifest_path}")
    print(f"Queries  : {queries_path}")

    query_rows: list[QueryRow] = []

    for idx, spec in enumerate(books, start=1):
        book_dir = (REPO_ROOT / spec.book_relpath).resolve()
        if not book_dir.is_dir():
            print(f"\n[{idx}/{len(books)}] SKIP missing {spec.book_relpath}")
            continue

        queries = queries_by_book.get(spec.book_relpath, [])
        if not queries:
            # Fallback to three generic query types if template has no rows for this book.
            queries = [
                QuerySpec(
                    query_id=f"{spec.book_relpath}:factual_entity",
                    query_type="factual_entity",
                    book_relpath=spec.book_relpath,
                    query_text=FALLBACK_BY_TYPE["factual_entity"],
                ),
                QuerySpec(
                    query_id=f"{spec.book_relpath}:thematic_semantic",
                    query_type="thematic_semantic",
                    book_relpath=spec.book_relpath,
                    query_text=FALLBACK_BY_TYPE["thematic_semantic"],
                ),
                QuerySpec(
                    query_id=f"{spec.book_relpath}:cross_chunk_context",
                    query_type="cross_chunk_context",
                    book_relpath=spec.book_relpath,
                    query_text=FALLBACK_BY_TYPE["cross_chunk_context"],
                ),
            ]

        print(f"\n[{idx}/{len(books)}] {spec.genre} :: {spec.book_name} ({len(queries)} queries)")
        kg = DocKG(book_dir)
        db = kg.db_path
        if not db.exists():
            print(f"  SKIP no graph DB: {db}")
            kg.close()
            continue

        cache = db.parent / "embeddings_retrieval_ab.json"
        t0 = time.perf_counter()
        kg.build_embeddings(out=cache, n_workers=args.n_workers)
        print(f"  Cache built in {time.perf_counter() - t0:.1f}s")

        for cap in caps:
            clear_similar_edges(kg)
            t_build = time.perf_counter()
            kg.build_index_from_cache(
                cache,
                wipe=True,
                similar_k=args.similar_k,
                similarity_edge_threshold=args.threshold,
                similar_max_degree=cap,
            )
            build_s = time.perf_counter() - t_build
            print(f"  cap={cap:<3} built in {build_s:.1f}s")

            for mode, rels in (
                ("without_similar", rels_without),
                ("with_similar", rels_with),
            ):
                mode_times: list[float] = []
                for q in queries:
                    t_q = time.perf_counter()
                    qr = kg.query(
                        q.query_text,
                        k=args.k,
                        hop=args.hop,
                        rels=rels,
                        max_nodes=args.max_nodes,
                    )
                    q_s = time.perf_counter() - t_q
                    mode_times.append(q_s)

                    returned, uniq_nodes, uniq_files, sim_frac = compute_query_metrics(
                        qr,
                        q_s,
                        args.max_nodes,
                    )

                    query_rows.append(
                        QueryRow(
                            genre=spec.genre,
                            size_tier=spec.size_tier,
                            book_name=spec.book_name,
                            book_relpath=spec.book_relpath,
                            cap=cap,
                            mode=mode,
                            query_id=q.query_id,
                            query_type=q.query_type,
                            query_text=q.query_text,
                            k=args.k,
                            hop=args.hop,
                            max_nodes=args.max_nodes,
                            query_seconds=round(q_s, 6),
                            returned_nodes=returned,
                            unique_node_ratio=round(uniq_nodes, 6),
                            unique_file_ratio=round(uniq_files, 6),
                            similar_edge_fraction=round(sim_frac, 6),
                        )
                    )

                mean_q_s = sum(mode_times) / max(len(mode_times), 1)
                print(f"    mode={mode:<15} mean_query={mean_q_s:.3f}s")

        cache.unlink(missing_ok=True)
        kg.close()

    if not query_rows:
        raise SystemExit("No query rows produced")

    grouped: dict[tuple[str, str, str, str, int, str], list[QueryRow]] = defaultdict(list)
    for r in query_rows:
        key = (r.genre, r.size_tier, r.book_name, r.book_relpath, r.cap, r.mode)
        grouped[key].append(r)

    summary_rows: list[SummaryRow] = []
    for (genre, tier, name, relpath, cap, mode), rr in grouped.items():
        n = len(rr)
        summary_rows.append(
            SummaryRow(
                genre=genre,
                size_tier=tier,
                book_name=name,
                book_relpath=relpath,
                cap=cap,
                mode=mode,
                n_queries=n,
                mean_query_seconds=round(sum(x.query_seconds for x in rr) / n, 6),
                mean_returned_nodes=round(sum(x.returned_nodes for x in rr) / n, 6),
                mean_unique_node_ratio=round(sum(x.unique_node_ratio for x in rr) / n, 6),
                mean_unique_file_ratio=round(sum(x.unique_file_ratio for x in rr) / n, 6),
                mean_similar_edge_fraction=round(
                    sum(x.similar_edge_fraction for x in rr) / n,
                    6,
                ),
            )
        )

    summary_rows.sort(key=lambda r: (r.book_relpath, r.cap, r.mode))

    meta = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "queries": str(queries_path),
        "caps": caps,
        "k": args.k,
        "hop": args.hop,
        "max_nodes": args.max_nodes,
        "similar_k": args.similar_k,
        "threshold": args.threshold,
        "books_processed": len({r.book_relpath for r in query_rows}),
        "query_rows": len(query_rows),
    }

    summary_csv, query_csv, payload_json = write_outputs(out_prefix, summary_rows, query_rows, meta)
    print("\nWrote:")
    print(f"  - {summary_csv}")
    print(f"  - {query_csv}")
    print(f"  - {payload_json}")


if __name__ == "__main__":
    main()
