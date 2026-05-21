# SIMILAR_TO Default-On Recommendation

**Date:** 2026-05-21
**Decision:** Enable SIMILAR_TO by default at `similar_max_degree=8`

---

## Decision

**SIMILAR_TO should be default-on at cap 8.**

The labeled evaluation shows a 5.6% relative nDCG gain and a 2.9% relative MRR gain over
the no-SIMILAR baseline, meeting the ≥5% threshold on at least one metric. Cap 8 and cap
15 are statistically indistinguishable, so the lower cap is preferred for its smaller edge
footprint.

---

## Evidence

### Quality metrics (36 labeled queries, 12 books, 4 genres)

| Condition | MRR@15 | nDCG@15 | Recall@15 | Δ MRR vs none | Δ nDCG vs none |
|-----------|--------|---------|-----------|--------------|----------------|
| none      | 0.2300 | 0.1283  | 0.120     | —            | —              |
| cap 8     | 0.2367 | 0.1355  | 0.134     | +2.9%        | **+5.6%**      |
| cap 15    | 0.2369 | 0.1356  | 0.134     | +2.9%        | +5.7%          |

### Cost metrics (mean across 12 books)

| Condition | Mean build time | Mean SIMILAR_TO edges |
|-----------|----------------|----------------------|
| none      | 0.40s          | 0                    |
| cap 8     | 3.86s          | 2,851                |
| cap 15    | 3.85s          | 3,894                |

Build time is flat between cap 8 and cap 15 (0.01s difference). Cap 15 adds 37% more
edges for zero measurable retrieval gain — cap 8 wins on efficiency.

### Prior structural evidence (cap sweep, May 2026)

From `analysis/similar_to_cap_sweep_20260521_020541.csv`:

- Cap 0 (unlimited): 4,058 mean edges, 3.17s build
- Cap 8: 2,550 mean edges, 3.11s build — 34% edge reduction, negligible time cost
- Cap 15: 2,902 mean edges, 3.10s build
- Runtime is nearly flat across all caps

### Prior retrieval A/B evidence

From `analysis/similar_to_retrieval_ab_summary_20260521_021841.csv`, proxy retrieval
between cap 8 and cap 15 shows identical returned nodes and unique node/file ratios,
with cap 15 carrying only +0.007 similar-edge usage fraction over cap 8. This is
consistent with the labeled evaluation showing negligible difference above cap 8.

---

## Decision Criteria Check

| Criterion | Required | Cap 8 result | Met? |
|-----------|----------|--------------|------|
| Relative gain in MRR or nDCG ≥ 5% | Either | nDCG +5.6% | ✅ |
| Gains not limited to one book | All genres | 4 genres all positive | ✅ |
| Edge growth acceptable | Project budget | +2,851 edges mean, 3.4s build | ✅ |

---

## Rollout Plan

### CLI defaults

Change the DocKG build default from `discover_similar=False` to:

```python
discover_similar=True
similar_max_degree=8
similar_k=5
similarity_edge_threshold=0.85
```

### Migration notes

- Existing `.dockg/` indices do **not** contain SIMILAR_TO edges unless they were
  built with `discover_similar=True`. Rebuild with `--force-build` to add them.
- Corpus-level rebuild: `gutenkg ingest --force-build` (all genres) or
  `gutenkg ingest --force-build --genre <genre>` per genre.
- The evaluation embedding cache (`embeddings_value_eval.json`) is a build artefact;
  it is already cleaned up by the evaluator after each book. The standard
  `embeddings.json` per book remains unchanged.
- RunPod batch builds already pass `--similar-max-degree`; update the default there
  to `--similar-max-degree 8` and set `--discover-similar` if not already defaulting.

### What to leave alone

- `similar_k=5` and `similarity_edge_threshold=0.85` remain unchanged — the cap sweep
  showed these produce good edge quality.
- Cap 15 remains available as a user override for corpora where richer cross-section
  retrieval is worth the extra edges.

---

## Evaluation Provenance

| File | Description |
|------|-------------|
| `analysis/similar_to_book_manifest.csv` | 12-book stratified sample (4 genres × 3 size tiers) |
| `analysis/similar_to_query_template.csv` | 36 labeled queries (3 per book: factual / thematic / cross-chunk) |
| `analysis/similar_to_cap_sweep_20260521_020541.csv` | Structural cap sweep |
| `analysis/similar_to_retrieval_ab_summary_20260521_021841.csv` | Proxy A/B retrieval |
| `analysis/similar_to_value_eval_summary_20260521_024749.csv` | Labeled quality summary |
| `analysis/similar_to_value_eval_20260521_024749.json` | Full JSON payload + recommendation block |

Scripts: `scripts/run_similar_to_cap_sweep.py`, `scripts/run_retrieval_cap_ab.py`,
`scripts/evaluate_similar_to_value.py`
