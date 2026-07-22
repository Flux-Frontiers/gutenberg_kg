#!/usr/bin/env python3
"""Run GutenbergKG standard chat queries against a live worker and validate hits.

Usage:
    python scripts/check_standard_queries.py
    python scripts/check_standard_queries.py --endpoint http://localhost:8000 --min-hits 1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_ENDPOINT = "http://localhost:8000"

STANDARD_QUERIES: list[tuple[str, str, tuple[str, ...]]] = [
    ("philosophy", "What is justice according to Plato?", ("The Republic",)),
    ("sacred-texts", "What does the Quran say about Moses?", ("The Quran",)),
    (
        "world-literature",
        "How does Dante describe the circles of Hell?",
        ("The Divine Comedy",),
    ),
    (
        "russian-literature",
        "How does Tolstoy portray the Napoleonic invasion?",
        ("War and Peace",),
    ),
    (
        "french-literature",
        "How did Jules Verne describe undersea exploration?",
        ("Twenty Thousand Leagues Under the Sea",),
    ),
    (
        "natural-history",
        "Describe Darwin's observations on the Galapagos",
        ("The Voyage of the Beagle",),
    ),
    (
        "ancient-classical",
        "What virtues does Seneca recommend in his dialogues?",
        ("Minor Dialogues",),
    ),
    ("diary", "What did Pepys say about the great fire?", ("Samuel Pepys",)),
]


def _has_expected_title(hits: list[dict], expected_titles: tuple[str, ...], rank: int) -> bool:
    """Return whether an expected work occurs within the leading hits.

    :param hits: Handler hit dictionaries in retrieval order.
    :param expected_titles: Case-insensitive title fragments accepted as relevant.
    :param rank: Number of leading hits to inspect.
    :returns: ``True`` when any expected fragment occurs in a leading hit title.
    """
    leading_titles = [
        str(hit.get("title") or hit.get("name") or "").casefold() for hit in hits[:rank]
    ]
    return any(
        expected.casefold() in title for expected in expected_titles for title in leading_titles
    )


def _post_runsync(endpoint: str, payload: dict) -> dict:
    body = json.dumps({"input": payload}).encode("utf-8")
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/runsync",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") == "FAILED":
        raise RuntimeError(data.get("error") or "runsync FAILED")
    return data.get("output", data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run standard GutenbergKG query checks")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Worker base URL")
    parser.add_argument("--k", type=int, default=10, help="Top-k retrieval")
    parser.add_argument("--min-score", type=float, default=0.5, help="Min similarity score")
    parser.add_argument("--semantic-floor", type=float, default=0.0, help="KG semantic floor")
    parser.add_argument("--min-hits", type=int, default=1, help="Required minimum hits per query")
    parser.add_argument(
        "--expected-rank",
        type=int,
        default=3,
        help="Require the expected work within the top N hits",
    )
    parser.add_argument(
        "--show-top",
        type=int,
        default=3,
        help="How many top hits to print for each query",
    )
    args = parser.parse_args()

    failures = 0
    start = time.perf_counter()

    print(f"Endpoint: {args.endpoint}")
    print(f"k={args.k} min_score={args.min_score} semantic_floor={args.semantic_floor}")
    print("-" * 72)

    for corpus, query, expected_titles in STANDARD_QUERIES:
        payload = {
            "query": query,
            "corpus": corpus,
            "k": args.k,
            "min_score": args.min_score,
            "semantic_floor": args.semantic_floor,
            "synthesize": False,
        }
        try:
            out = _post_runsync(args.endpoint, payload)
        except urllib.error.URLError as exc:
            print(f"FAIL [{corpus}] {query}")
            print(f"  request error: {exc}")
            failures += 1
            continue
        except (RuntimeError, ValueError) as exc:
            print(f"FAIL [{corpus}] {query}")
            print(f"  unexpected error: {exc}")
            failures += 1
            continue

        if out.get("error"):
            print(f"FAIL [{corpus}] {query}")
            print(f"  worker error: {out['error']}")
            failures += 1
            continue

        hits = out.get("hits", []) or []
        total = int(out.get("total_hits", len(hits)))
        enough_hits = total >= args.min_hits
        expected_found = _has_expected_title(hits, expected_titles, args.expected_rank)
        ok = enough_hits and expected_found
        status = "PASS" if ok else "FAIL"
        print(f"{status} [{corpus}] hits={total} q={query}")

        for idx, hit in enumerate(hits[: args.show_top], start=1):
            genre = hit.get("genre", "")
            title = hit.get("title") or hit.get("name") or "-"
            score = float(hit.get("score", 0.0))
            print(f"  {idx}. score={score:.3f} genre={genre} title={title}")

        if not ok:
            if not enough_hits:
                print(f"  expected at least {args.min_hits} hits")
            if not expected_found:
                expected = " or ".join(repr(title) for title in expected_titles)
                print(f"  expected {expected} within top {args.expected_rank} titles")
            failures += 1

    elapsed_ms = round((time.perf_counter() - start) * 1000)
    print("-" * 72)
    print(f"Completed in {elapsed_ms} ms")
    if failures:
        print(f"Result: FAIL ({failures} query checks failed)")
        return 1
    print("Result: PASS (all query checks succeeded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
