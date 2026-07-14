# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Benchmark spike: LanceDB (IvfFlat ANN) vs sqlite-vec (vec0 brute force).

Converts the consolidated DocKG LanceDB table's searched subset — the same
``kind IN ('chunk','section') AND file_path NOT LIKE '%reference.md'`` scope
the serve handler queries — into vec0 tables (fp32 and int8) and compares
both engines against exact NumPy ground truth on a golden query set.

Reports per-query and aggregate:
  * recall@10 vs exact brute-force ground truth
  * cosine-score error (int8 quantization loss)
  * warm query latency (median of 5)
  * on-disk size of each store

Usage (from repo root):
    poetry run python benchmarks/bench_sqlite_vec.py [--out DIR]

sqlite-vec is not a project dependency; install it anywhere importable, e.g.:
    poetry run pip install --target /tmp/pylibs sqlite-vec
    PYTHONPATH=/tmp/pylibs poetry run python benchmarks/bench_sqlite_vec.py
"""

from __future__ import annotations

import argparse
import sqlite3
import statistics
import time
from pathlib import Path

import numpy as np

BUNDLE_LANCEDB = Path("bundles/gutenberg-all/.dockg/lancedb")
TABLE = "dockg_nodes"
DIM = 384
K = 10
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
WHERE = "kind IN ('chunk', 'section') AND file_path NOT LIKE '%reference.md'"

GOLDEN_QUERIES = [
    "pillar of salt",
    "circles of Hell",
    "What does the Quran say about Moses?",
    "the whiteness of the whale",
    "descriptions of the Great Fire of London",
    "the categorical imperative and moral duty",
    "a monster assembled from dead body parts",
    "time travel to the distant future",
    "the fall of the House of Usher",
    "how to wire an electric bell",
    "shipwreck on a desert island",
    "a dinner party with too much wine in a London diary",
]


def load_eligible_rows() -> tuple[list[str], np.ndarray]:
    """Load (ids, vectors) for the handler-eligible subset from LanceDB.

    :returns: Node IDs and an ``(N, 384)`` float32 vector matrix.
    """
    import lancedb

    db = lancedb.connect(str(BUNDLE_LANCEDB))
    t = db.open_table(TABLE)
    try:
        arrow = t.to_arrow(columns=["id", "kind", "file_path", "vector"])
    except TypeError:
        arrow = t.to_arrow()
    kinds = arrow["kind"].to_pylist()
    paths = arrow["file_path"].to_pylist()
    ids_all = arrow["id"].to_pylist()
    vecs_all = np.asarray(arrow["vector"].to_pylist(), dtype=np.float32)
    mask = [
        k in ("chunk", "section") and not (p or "").endswith("reference.md")
        for k, p in zip(kinds, paths)
    ]
    idx = np.flatnonzero(mask)
    ids = [ids_all[i] for i in idx]
    return ids, vecs_all[idx]


def build_vec0(db_path: Path, ids: list[str], vecs: np.ndarray, dtype: str) -> None:
    """Build a vec0 table at *db_path* from the given vectors.

    :param dtype: ``"float"`` or ``"int8"`` (int8 assumes unit-norm inputs,
        scaled by 127).
    """
    import sqlite_vec

    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute(
        f"CREATE VIRTUAL TABLE v USING vec0("
        f"id TEXT PRIMARY KEY, embedding {dtype}[{DIM}] distance_metric=cosine)"
    )
    if dtype == "int8":
        payload = np.clip(np.round(vecs * 127.0), -128, 127).astype(np.int8)
        value_expr = "vec_int8(?)"  # raw 384-byte blobs are parsed as float32
    else:
        payload = vecs
        value_expr = "?"
    batch = 5000
    with conn:
        for start in range(0, len(ids), batch):
            rows = [
                (ids[i], payload[i].tobytes()) for i in range(start, min(start + batch, len(ids)))
            ]
            conn.executemany(f"INSERT INTO v(id, embedding) VALUES (?, {value_expr})", rows)
    conn.close()


def vec0_search(conn: sqlite3.Connection, qvec: np.ndarray, dtype: str) -> list[tuple[str, float]]:
    """Top-k cosine kNN against a vec0 table; returns (id, similarity) pairs."""
    if dtype == "int8":
        blob = np.clip(np.round(qvec * 127.0), -128, 127).astype(np.int8).tobytes()
        match_expr = "vec_int8(?)"
    else:
        blob = qvec.astype(np.float32).tobytes()
        match_expr = "?"
    rows = conn.execute(
        f"SELECT id, distance FROM v WHERE embedding MATCH {match_expr} AND k = ? "
        "ORDER BY distance",
        (blob, K),
    ).fetchall()
    return [(r[0], 1.0 - r[1]) for r in rows]


def timed(fn, n: int = 5) -> tuple[object, float]:
    """Run *fn* once to warm, then *n* times; return (result, median ms)."""
    result = fn()
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return result, statistics.median(times)


def main() -> None:
    """Run the benchmark and write RESULTS.md next to this script."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("benchmarks"))
    args = parser.parse_args()

    import lancedb
    import sqlite_vec
    from sentence_transformers import SentenceTransformer

    print("loading eligible rows from LanceDB …", flush=True)
    ids, vecs = load_eligible_rows()
    n = len(ids)
    print(f"  {n:,} vectors ({vecs.nbytes / 1e6:.0f} MB fp32)", flush=True)

    # Exact ground truth needs true cosine: normalize a copy.
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    unit = vecs / np.maximum(norms, 1e-12)

    print("embedding golden queries …", flush=True)
    model = SentenceTransformer(EMBED_MODEL)
    qvecs = model.encode(GOLDEN_QUERIES, normalize_embeddings=True).astype(np.float32)

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    fp32_db = out_dir / "vec_fp32.db"
    int8_db = out_dir / "vec_int8.db"
    for dtype, path in [("float", fp32_db), ("int8", int8_db)]:
        print(f"building vec0 {dtype} table …", flush=True)
        t0 = time.perf_counter()
        build_vec0(path, ids, unit, dtype)
        print(
            f"  {path.name}: {path.stat().st_size / 1e6:.0f} MB in {time.perf_counter() - t0:.0f}s",
            flush=True,
        )

    ldb = lancedb.connect(str(BUNDLE_LANCEDB))
    table = ldb.open_table(TABLE)

    conns = {}
    for dtype, path in [("float", fp32_db), ("int8", int8_db)]:
        c = sqlite3.connect(path)
        c.enable_load_extension(True)
        sqlite_vec.load(c)
        c.enable_load_extension(False)
        conns[dtype] = c

    id_pos = {nid: i for i, nid in enumerate(ids)}
    lines = [
        "# sqlite-vec vs LanceDB — benchmark results",
        "",
        f"Corpus subset: {n:,} chunk/section vectors, {DIM}-dim, {EMBED_MODEL}.",
        "Ground truth: exact NumPy cosine top-10. LanceDB uses its IvfFlat ANN "
        "index; vec0 is exact brute force.",
        "",
        "| Query | LanceDB r@10 / ms | vec0 fp32 r@10 / ms | vec0 int8 r@10 / ms | int8 score MAE |",
        "|---|---|---|---|---|",
    ]
    agg = {"lance": [], "fp32": [], "int8": []}
    lat = {"lance": [], "fp32": [], "int8": []}
    maes = []
    for q, qvec in zip(GOLDEN_QUERIES, qvecs):
        sims = unit @ qvec
        truth_idx = np.argsort(-sims)[:K]
        truth = {ids[i] for i in truth_idx}
        truth_scores = {ids[i]: float(sims[i]) for i in truth_idx}

        res_l, ms_l = timed(
            lambda qv=qvec: (
                table.search(qv).metric("cosine").where(WHERE, prefilter=True).limit(K).to_list()
            )
        )
        got_l = {r["id"] for r in res_l}

        res_f, ms_f = timed(lambda qv=qvec: vec0_search(conns["float"], qv, "float"))
        got_f = {r[0] for r in res_f}

        res_i, ms_i = timed(lambda qv=qvec: vec0_search(conns["int8"], qv, "int8"))
        got_i = {r[0] for r in res_i}
        # Quantization score error over int8 hits that exist in ground truth
        errs = [abs(s - truth_scores[nid]) for nid, s in res_i if nid in truth_scores]
        # Fall back to exact-recomputed scores for hits outside the truth set
        errs += [
            abs(s - float(unit[id_pos[nid]] @ qvec))
            for nid, s in res_i
            if nid not in truth_scores and nid in id_pos
        ]
        mae = statistics.mean(errs) if errs else 0.0
        maes.append(mae)

        r_l, r_f, r_i = (len(truth & g) / K for g in (got_l, got_f, got_i))
        agg["lance"].append(r_l)
        agg["fp32"].append(r_f)
        agg["int8"].append(r_i)
        lat["lance"].append(ms_l)
        lat["fp32"].append(ms_f)
        lat["int8"].append(ms_i)
        lines.append(
            f"| {q} | {r_l:.1f} / {ms_l:.0f} | {r_f:.1f} / {ms_f:.0f} "
            f"| {r_i:.1f} / {ms_i:.0f} | {mae:.4f} |"
        )
        print(
            f"  {q!r}: lance {r_l:.1f}@{ms_l:.0f}ms  fp32 {r_f:.1f}@{ms_f:.0f}ms  "
            f"int8 {r_i:.1f}@{ms_i:.0f}ms  mae {mae:.4f}",
            flush=True,
        )

    lines += [
        "",
        "## Aggregate",
        "",
        "| Engine | mean recall@10 | median latency (ms) | store size |",
        "|---|---|---|---|",
        f"| LanceDB IvfFlat | {statistics.mean(agg['lance']):.3f} | "
        f"{statistics.median(lat['lance']):.0f} | 2.5 GB (688K rows, incl. embed-text) |",
        f"| vec0 fp32 (exact) | {statistics.mean(agg['fp32']):.3f} | "
        f"{statistics.median(lat['fp32']):.0f} | {fp32_db.stat().st_size / 1e6:.0f} MB |",
        f"| vec0 int8 (exact) | {statistics.mean(agg['int8']):.3f} | "
        f"{statistics.median(lat['int8']):.0f} | {int8_db.stat().st_size / 1e6:.0f} MB |",
        "",
        f"int8 mean cosine-score MAE: {statistics.mean(maes):.4f}",
        "",
    ]
    results = out_dir / "SQLITE_VEC_RESULTS.md"
    results.write_text("\n".join(lines))
    print(f"\nwrote {results}", flush=True)


if __name__ == "__main__":
    main()
