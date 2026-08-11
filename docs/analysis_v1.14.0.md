> **Analysis Report Metadata**
> - **Generated:** 2026-08-11T20:11:13Z
> - **Version:** pycode-kg 0.21.2
> - **Commit:** 5590e2c (main)
> - **Platform:** macOS 27.0 | arm64 (arm) | turing | Python 3.12.13
> - **Graph:** 7659 nodes · 6508 edges (501 meaningful)
> - **Included directories:** docker, runpod, src
> - **Excluded directories:** none
> - **Elapsed time:** 5s

# gutenberg_kg Analysis

**Generated:** 2026-08-11 20:11:13 UTC

---

## Executive Summary

This report provides a comprehensive architectural analysis of the **gutenberg_kg** repository using PyCodeKG's knowledge graph. The analysis covers complexity hotspots, module coupling, key call chains, and code quality signals to guide refactoring and architecture decisions.

| Overall Quality | Grade | Score |
|----------------|-------|-------|
| [B] **Good** | **B** | 80 / 100 |

---

## Baseline Metrics

| Metric | Value |
|--------|-------|
| **Total Nodes** | 7659 |
| **Total Edges** | 6508 |
| **Modules** | 54 (of 54 total) |
| **Functions** | 337 |
| **Classes** | 30 |
| **Methods** | 80 |

### Edge Distribution

| Relationship Type | Count |
|-------------------|-------|
| CALLS | 2791 |
| CONTAINS | 447 |
| IMPORTS | 433 |
| ATTR_ACCESS | 2035 |
| INHERITS | 11 |

---

## Fan-In Ranking

Most-called functions are potential bottlenecks or core functionality. These functions are heavily depended upon across the codebase.

| # | Function | Module | Callers |
|---|----------|--------|---------|
| 1 | `run()` | runpod/build_kg.py | **12** |
| 2 | `step()` | runpod/build_kg.py | **8** |
| 3 | `info()` | runpod/build_kg.py | **8** |
| 4 | `reset_camera()` | src/gutenberg_kg/viz3d.py | **5** |
| 5 | `_c()` | runpod/build_kg.py | **4** |
| 6 | `_call_worker()` | src/gutenberg_kg/serve/pages/1_Browse.py | **4** |
| 7 | `edges()` | src/gutenberg_kg/ingest.py | **4** |
| 8 | `nodes()` | src/gutenberg_kg/ingest.py | **4** |
| 9 | `_month_num()` | src/gutenberg_kg/diary/parser.py | **4** |
| 10 | `collect_genre_stats()` | src/gutenberg_kg/corpus.py | **4** |
| 11 | `fetch_url()` | src/gutenberg_kg/gutenberg.py | **4** |
| 12 | `slugify()` | src/gutenberg_kg/ingest.py | **4** |
| 13 | `fmt_duration()` | src/gutenberg_kg/ingest.py | **4** |
| 14 | `elapsed()` | src/gutenberg_kg/ingest.py | **3** |
| 15 | `_clear_highlight()` | src/gutenberg_kg/viz3d.py | **3** |


**Insight:** Functions with high fan-in are either core APIs or bottlenecks. Review these for:
- Thread safety and performance
- Clear documentation and contracts
- Potential for breaking changes

---

## High Fan-Out Functions (Orchestrators)

Functions that call many others may indicate complex orchestration logic or poor separation of concerns.

No extreme high fan-out functions detected. Well-balanced architecture.

---

## Module Architecture

Top modules by dependency coupling and cohesion (showing up to 10 with activity).
Cohesion = incoming / (incoming + outgoing + 1); higher = more internally focused.

