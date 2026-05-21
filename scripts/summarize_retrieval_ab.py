#!/usr/bin/env python3
"""Summarize retrieval A/B outputs by cap and mode."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv_path", help="Path to similar_to_retrieval_ab_summary_*.csv")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.csv_path)
    rows = list(csv.DictReader(path.open("r", encoding="utf-8", newline="")))

    agg = defaultdict(
        lambda: {
            "n": 0,
            "qsec": 0.0,
            "ret": 0.0,
            "unode": 0.0,
            "ufile": 0.0,
            "sfrac": 0.0,
        }
    )

    for r in rows:
        key = (int(r["cap"]), r["mode"])
        a = agg[key]
        a["n"] += 1
        a["qsec"] += float(r["mean_query_seconds"])
        a["ret"] += float(r["mean_returned_nodes"])
        a["unode"] += float(r["mean_unique_node_ratio"])
        a["ufile"] += float(r["mean_unique_file_ratio"])
        a["sfrac"] += float(r["mean_similar_edge_fraction"])

    print(
        "cap,mode,mean_query_s,mean_returned,mean_unique_node,mean_unique_file,mean_similar_edge_frac"
    )
    for cap in sorted({k[0] for k in agg}):
        for mode in ("without_similar", "with_similar"):
            a = agg[(cap, mode)]
            n = max(a["n"], 1)
            print(
                f"{cap},{mode},{a['qsec'] / n:.5f},{a['ret'] / n:.3f},{a['unode'] / n:.3f},{a['ufile'] / n:.3f},{a['sfrac'] / n:.3f}"
            )

    m = "with_similar"
    if (8, m) in agg and (15, m) in agg:
        a8 = agg[(8, m)]
        a15 = agg[(15, m)]
        n8 = max(a8["n"], 1)
        n15 = max(a15["n"], 1)
        v8 = {k: a8[k] / n8 for k in ("qsec", "ret", "unode", "ufile", "sfrac")}
        v15 = {k: a15[k] / n15 for k in ("qsec", "ret", "unode", "ufile", "sfrac")}

        print("\nwith_similar deltas (15-8):")
        print(f"query_s_delta={v15['qsec'] - v8['qsec']:.5f}")
        print(f"returned_delta={v15['ret'] - v8['ret']:.3f}")
        print(f"unique_node_delta={v15['unode'] - v8['unode']:.3f}")
        print(f"unique_file_delta={v15['ufile'] - v8['ufile']:.3f}")
        print(f"similar_edge_frac_delta={v15['sfrac'] - v8['sfrac']:.3f}")


if __name__ == "__main__":
    main()
