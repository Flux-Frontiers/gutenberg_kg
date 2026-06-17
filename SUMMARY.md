# Work Summary — Retrieval Quality, Corpus Hygiene & Build Performance

_Branch: `fix/build-corpus-memory`. Date: 2026-06-16 → 06-17._

This documents three intertwined workstreams, the root-cause findings (especially
the embedding-performance hunt), the exact changes by repo, and the **integration /
release plan** to get everything properly shipped.

---

## TL;DR

1. **Retrieval quality** — the consolidated handler did pure-dense cosine and buried
   exact-term matches (e.g. `[world-literature] "circles of Hell"` returned only
   Purgatory/Paradise). Added **dense + FTS5/BM25 + RRF hybrid** retrieval.
2. **Corpus hygiene** — three mislabeled/duplicate Dante editions in `world-literature`.
   Relabeled to **Longfellow** / **Cary**, dropped the duplicate.
3. **Build performance** — the consolidated embed degraded badly over a run. The hunt
   uncovered **two independent effects** that were tangled together:
   - **Process accumulation** (~16% sag, every machine) — long-lived embedding workers
     accumulate allocator/heap/GC state; **fixed by recycling** (`maxtasksperchild=1`).
   - **Laptop thermal throttling** (laptop-only, recycling-proof) — sustained multi-core
     embedding on the MacBook craters throughput (ETA 7:30 → 30:00 across the inflection)
     *even with recycling*. The Mini ran the identical CPU-parallel path to completion
     (~730 tex/s). **Build on the cool machine; the laptop is not an embedding box.**
   Also: `--embed-device auto` → **MPS** on Macs takes a single-process streaming path
   whose allocator degrades worst (hard-OOM on the laptop). **Force CPU + parallel.**

---

## Root-cause findings (recorded so we don't re-litigate)

The embedding slowdown was chased to ground with measurements, not theory:

- **Data is uniform** — avg chunk length ~430 chars across every genre position; only
  309 chunks > 2048 chars in 348k; bge-small truncates at 512 tokens. No heavy region.
- **The JSONL stream is flat** — replaying the exact `iter_nodes` cursor over the real
  683k graph with a dummy vector (no embedding) streamed **683k rows in 10 s**, flat
  ~65k rows/s. Streaming is a rounding error, not the bottleneck.
- **Not O(n²) pagination** — `store.iter_nodes()` uses a single cursor + `fetchmany`, not
  `LIMIT/OFFSET`.
- **Not (only) thermal** — on the *same Mini*, CPU-parallel embedding was flat (~874 tex/s)
  while MPS single-process streaming sagged. Same heat, different path ⇒ thermal ruled out
  as the primary cause.
- **Effect 1 — process accumulation** — throughput decays as a long-lived embedding process
  crosses ~320k items (allocator/heap/GC growth). Device-independent, ~16% at 683k, grows
  with corpus size. The earlier benchmark "looked flat" only because it stopped at
  `--n 300000`, ~20k short of the inflection.
- **Effect 2 — laptop thermal** — the recycling build on the laptop **still exploded**
  (ETA 7:30 → 30:00 from 298k → 345k), while the same CPU-parallel path completed cleanly on
  the Mini. Same code, different machine ⇒ the laptop delta is heat, and recycling can't fix
  heat. The laptop also spawns more workers (9 vs 7) → more sustained heat = worst case.
