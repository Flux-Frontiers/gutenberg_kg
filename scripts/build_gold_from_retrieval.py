#!/usr/bin/env python3
"""Build gold-set expected_node_ids by running retrieval and validating results.

Flips the gold-set construction order: retrieval runs first, a human marks
which returned chunk nodes are actually relevant, and those become the
expected_node_ids written back to the query template CSV.

For each query the script:

1. Embeds the book once and builds indices for two conditions:
   - BASE (no SIMILAR_TO)
   - SIM  (SIMILAR_TO cap 8)
2. Pools the returned chunk nodes from both conditions.
3. Prints each candidate chunk with its text and a [BASE] / [SIM] / [BOTH] tag
   so you can see what SIMILAR_TO uniquely contributes.
4. Prompts y / n / s (skip) for each candidate.
5. Writes validated IDs back to the template CSV after every query.

Queries that already have expected_node_ids filled are skipped unless --force
is passed.

Usage:

    poetry run python scripts/build_gold_from_retrieval.py

    poetry run python scripts/build_gold_from_retrieval.py --force
    poetry run python scripts/build_gold_from_retrieval.py --query-ids Q0001,Q0014
    poetry run python scripts/build_gold_from_retrieval.py --limit-books 2
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
QUERIES_PATH = REPO_ROOT / "analysis/similar_to_query_template.csv"
SIM_CAP = 8
SIM_K = 5
SIM_THRESHOLD = 0.85
QUERY_K = 8
QUERY_HOP = 1
QUERY_MAX_NODES = 15


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--queries",
        default=str(QUERIES_PATH),
        help="Query template CSV path.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-validate queries that already have expected_node_ids.",
    )
    p.add_argument(
        "--query-ids",
        default="",
        help="Comma-separated query IDs to process (default: all unfilled).",
    )
    p.add_argument(
        "--limit-books",
        type=int,
        default=0,
        help="Stop after this many distinct books (0 = all).",
    )
    p.add_argument(
        "--sim-cap",
        type=int,
        default=SIM_CAP,
        help="SIMILAR_TO degree cap for the SIM condition.",
    )
    p.add_argument(
        "--n-workers",
        type=int,
        default=4,
        help="Embedding worker count.",
    )
    return p.parse_args()


def load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def clear_similar_edges(kg: object) -> None:
    con = getattr(getattr(kg, "store"), "con")
    con.execute("DELETE FROM edges WHERE rel='SIMILAR_TO'")
    con.commit()


def run_query_chunks(kg, query_text: str, rels: tuple) -> list[tuple[str, str]]:
    """Return (chunk_id, chunk_text) for chunk nodes returned by kg.query."""
    result = kg.query(
        query_text,
        k=QUERY_K,
        hop=QUERY_HOP,
        rels=rels,
        max_nodes=QUERY_MAX_NODES,
    )
    out = []
    for n in getattr(result, "nodes", []):
        if n.get("kind") == "chunk":
            out.append((str(n.get("id", "")), str(n.get("text", "") or "")))
    return out


def prompt_yn(prompt: str) -> str:
    """Return 'y', 'n', 's' (skip), or 'q' (quit)."""
    while True:
        try:
            ans = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "q"
        if ans in ("y", "n", "s", "q", "yes", "no", "skip", "quit"):
            return ans[0]
        print("  Enter y / n / s (skip) / q (quit)")


def validate_book(
    rows_for_book: list[dict],
    rows_all: list[dict],
    book_relpath: str,
    args: argparse.Namespace,
    queries_path: Path,
) -> bool:
    """Return True if the user requested a full quit, False otherwise."""
    from doc_kg.kg import DocKG  # pylint: disable=import-outside-toplevel
    from doc_kg.store import DEFAULT_RELS  # pylint: disable=import-outside-toplevel

    rels_base = tuple(r for r in DEFAULT_RELS if r != "SIMILAR_TO")
    rels_sim = tuple(DEFAULT_RELS)

    book_dir = (REPO_ROOT / book_relpath).resolve()
    kg = DocKG(book_dir)
    db = kg.db_path
    if not db.exists():
        print(f"  SKIP — no graph DB at {db}")
        kg.close()
        return False

    cache = db.parent / "embeddings_gold_build.json"
    print("  Building embeddings … ", end="", flush=True)
    t0 = time.perf_counter()
    kg.build_embeddings(out=cache, n_workers=args.n_workers, quiet=True)
    print(f"{time.perf_counter() - t0:.1f}s")

    for row in rows_for_book:
        qid = row["query_id"]
        qtext = row.get("query_text", "").strip()
        if not qtext:
            print(f"\n  [{qid}] SKIP — no query_text")
            continue

        already_filled = bool(row.get("expected_node_ids", "").strip())
        if already_filled and not args.force:
            print(f"\n  [{qid}] already filled — skipping (use --force to re-validate)")
            continue

        print(f"\n{'─' * 70}")
        print(f"  [{qid}]  {row.get('query_type', '')}  /  {row.get('book_name', '')}")
        print(f"  Q: {qtext}")
        print()

        # Build BASE index
        clear_similar_edges(kg)
        kg.build_index_from_cache(
            cache,
            wipe=True,
            discover_similar=False,
            similar_k=SIM_K,
            similarity_edge_threshold=SIM_THRESHOLD,
            similar_max_degree=0,
        )
        base_chunks = run_query_chunks(kg, qtext, rels_base)
        base_ids = {cid for cid, _ in base_chunks}

        # Build SIM index
        clear_similar_edges(kg)
        kg.build_index_from_cache(
            cache,
            wipe=True,
            discover_similar=True,
            similar_k=SIM_K,
            similarity_edge_threshold=SIM_THRESHOLD,
            similar_max_degree=args.sim_cap,
        )
        sim_chunks = run_query_chunks(kg, qtext, rels_sim)
        sim_ids = {cid for cid, _ in sim_chunks}

        # Union of candidates, preserving BASE order then SIM-only additions
        seen: set[str] = set()
        candidates: list[tuple[str, str, str]] = []  # (id, text, tag)
        for cid, txt in base_chunks:
            if cid not in seen:
                tag = "BOTH" if cid in sim_ids else "BASE"
                candidates.append((cid, txt, tag))
                seen.add(cid)
        for cid, txt in sim_chunks:
            if cid not in seen:
                candidates.append((cid, txt, "SIM "))
                seen.add(cid)

        if not candidates:
            print("  No chunk nodes returned by either condition — skipping.")
            continue

        user_quit = False

        print(
            f"  {len(candidates)} candidate chunk(s) to review "
            f"(BASE={len(base_ids)}  SIM={len(sim_ids)}  "
            f"SIM-only={len(sim_ids - base_ids)}):\n"
        )

        approved: list[str] = []

        for i, (cid, txt, tag) in enumerate(candidates, start=1):
            print(f"  ┌─ [{tag}] chunk {i}/{len(candidates)} ─────────────────────────────")
            print(f"  │  Q: {qtext}")
            print(f"  │  ID: {cid}")
            print("  └─────────────────────────────────────────────────────────────")
            # Print full chunk text, wrapped at 72 chars
            for line in txt.strip().splitlines():
                line = line.strip()
                while len(line) > 72:
                    print(f"     {line[:72]}")
                    line = line[72:]
                if line:
                    print(f"     {line}")
            print()
            ans = prompt_yn("  Relevant? [y/n/s/q] → ")
            if ans == "q":
                user_quit = True
                break
            if ans == "y":
                approved.append(cid)
            print()

        # Always save the current query before propagating quit
        expected = "|".join(approved)
        for r in rows_all:
            if r["query_id"] == qid:
                r["expected_node_ids"] = expected
                r["assessor"] = "human"
                break
        save_rows(queries_path, rows_all)
        print(f"  → saved {len(approved)} id(s) for {qid}")

        if user_quit:
            print("\nQuitting — progress saved.")
            cache.unlink(missing_ok=True)
            kg.close()
            return True

    cache.unlink(missing_ok=True)
    kg.close()
    return False


def main() -> None:
    args = parse_args()
    queries_path = Path(args.queries)
    rows = load_rows(queries_path)

    filter_ids: set[str] = set()
    if args.query_ids:
        filter_ids = {x.strip() for x in args.query_ids.split(",") if x.strip()}

    # Group rows by book_relpath preserving order
    from collections import OrderedDict

    books: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        rp = row.get("book_relpath", "").strip()
        if not rp:
            continue
        if filter_ids and row["query_id"] not in filter_ids:
            continue
        already = bool(row.get("expected_node_ids", "").strip())
        if already and not args.force and not filter_ids:
            continue
        books.setdefault(rp, []).append(row)

    if not books:
        print("Nothing to validate — all rows already filled. Use --force to redo.")
        return

    total_q = sum(len(v) for v in books.values())
    print(f"Books to process : {len(books)}")
    print(f"Queries to review: {total_q}")

    books_done = 0
    for book_relpath, book_rows in books.items():
        book_name = book_rows[0].get("book_name", book_relpath)
        print(f"\n{'═' * 70}")
        print(f"Book [{books_done + 1}/{len(books)}]: {book_name}")
        quit_requested = validate_book(book_rows, rows, book_relpath, args, queries_path)
        books_done += 1
        if quit_requested:
            break
        if args.limit_books and books_done >= args.limit_books:
            print("\nReached --limit-books cap.")
            break

    print("\nDone.")


if __name__ == "__main__":
    main()
