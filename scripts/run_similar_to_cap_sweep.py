#!/usr/bin/env python3
"""Run a SIMILAR_TO cap sweep over books listed in a manifest CSV.

This script automates the cap matrix for analysis planning:

1. Reads sampled books from analysis/similar_to_book_manifest.csv.
2. Builds one embedding cache per book.
3. Rebuilds index from cache for each cap in the sweep.
4. Records graph density, hub metrics, and runtime per run.
5. Writes results to analysis/ as CSV and JSON.

Usage:

    poetry run python scripts/run_similar_to_cap_sweep.py

    poetry run python scripts/run_similar_to_cap_sweep.py \
      --caps 0,4,8,10,15,20 \
      --similar-k 5 \
      --threshold 0.85

    # Quick smoke run (one book)
    poetry run python scripts/run_similar_to_cap_sweep.py --limit-books 1 --caps 0,10
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BookSpec:
    """Book selection entry loaded from the manifest.

    :param genre: Genre name from manifest.
    :param book_name: Book directory name.
    :param book_relpath: Path relative to repo root.
    :param size_tier: short, medium, long.
    """

    genre: str
    book_name: str
    book_relpath: str
    size_tier: str


@dataclass(frozen=True)
class SweepRow:
    """One cap-run result row."""

    genre: str
    size_tier: str
    book_name: str
    book_relpath: str
    cap: int
    similar_k: int
    threshold: float
    nodes: int
    similar_edges: int
    similar_edges_added: int | None
    max_total_degree: int
    max_total_degree_node: str
    max_out_degree: int
    max_out_degree_node: str
    elapsed_seconds: float
    edge_reduction_vs_cap0_pct: float | None


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--manifest",
        default="analysis/similar_to_book_manifest.csv",
        help="Manifest CSV path relative to repo root.",
    )
    p.add_argument(
        "--caps",
        default="0,2,4,6,8,10,15,20,30,50",
        help="Comma-separated similar_max_degree values.",
    )
    p.add_argument(
        "--similar-k",
        type=int,
        default=5,
        help="similar_k for SIMILAR_TO scan (default: 5).",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="similarity_edge_threshold (default: 0.85).",
    )
    p.add_argument(
        "--n-workers",
        type=int,
        default=4,
        help="Worker count for embedding cache build (default: 4).",
    )
    p.add_argument(
        "--limit-books",
        type=int,
        default=0,
        help="Limit number of books from manifest for quick runs (0=all).",
    )
    p.add_argument(
        "--out-prefix",
        default="analysis/similar_to_cap_sweep",
        help="Output path prefix relative to repo root; timestamp and extension are appended.",
    )
    return p.parse_args()


def parse_caps(raw: str) -> list[int]:
    """Parse and validate comma-separated cap values."""
    vals = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        vals.append(int(part))
    if not vals:
        raise ValueError("No cap values provided")
    if any(v < 0 for v in vals):
        raise ValueError("Cap values must be >= 0")
    return sorted(set(vals))


def load_manifest(path: Path) -> list[BookSpec]:
    """Load book specs from CSV manifest."""
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    books: list[BookSpec] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"genre", "book_name", "book_relpath", "size_tier"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Manifest missing columns: {sorted(missing)}")

        for row in reader:
            books.append(
                BookSpec(
                    genre=(row.get("genre") or "").strip(),
                    book_name=(row.get("book_name") or "").strip(),
                    book_relpath=(row.get("book_relpath") or "").strip(),
                    size_tier=(row.get("size_tier") or "").strip(),
                )
            )
    return books


def clear_similar_edges(db_path: Path) -> None:
    """Delete all SIMILAR_TO edges before each cap run for fair comparison."""
    con = sqlite3.connect(db_path)
    con.execute("DELETE FROM edges WHERE rel='SIMILAR_TO'")
    con.commit()
    con.close()


def count_nodes(db_path: Path) -> int:
    """Count all nodes in graph DB."""
    con = sqlite3.connect(db_path)
    (n,) = con.execute("SELECT COUNT(*) FROM nodes").fetchone()
    con.close()
    return int(n)


def count_similar_edges(db_path: Path) -> int:
    """Count SIMILAR_TO edges in graph DB."""
    con = sqlite3.connect(db_path)
    (n,) = con.execute("SELECT COUNT(*) FROM edges WHERE rel='SIMILAR_TO'").fetchone()
    con.close()
    return int(n)


def max_total_degree(db_path: Path) -> tuple[int, str]:
    """Return (degree, node_id) for highest total SIMILAR_TO degree."""
    con = sqlite3.connect(db_path)
    row = con.execute("""
        SELECT node_id, COUNT(*) AS deg FROM (
            SELECT src AS node_id FROM edges WHERE rel='SIMILAR_TO'
            UNION ALL
            SELECT dst AS node_id FROM edges WHERE rel='SIMILAR_TO'
        )
        GROUP BY node_id
        ORDER BY deg DESC
        LIMIT 1
        """).fetchone()
    con.close()
    if not row:
        return (0, "")
    return (int(row[1]), str(row[0]))


def max_out_degree(db_path: Path) -> tuple[int, str]:
    """Return (degree, node_id) for highest SIMILAR_TO out-degree."""
    con = sqlite3.connect(db_path)
    row = con.execute("""
        SELECT src AS node_id, COUNT(*) AS out_deg
        FROM edges
        WHERE rel='SIMILAR_TO'
        GROUP BY src
        ORDER BY out_deg DESC
        LIMIT 1
        """).fetchone()
    con.close()
    if not row:
        return (0, "")
    return (int(row[1]), str(row[0]))


def write_outputs(rows: list[SweepRow], out_prefix: Path, meta: dict) -> tuple[Path, Path]:
    """Write CSV and JSON outputs for sweep results."""
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    csv_path = out_prefix.parent / f"{out_prefix.name}_{stamp}.csv"
    json_path = out_prefix.parent / f"{out_prefix.name}_{stamp}.json"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    payload = {
        "meta": meta,
        "rows": [asdict(r) for r in rows],
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return (csv_path, json_path)


def main() -> None:
    """Run the cap sweep and persist results."""
    args = parse_args()
    caps = parse_caps(args.caps)
    manifest_path = (REPO_ROOT / args.manifest).resolve()
    out_prefix = (REPO_ROOT / args.out_prefix).resolve()

    books = load_manifest(manifest_path)
    if args.limit_books > 0:
        books = books[: args.limit_books]

    if not books:
        raise SystemExit("No books to process")

    from doc_kg.kg import DocKG  # pylint: disable=import-outside-toplevel

    print(f"Manifest : {manifest_path}")
    print(f"Books    : {len(books)}")
    print(f"Caps     : {caps}")
    print(f"similar_k: {args.similar_k}")
    print(f"threshold: {args.threshold}")

    all_rows: list[SweepRow] = []

    for idx, spec in enumerate(books, start=1):
        book_dir = (REPO_ROOT / spec.book_relpath).resolve()
        if not book_dir.is_dir():
            print(f"\n[{idx}/{len(books)}] SKIP missing: {spec.book_relpath}")
            continue

        print(f"\n[{idx}/{len(books)}] {spec.genre} :: {spec.book_name}")
        kg = DocKG(book_dir)
        db = kg.db_path
        cache = db.parent / "embeddings_cap_sweep.json"

        if not db.exists():
            print(f"  SKIP no graph DB: {db}")
            kg.close()
            continue

        nodes = count_nodes(db)
        print(f"  Nodes: {nodes:,}")

        t0 = time.perf_counter()
        kg.build_embeddings(out=cache, n_workers=args.n_workers)
        cache_s = time.perf_counter() - t0
        print(f"  Cache built in {cache_s:.1f}s")

        cap0_edges: int | None = None

        for cap in caps:
            clear_similar_edges(db)
            t1 = time.perf_counter()
            stats = kg.build_index_from_cache(
                cache,
                wipe=True,
                similar_k=args.similar_k,
                similarity_edge_threshold=args.threshold,
                similar_max_degree=cap,
            )
            elapsed = time.perf_counter() - t1

            sim_edges = count_similar_edges(db)
            max_deg, max_node = max_total_degree(db)
            out_deg, out_node = max_out_degree(db)

            if cap == 0:
                cap0_edges = sim_edges

            reduction_pct: float | None = None
            if cap0_edges and cap0_edges > 0:
                reduction_pct = 100.0 * (1.0 - (sim_edges / cap0_edges))

            row = SweepRow(
                genre=spec.genre,
                size_tier=spec.size_tier,
                book_name=spec.book_name,
                book_relpath=spec.book_relpath,
                cap=cap,
                similar_k=args.similar_k,
                threshold=args.threshold,
                nodes=nodes,
                similar_edges=sim_edges,
                similar_edges_added=getattr(stats, "similar_edges_added", None),
                max_total_degree=max_deg,
                max_total_degree_node=max_node,
                max_out_degree=out_deg,
                max_out_degree_node=out_node,
                elapsed_seconds=round(elapsed, 4),
                edge_reduction_vs_cap0_pct=(
                    round(reduction_pct, 4) if reduction_pct is not None else None
                ),
            )
            all_rows.append(row)

            reduction_str = (
                f"{row.edge_reduction_vs_cap0_pct:.1f}%"
                if row.edge_reduction_vs_cap0_pct is not None
                else "n/a"
            )
            print(
                "  "
                f"cap={cap:<3} edges={sim_edges:<7,} "
                f"max_total={max_deg:<4} max_out={out_deg:<4} "
                f"time={elapsed:.1f}s reduction={reduction_str}"
            )

        cache.unlink(missing_ok=True)
        kg.close()

    if not all_rows:
        raise SystemExit("Sweep produced no rows")

    meta = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "books_processed": len({r.book_relpath for r in all_rows}),
        "caps": caps,
        "similar_k": args.similar_k,
        "threshold": args.threshold,
        "n_workers": args.n_workers,
    }

    csv_path, json_path = write_outputs(all_rows, out_prefix, meta)
    print("\nWrote:")
    print(f"  - {csv_path}")
    print(f"  - {json_path}")


if __name__ == "__main__":
    main()