- **The MPS trap** — `--embed-device auto` resolves to **MPS** on Macs and takes the
  **single-process `.jsonl` streaming** path, where the MPS allocator degrades worst (and
  on the laptop, hard-OOM'd). That path being the default is what surfaced the problem.

**Conclusion:** embed on **CPU + parallel** with **process recycling** (fixes Effect 1 and
scales), and run the consolidated build on **cool hardware** (the Mini), not the laptop
(Effect 2). Recycling must be validated on cool hardware — the laptop's thermal masks it.

---

## Changes by repo

### `gutenberg_kg` (this repo — branch `fix/build-corpus-memory`, editable)

| File | Change |
|---|---|
| `docker/handler.py` | Hybrid retrieval: `_semantic_search` now fuses **dense cosine + FTS5/BM25** via RRF (`_rrf_fuse`, `_RRF_K=60`, `_open_dockg_store`). Genre/kind filters pushed into both channels; degrades to dense-only if `nodes_fts` absent. |
| `src/gutenberg_kg/build_corpus.py` | (1) Phase-3 **explicit `rebuild_fts()` guard** (root `.dockg` was shipping without `nodes_fts`). (2) Phase-2 **device branch**: CPU → parallel `.json`; MPS/CUDA → single-process `.jsonl` stream; sets `KG_EMBED_DEVICE`; honest "embed mode" banner. |
| `corpus/world-literature/` | **Dante relabel/dedup**: `(Longfellow)` = PG#1004 complete; `(Cary)` = PG#8800 complete (title + H1 fixed); removed PG#8799 (Cary Paradiso-only duplicate). |
| `scratch_embed_bench.py` | Diagnostic: version-independent embedding throughput-over-time harness (single-process & `--parallel`). **Keep** — it's how we isolated the root cause. |

Per-book + registry side-effects already applied locally: the 2 Dante books were
re-ingested (with `nodes_fts`), and 3 stale Dante entries were removed from the KGRAG
registry (`~/.kgrag/registry.sqlite`).

### `kgmodule-utils` (`../KG_utils`) — **0.4.3 → 0.4.4**

- `load_sentence_transformer(model_name, device=None)`: explicit `device` param +
  `KG_EMBED_DEVICE` env override. Precedence: **explicit arg > env > auto-detect**.
  The env channel is what lets spawn-based workers be pinned to CPU (they inherit
  `os.environ`), preventing N workers each grabbing MPS → OOM.

### `doc-kg` (`../doc_kg`) — **0.15.8 → 0.15.9**

| File | Change |
|---|---|
| `embedder_worker.py` | `_resolve_device()`; `CorpusEmbedder(device=None)` + **GPU→single-process guard** (a GPU can't be shared across spawn workers). `_embed_shard` pins the worker via **`model.to(device)`** after an auto-detect load — so doc-kg works with **any** kg_utils version (no hard 0.4.4 dependency; this is the form that shipped). **Performance fix:** many small shards (`_RECYCLE_SHARD=25_000`) + **`Pool(maxtasksperchild=1)`** → a fresh worker per shard, resetting accumulated state ⇒ flat throughput at any scale. |
| `index.py` | `precompute_embeddings(device=None)` passthrough to `CorpusEmbedder`. |
| `kg.py` | `build_embeddings(device=None)` passthrough. |

---

## Status (2026-06-17)

- **Published**: `kgmodule-utils 0.4.4` and `doc-kg 0.15.9` are on PyPI (both confirmed as the
  latest resolvable versions). `gutenberg_kg` pins bumped accordingly (`pyproject.toml` +
  `docker/Dockerfile`).
- **Bundle**: the full consolidated bundle was **built on the Mini** (683k nodes, 857k
  SIMILAR_TO, 233 books, 4 diaries) — on **stock 0.15.8 / 0.4.3**, parallel CPU, ~15:35
  embed (~730 tex/s, ~16% sag, completed). ⚠️ This shipped bundle **predates the recycling
  fix** — recycling (0.15.9) is published but **not yet exercised at 683k scale on cool
  hardware**, so the flat-throughput claim is still pending validation there.
- **Laptop test outcome**: the recycling build on the laptop **still exploded** (ETA 7:30 →
  30:00 across the inflection), confirming the laptop's slowdown is **thermal**, separate from
  process accumulation. The laptop is not an embedding box; build on the Mini.
- **Remaining**: commit the `gutenberg_kg` branch pins + this summary, then **rebuild the
  Docker image** with the new pins + the Mini bundle to make the retrieval fix live.

---

## Source integrity — verified

**`../doc_kg` is NOT stale.** Verified by diffing repo HEAD (0.15.8) against the PyPI
`doc-kg==0.15.8` wheel: `index.py`, `embedder_worker.py`, `kg.py` are **byte-identical**.
So the 0.15.9 changes layer cleanly on the real 0.15.8 — no reconciliation, no regression.
(An earlier worry that the jsonl stream had lost an `mps.empty_cache` eviction was wrong:
that eviction lives in `build()`, and the single-process jsonl stream never had it in 0.15.8.
That missing eviction is a real reason the MPS stream degrades — a roadmap item, not a
release blocker, since CPU+parallel is the supported path.)

---

## Integration / release plan (ordered)

1. ~~Reconcile `../doc_kg` ↔ PyPI 0.15.8~~ — **done; verified byte-identical, not stale.**
2. ~~Release `kgmodule-utils 0.4.4`~~ — **DONE, on PyPI.**
3. ~~Release `doc-kg 0.15.9`~~ — **DONE, on PyPI.** (Shipped with the `model.to(device)`
   decouple, so it no longer hard-depends on kg_utils 0.4.4.)
4. ~~Bump pins in `gutenberg_kg`~~ — **DONE** (`pyproject.toml` floors + `docker/Dockerfile`
   ARGs to 0.15.9 / 0.4.4).
5. **Merge** `fix/build-corpus-memory` → `main` (handler hybrid, build_corpus device branch +
   FTS guard, Dante corpus fix, `scratch_embed_bench.py`, pins, this summary). ← _next_
6. **Rebuild the Docker image** with the released versions + the Mini-built bundle (the bundle
   is already correct; just bake it). Standardize the build command:
   `gutenkg build-corpus --embed-device cpu --embed-batch-size 512`.
7. **Sync other machines** (e.g. the Mini) by `pip install` of the **released** versions —
   not source repos — so they get the recycling fix + device pin without local checkouts.
8. **Validate recycling at scale on cool hardware** (still pending — the shipped bundle was
   built on stock 0.15.8). Re-run a 683k build on the Mini with 0.15.9 and confirm flat past
   ~320k.

---

## Verification checklist (before shipping a bundle)

- [ ] `bundles/gutenberg-all/.dockg/graph.sqlite` has a `nodes_fts` table.
- [ ] `catalog.json` shows **The Divine Comedy (Longfellow)** and **(Cary)**; no
      Purgatorio/Paradiso entries.
- [ ] Handler hybrid retrieval: `[world-literature] "circles of Hell"` now returns
      **Inferno** passages (the original failure).
- [ ] Consolidated build ran on **CPU + parallel** (banner: `parallel (CPU multiprocessing…)`)
      on **cool hardware** (the Mini), not the laptop.
- [ ] Recycling validated on cool hardware: throughput holds **flat past ~320k** (do NOT
      validate on the laptop — thermal masks the result).

---

## Roadmap (when rested — not blocking)

- **Kill the 5.6 GB JSON round-trip.** The `.json` parallel path accumulates every vector in
  RAM then writes/reloads 5.6 GB (~2 min each way). Move to **parallel workers streaming
  compact shards to disk** (numpy/float16), avoiding both the accumulation and the round-trip.
- **Pluggable embedding backend.** Define one interface, target in-process /
  **TEI** (HF `text-embeddings-inference`, platform-agnostic, dynamic batching, flat memory) /
  **MLX** (Apple-Silicon fast path). Decouples embedding from the KG build and gives
  flat-by-design throughput. The platform-agnostic + optional-MLX combo is the goal.
- **Incremental embedding.** Per-book `.dockg` indices already hold vectors; reuse them and
  only embed new/changed books. This is what actually scales as the corpus grows.
- **MPS streaming path:** either fix the allocator growth (the `empty_cache` isn't enough) or
  explicitly deprecate MPS for large consolidated builds (CPU+parallel+recycling is the
  supported path).