| Module | Functions | Classes | Incoming | Outgoing | Cohesion |
|--------|-----------|---------|----------|----------|----------|
| `src/gutenberg_kg/viz3d.py` | 5 | 3 | 0 | 1 | 0.00 |
| `src/gutenberg_kg/ingest.py` | 20 | 5 | 5 | 1 | 0.71 |
| `src/gutenberg_kg/scene.py` | 14 | 5 | 1 | 1 | 0.33 |
| `src/gutenberg_kg/serve/handler.py` | 27 | 0 | 0 | 2 | 0.00 |
| `src/gutenberg_kg/diary/parser.py` | 7 | 5 | 4 | 0 | 0.80 |
| `src/gutenberg_kg/gutenberg.py` | 22 | 0 | 2 | 3 | 0.33 |
| `src/gutenberg_kg/corpus.py` | 14 | 1 | 3 | 1 | 0.60 |
| `runpod/build_kg.py` | 19 | 0 | 2 | 0 | 0.67 |
| `src/gutenberg_kg/serve/Chat.py` | 19 | 0 | 0 | 0 | 0.00 |
| `src/gutenberg_kg/ia.py` | 18 | 0 | 1 | 2 | 0.25 |

---

## Key Call Chains

Deepest call chains in the codebase.

**Chain 1** (depth: 3)

```
reset_settings → reset_camera → render
```

---

## Public API Surface

Identified public APIs (module-level functions with high usage).

| Function | Module | Fan-In | Type |
|----------|--------|--------|------|
| `run()` | runpod/build_kg.py | 12 | function |
| `info()` | runpod/build_kg.py | 8 | function |
| `step()` | runpod/build_kg.py | 8 | function |
| `collect_genre_stats()` | src/gutenberg_kg/corpus.py | 4 | function |
| `fetch_url()` | src/gutenberg_kg/gutenberg.py | 4 | function |
| `slugify()` | src/gutenberg_kg/ingest.py | 4 | function |
| `fmt_duration()` | src/gutenberg_kg/ingest.py | 4 | function |
| `parse()` | src/gutenberg_kg/diary/parser.py | 3 | function |
| `error()` | runpod/build_kg.py | 2 | function |
| `get_parser()` | src/gutenberg_kg/diary/parser.py | 2 | function |
---

## Docstring Coverage

Docstring coverage directly determines semantic retrieval quality. Nodes without
docstrings embed only structured identifiers (`KIND/NAME/QUALNAME/MODULE`), where
keyword search is as effective as vector embeddings. The semantic model earns its
value only when a docstring is present.

| Kind | Documented | Total | Coverage |
|------|-----------|-------|----------|
| `function` | 321 | 337 | [OK] 95.3% |
| `method` | 73 | 80 | [OK] 91.2% |
| `class` | 28 | 30 | [OK] 93.3% |
| `module` | 53 | 54 | [OK] 98.1% |
| **total** | **475** | **501** | **[OK] 94.8%** |

---

## Structural Importance Ranking (SIR)

Weighted PageRank aggregated by module — reveals architectural spine. Cross-module edges boosted 1.5×; private symbols penalized 0.85×. Node-level detail: `pycodekg centrality --top 25`

| Rank | Score | Members | Module |
|------|-------|---------|--------|
| 1 | 0.132222 | 40 | `src/gutenberg_kg/ingest.py` |
| 2 | 0.076489 | 45 | `src/gutenberg_kg/viz3d.py` |
| 3 | 0.067514 | 21 | `src/gutenberg_kg/corpus.py` |
| 4 | 0.062942 | 29 | `src/gutenberg_kg/scene.py` |
| 5 | 0.060229 | 20 | `runpod/build_kg.py` |
| 6 | 0.055794 | 23 | `src/gutenberg_kg/gutenberg.py` |
| 7 | 0.050238 | 23 | `src/gutenberg_kg/diary/parser.py` |
| 8 | 0.038204 | 19 | `src/gutenberg_kg/ia.py` |
| 9 | 0.037941 | 28 | `src/gutenberg_kg/serve/handler.py` |
| 10 | 0.033781 | 14 | `src/gutenberg_kg/layout_organic.py` |
| 11 | 0.029724 | 18 | `src/gutenberg_kg/audit.py` |
| 12 | 0.024328 | 20 | `src/gutenberg_kg/serve/Chat.py` |
| 13 | 0.023398 | 9 | `src/gutenberg_kg/authors.py` |
| 14 | 0.022042 | 17 | `runpod/handler.py` |
| 15 | 0.020010 | 12 | `src/gutenberg_kg/build_corpus.py` |



---

## Code Quality Issues

