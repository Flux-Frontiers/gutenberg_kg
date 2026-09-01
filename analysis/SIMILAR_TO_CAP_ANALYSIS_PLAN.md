# SIMILAR_TO Cap Analysis Plan

Date: 2026-05-20
Owner: gutenberg_kg team
Status: Draft ready to execute

## Goal

Decide two things with evidence:

1. What `similar_max_degree` default should be.
2. Whether `SIMILAR_TO` edges should be enabled by default in ingest/query workflows.

## Decision Rule

Choose the smallest cap that satisfies all of the following:

1. Retrieval quality is within 95% of the best observed quality across tested caps.
2. SIMILAR_TO scan overhead stays within budget (target: <= 25% extra ingest wall time).
3. Hubness is controlled (max degree and p99 degree remain bounded, no extreme hubs).

If no cap satisfies these, disable SIMILAR_TO by default and keep it as an opt-in mode.

## Hypotheses

1. A moderate cap will preserve most retrieval quality while reducing hub effects and ingest cost.
2. Uncapped or weakly capped SIMILAR_TO edges add cost and graph noise with limited quality gain.
3. SIMILAR_TO helps queries that require semantic bridging across chunks/books, but may be neutral for straightforward lexical queries.

## Scope

In scope:

1. Cap sweep analysis for SIMILAR_TO edge construction.
2. A/B retrieval impact with and without SIMILAR_TO traversal.
3. Build/scan cost analysis.

Out of scope:

1. Embedding model replacement.
2. Major query-ranking redesign.
3. UI/visualization changes.

## Datasets and Sampling

Use a stratified sample from the corpus.

1. Genres: at least 4 (for example biography, philosophy, science-fiction, english-literature).
2. Size tiers per genre: short, medium, long books (by chunk count).
3. Minimum sample: 12 books total.
4. Preferred sample: 24 books total.

Why: avoids overfitting cap choice to one author or one prose style.

## Experimental Factors

Primary factors:

1. `similar_max_degree`: `[0, 2, 4, 6, 8, 10, 15, 20, 30, 50]`
2. `similar_k`: `[5, 10, 20]`

Secondary factor (phase 2 only):

1. `similarity_edge_threshold`: current default, plus one lower and one higher value.

Keep all other settings fixed within each phase.

## Ablation Matrix

For each sampled book and parameter setting, run:

1. No SIMILAR_TO edges created (`discover_similar=False`) baseline.
2. SIMILAR_TO edges created but excluded from expansion rels.
3. SIMILAR_TO edges created and included in expansion rels.

This isolates:

1. Build/storage cost of SIMILAR_TO.
2. Retrieval effect of actually traversing SIMILAR_TO.

## Metrics

### Graph Metrics

1. SIMILAR_TO edge count.
2. Degree distribution by SIMILAR_TO: max, p95, p99.
3. Hub concentration: fraction of edges incident to top 1% nodes.
4. Connected components over chunk subgraph (count and giant component size).

### Cost Metrics

1. Total ingest wall time.
2. SIMILAR_TO scan wall time.
3. SQLite size delta and LanceDB size delta.

### Retrieval Metrics

1. Recall@k (k = 5, 10).
2. MRR@k.
3. nDCG@k (if graded labels are available).
4. Duplicate-rate in top-k chunks.
5. Diversity proxy: unique file paths in top-k.

### Operational Metrics

1. Run-to-run variance (at least 2 repeated runs for selected points).
2. Failure rate/timeouts.

## Relevance Set Construction

Use a mixed approach:

1. Existing benchmark prompts where available.
2. Add per-book query sets with 3 query types:
   - factual/entity lookup,
   - thematic/semantic query,
   - cross-chunk context query.
3. Human label at least a small gold set (for example 10 to 20 queries per genre).

If full manual labeling is too expensive, use a two-stage approach:

1. weak labels for broad sweep,
2. manual labels for finalist caps.

## Execution Phases

### Phase 0: Harness Validation

1. Verify scripts produce deterministic output format.
2. Verify fair comparisons (clear/rebuild SIMILAR_TO edges each run).
3. Dry run on 1 book.

Exit criteria:

1. Outputs include all required graph/cost metrics.
2. Re-run on same settings yields similar results.

### Phase 1: Broad Sweep

1. Run full cap x similar_k matrix on minimum sample.
2. Collect graph + cost + weak retrieval metrics.
3. Identify Pareto frontier and eliminate dominated settings.

Exit criteria:

1. Top 3 candidate caps identified.

### Phase 2: Quality Deep Dive

1. Run finalists on preferred sample.
2. Include manual/gold retrieval evaluation.
3. Run no-SIMILAR_TO baseline comparison.

Exit criteria:

1. Clear recommendation for default cap and default enable/disable choice.

### Phase 3: Stability Check

1. Re-run finalists (2x) on subset to check variance.
2. Confirm selected cap is robust.

Exit criteria:

1. Recommendation remains stable across reruns.

## Analysis Method

1. Build Pareto plots: quality vs ingest overhead, quality vs degree/hubness.
2. Normalize quality score per setting:

   `quality_norm = metric / metric_best`

3. Prefer smallest cap meeting quality threshold and operational constraints.
4. Report confidence bands from repeated runs.

## Recommendation Template

At completion, report:

1. Recommended default `similar_max_degree`.
2. Whether SIMILAR_TO is enabled by default.
3. Optional profiles:
   - fast profile,
   - balanced profile,
   - quality profile.
4. Risks and known caveats.

## Deliverables

1. Raw results per run in JSON/CSV under `analysis/`.
2. Summary notebook or markdown report under `analysis/`.
3. Final recommendation memo under `docs/`.
4. CLI/docs update proposal if defaults change.

## Suggested File Outputs

1. `analysis/similar_to_cap_sweep_<timestamp>.json`
2. `analysis/similar_to_cap_summary_<timestamp>.md`
3. `analysis/SIMILAR_TO_CAP_RECOMMENDATION.md`

## Risks and Mitigations

1. Risk: sample bias by genre or author.
   Mitigation: stratified multi-genre sampling and size tiers.
2. Risk: weak labels mislead quality conclusions.
   Mitigation: manual adjudication on finalist settings.
3. Risk: runtime cost too high for full matrix.
   Mitigation: staged filtering; prune obviously dominated settings early.

## Success Criteria

This analysis is successful if it yields:

1. A defensible default cap value with supporting plots/tables.
2. A clear yes/no decision for enabling SIMILAR_TO by default.
3. Reproducible results and a documented run procedure.

## Next Immediate Actions

1. Build the sampled-book manifest.
2. Finalize query/relevance set.
3. Implement the sweep runner and result schema.
4. Execute Phase 0 dry run.
