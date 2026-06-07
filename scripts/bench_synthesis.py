#!/usr/bin/env python3
"""Latency benchmark for the GutenbergKG synthesis endpoint.

Hits http://localhost:8000/runsync with synthesize=true and reports
wall-clock, search_ms, and synthesis_ms for each query.
"""

from __future__ import annotations

import sys
import time

import httpx

ENDPOINT = "http://localhost:8000/runsync"

QUERIES = [
    ("What did Pepys observe about the Great Fire of London?", "diary", 8),
    ("How did Pepys describe plague and disease in London?", "diary", 8),
    ("What does Pepys say about King Charles II at court?", "diary", 8),
    ("Describe Pepys's experiences at the theatre.", "diary", 6),
    ("What were Boswell's impressions of Samuel Johnson?", "diary", 6),
]


def run(query: str, corpus: str, k: int, client: httpx.Client) -> dict:
    payload = {
        "input": {
            "query": query,
            "corpus": corpus,
            "k": k,
            "synthesize": True,
        }
    }
    t0 = time.perf_counter()
    resp = client.post(ENDPOINT, json=payload, timeout=300.0)
    wall_ms = (time.perf_counter() - t0) * 1000
    resp.raise_for_status()
    out = resp.json().get("output", {})
    return {
        "query": query[:60],
        "corpus": corpus,
        "hits": out.get("total_hits", 0),
        "search_ms": out.get("search_ms"),
        "synthesis_ms": out.get("synthesis_ms"),
        "wall_ms": round(wall_ms),
        "model": out.get("model", ""),
        "answer_len": len(out.get("synthesis") or ""),
        "error": out.get("error"),
    }


def main() -> None:
    print(
        f"{'Query':<62} {'Corpus':<16} {'Hits':>4} {'Search':>8} {'Synth':>8} {'Wall':>8}  Answer"
    )
    print("-" * 130)

    results = []
    with httpx.Client() as client:
        for query, corpus, k in QUERIES:
            try:
                r = run(query, corpus, k, client)
            except Exception as exc:  # noqa: BLE001
                print(f"  ERROR: {exc}")
                continue

            if r["error"]:
                print(f"  HANDLER ERROR: {r['error']}")
                continue

            results.append(r)
            srch = f"{r['search_ms']:>7}ms" if r["search_ms"] is not None else "       N/A"
            syn = f"{r['synthesis_ms']:>7}ms" if r["synthesis_ms"] is not None else "       N/A"
            print(
                f"{r['query']:<62} {r['corpus']:<16} {r['hits']:>4}"
                f" {srch} {syn} {r['wall_ms']:>7}ms  {r['answer_len']}ch"
            )

    if not results:
        print("No results.")
        sys.exit(1)

    print("-" * 130)
    srch_vals = [r["search_ms"] for r in results if r["search_ms"] is not None]
    syn_vals = [r["synthesis_ms"] for r in results if r["synthesis_ms"] is not None]
    wall_vals = [r["wall_ms"] for r in results]

    def stats(vals: list[int]) -> str:
        if not vals:
            return "N/A"
        return f"avg={sum(vals) // len(vals)}ms  min={min(vals)}ms  max={max(vals)}ms"

    print(f"Search:    {stats(srch_vals)}")
    print(f"Synthesis: {stats(syn_vals)}")
    print(f"Wall:      {stats(wall_vals)}")
    if results:
        print(f"Model:     {results[0]['model']}")


if __name__ == "__main__":
    main()