- [WARN] 3 orphaned functions found (`_clean`, `main`, `ImageGenRequest`) -- consider archiving or documenting
- [WARN] `viz3d.py` has 44 functions/methods/classes -- consider splitting into focused submodules
- [WARN] `ingest.py` has 39 functions/methods/classes -- consider splitting into focused submodules

---

## Architectural Strengths

- Well-structured with 15 core functions identified
- No god objects or god functions detected
- Good docstring coverage: 94.8% of functions/methods/classes/modules documented

---

## Recommendations

### Immediate Actions
1. **Remove or archive orphaned functions** — `_clean`, `main`, `ImageGenRequest` have zero callers and add maintenance burden

### Medium-term Refactoring
1. **Harden high fan-in functions** — `run`, `step`, `info` are widely depended upon; review for thread safety, clear contracts, and stable interfaces
2. **Reduce module coupling** — consider splitting tightly coupled modules or introducing interface boundaries
3. **Add tests for key call chains** — the identified call chains represent well-traveled execution paths that benefit most from regression coverage

### Long-term Architecture
1. **Version and stabilize the public API** — document breaking-change policies for `run`, `info`, `step`
2. **Enforce layer boundaries** — add linting or CI checks to prevent unexpected cross-module dependencies as the codebase grows
3. **Monitor hot paths** — instrument the high fan-in functions identified here to catch performance regressions early

---

## Inheritance Hierarchy

**11** INHERITS edges across **11** classes. Max depth: **1**.

| Class | Module | Depth | Parents | Children |
|-------|--------|-------|---------|----------|
| `BoswellParser` | src/gutenberg_kg/diary/parser.py | 1 | 1 | 0 |
| `EvelynParser` | src/gutenberg_kg/diary/parser.py | 1 | 1 | 0 |
| `PepysParser` | src/gutenberg_kg/diary/parser.py | 1 | 1 | 0 |
| `GutenbergSnapshotManager` | src/gutenberg_kg/corpus.py | 0 | 1 | 0 |
| `BaseDiaryParser` | src/gutenberg_kg/diary/parser.py | 0 | 1 | 3 |
| `ForestLayout` | src/gutenberg_kg/scene.py | 0 | 1 | 0 |
| `ImageGenRequest` | src/gutenberg_kg/serve/image_server.py | 0 | 1 | 0 |
| `ImageGenRequest` | src/gutenberg_kg/serve/sdxl_server.py | 0 | 1 | 0 |
| `ForestMainWindow` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |
| `GutenbergForestVisualizer` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |
| `TextPopup` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |


---

## Snapshot History

Recent snapshots in reverse chronological order. Δ columns show change vs. the immediately preceding snapshot.

| # | Timestamp | Branch | Version | Nodes | Edges | Coverage | Δ Nodes | Δ Edges | Δ Coverage |
|---|-----------|--------|---------|-------|-------|----------|---------|---------|------------|
| 1 | 2026-07-10 20:11:27 | main | 0.19.3 | 6453 | 5461 | 95.0% | +2585 | +2207 | +19.4% |
| 2 | 2026-06-06 01:27:01 | main | 0.19.2 | 3868 | 3254 | 75.6% | — | — | — |


---

## Appendix: Orphaned Code

Functions with zero callers (potential dead code):

| Function | Module | Lines |
|----------|--------|-------|
| `ImageGenRequest()` | src/gutenberg_kg/serve/sdxl_server.py | 9 |
| `_clean()` | src/gutenberg_kg/diary/parser.py | 4 |
| `main()` | src/gutenberg_kg/serve/handler.py | 2 |
---

## CodeRank -- Global Structural Importance

