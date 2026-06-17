#!/usr/bin/env python3
"""Isolate embedding throughput-over-time: physical (thermal) vs code regression.

A 683k-node embed is constant-cost per node, so throughput should be FLAT. This
benchmark feeds fixed-length synthetic texts (constant per-batch work) and logs
tex/s every 10k, so any decline is *not* data-dependent. Run the SAME script on
the laptop and the Mini:

    python scratch_embed_bench.py                  # single-process, CPU, 150k
    python scratch_embed_bench.py --parallel       # CorpusEmbedder (9 workers)
    python scratch_embed_bench.py --device mps     # GPU path
    python scratch_embed_bench.py --n 250000

How to read it (single-process is the cleanest signal):
  * FLAT tex/s start→end .......... loop is healthy; full-build slowdown is the
                                    parallel machinery or thermal, not embedding.
  * DEGRADES on laptop, FLAT on Mini ... physical: laptop thermal/power throttle.
  * DEGRADES on BOTH ............... torch/model/OS level, not our pipeline.
"""

from __future__ import annotations

import argparse
import os
import platform
import statistics
import time


def machine_info(device: str) -> None:
    print("=" * 60)
    print(f"host={platform.node()}  arch={platform.machine()}  cores={os.cpu_count()}")
    try:
        ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
        print(f"ram={ram:.0f}GB  python={platform.python_version()}  device={device}")
    except Exception:  # noqa: BLE001
        pass
    for m in ("kg_utils", "doc_kg"):
        try:
            print(f"  {m}={getattr(__import__(m), '__version__', '?')}")
        except Exception as e:  # noqa: BLE001
            print(f"  {m}=<not importable: {e}>")
    print("=" * 60)


def make_texts(n: int, length: int = 430) -> list[str]:
    """Fixed-length texts → constant per-batch cost (no data-driven variation)."""
    base = ("the quick brown fox jumps over the lazy dog " * 20)[:length]
    return [f"{i:08d} {base}" for i in range(n)]


def run_single(n: int, batch_size: int, device: str, model_name: str) -> None:
    os.environ["KG_EMBED_DEVICE"] = device
    from kg_utils.embedder import load_sentence_transformer

    print(f"[single] loading {model_name} on {device} ...")
    model = load_sentence_transformer(model_name, device=device)
    texts = make_texts(n)
    print(f"[single] embedding {n:,} texts (batch={batch_size}); tex/s per 10k:")

    t0 = time.monotonic()
    last_t, last_i, rates = t0, 0, []
    for i in range(0, n, batch_size):
        model.encode(
            texts[i : i + batch_size],
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        done = min(i + batch_size, n)
        if done - last_i >= 10000 or done == n:
            now = time.monotonic()
            rate = (done - last_i) / (now - last_t)
            rates.append(rate)
            print(f"  {done:>7}/{n}  {rate:7.0f} tex/s   (cumulative {done / (now - t0):7.0f})")
            last_t, last_i = now, done

    tot = time.monotonic() - t0
    print(f"[single] TOTAL {n:,} in {tot:.0f}s  =  {n / tot:.0f} tex/s avg")
    if len(rates) >= 4:
        first, last = statistics.mean(rates[:2]), statistics.mean(rates[-2:])
        ratio = first / last if last else float("inf")
        verdict = "DEGRADES (physical/thermal or torch)" if ratio > 1.5 else "FLAT (loop healthy)"
        print(f"[single] first {first:.0f} → last {last:.0f} tex/s  | {ratio:.2f}x  >>> {verdict}")


def run_parallel(n: int, batch_size: int, device: str, model_name: str) -> None:
    os.environ["KG_EMBED_DEVICE"] = device
    from doc_kg.embedder_worker import CorpusEmbedder

    texts = make_texts(n)
    ce = CorpusEmbedder(model_name, batch_size=batch_size, device=device)
    print(f"[parallel] n={n:,} workers={ce.n_workers} device={ce.device}")
    t0 = time.monotonic()
    cache = ce.embed(texts)
    tot = time.monotonic() - t0
    print(
        f"[parallel] TOTAL {n:,} in {tot:.0f}s  =  {n / tot:.0f} tex/s avg  (vectors={cache.n_vectors:,})"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150000)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--device", default="cpu", choices=["cpu", "mps", "cuda"])
    ap.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    ap.add_argument(
        "--parallel", action="store_true", help="use CorpusEmbedder instead of single-process"
    )
    args = ap.parse_args()

    machine_info(args.device)
    (run_parallel if args.parallel else run_single)(
        args.n, args.batch_size, args.device, args.model
    )