Weighted PageRank over CALLS + IMPORTS + INHERITS edges (test paths excluded). Scores are normalized to sum to 1.0. This ranking seeds Phase 2 fan-in discovery and Phase 15 concern queries.

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.000608 | function | `_c` | runpod/build_kg.py |
| 2 | 0.000390 | method | `BookMeta.kg_dir` | src/gutenberg_kg/scene.py |
| 3 | 0.000386 | function | `_call_worker` | src/gutenberg_kg/serve/pages/1_Browse.py |
| 4 | 0.000333 | method | `GenreSummary.nodes` | src/gutenberg_kg/ingest.py |
| 5 | 0.000333 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 6 | 0.000315 | method | `GenreSummary.elapsed` | src/gutenberg_kg/ingest.py |
| 7 | 0.000305 | function | `step` | runpod/build_kg.py |
| 8 | 0.000285 | function | `_month_num` | src/gutenberg_kg/diary/parser.py |
| 9 | 0.000273 | function | `run` | runpod/build_kg.py |
| 10 | 0.000270 | function | `info` | runpod/build_kg.py |
| 11 | 0.000261 | method | `ForestMainWindow._clear_highlight` | src/gutenberg_kg/viz3d.py |
| 12 | 0.000252 | class | `ModelCheckResult` | src/gutenberg_kg/model_setup.py |
| 13 | 0.000237 | function | `_open_vector_source` | runpod/handler.py |
| 14 | 0.000237 | function | `_open_vector_source` | src/gutenberg_kg/serve/handler.py |
| 15 | 0.000231 | function | `_dockg_store_ro` | src/gutenberg_kg/serve/handler.py |
| 16 | 0.000229 | function | `survey_repo` | src/gutenberg_kg/gutenberg.py |
| 17 | 0.000229 | function | `_save` | src/gutenberg_kg/genres.py |
| 18 | 0.000197 | function | `slugify` | src/gutenberg_kg/gutenberg.py |
| 19 | 0.000196 | method | `Skeleton.n_nodes` | src/gutenberg_kg/layout_organic.py |
| 20 | 0.000196 | function | `_count_authors` | src/gutenberg_kg/corpus.py |

---

## Concern-Based Hybrid Ranking

Top structurally-dominant nodes per architectural concern (0.60 × semantic + 0.25 × CodeRank + 0.15 × graph proximity).

### Configuration Loading Initialization Setup

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7516 | function | `setup_env` | runpod/build_kg.py |
| 2 | 0.7276 | function | `install_system_deps` | runpod/build_kg.py |
| 3 | 0.7274 | function | `_init_state` | src/gutenberg_kg/serve/Chat.py |
| 4 | 0.7273 | function | `init` | src/gutenberg_kg/cli/cmd_init.py |
| 5 | 0.7243 | method | `ForestLayout.__init__` | src/gutenberg_kg/scene.py |

### Data Persistence Storage Database

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7673 | function | `_dockg_store_ro` | src/gutenberg_kg/serve/handler.py |
| 2 | 0.7545 | function | `_stored_vector_dim` | src/gutenberg_kg/serve/handler.py |
| 3 | 0.75 | method | `GutenbergSnapshotManager.save_snapshot` | src/gutenberg_kg/corpus.py |
| 4 | 0.7477 | function | `resolve_vector_paths` | src/gutenberg_kg/vector_store.py |
| 5 | 0.7445 | function | `snapshot_save` | src/gutenberg_kg/cli/cmd_snapshot.py |

### Query Search Retrieval Semantic

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7512 | function | `_semantic_search` | src/gutenberg_kg/serve/handler.py |
| 2 | 0.7367 | function | `_semantic_search_diaries` | src/gutenberg_kg/serve/handler.py |
| 3 | 0.7277 | function | `_semantic_search` | runpod/handler.py |
| 4 | 0.723 | function | `_query_corpus` | src/gutenberg_kg/cli/cmd_imagine.py |
| 5 | 0.72 | function | `ia_search` | src/gutenberg_kg/cli/cmd_ia.py |

### Graph Traversal Node Edge

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7822 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 2 | 0.754 | function | `colonize` | src/gutenberg_kg/layout_organic.py |
| 3 | 0.75 | method | `ForestLayout.compute` | src/gutenberg_kg/scene.py |
| 4 | 0.7458 | function | `crown_spacing` | src/gutenberg_kg/layout_organic.py |
| 5 | 0.7415 | function | `grow_tree` | src/gutenberg_kg/layout_organic.py |



---

*Report generated by PyCodeKG Thorough Analysis Tool — analysis completed in 5.2s*
