> **Analysis Report Metadata**
> - **Generated:** 2026-06-17T22:52:41Z
> - **Version:** pycode-kg 0.19.3
> - **Commit:** 22c7ce3 (feat/incremental-build)
> - **Platform:** macOS 27.0 | arm64 (arm) | turing | Python 3.12.13
> - **Graph:** 5361 nodes · 4479 edges (346 meaningful)
> - **Included directories:** docker, runpod, src
> - **Excluded directories:** none
> - **Elapsed time:** 6s

# gutenberg_kg Analysis

**Generated:** 2026-06-17 22:52:41 UTC

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
| **Total Nodes** | 5361 |
| **Total Edges** | 4479 |
| **Modules** | 37 (of 37 total) |
| **Functions** | 235 |
| **Classes** | 15 |
| **Methods** | 59 |

### Edge Distribution

| Relationship Type | Count |
|-------------------|-------|
| CALLS | 1949 |
| CONTAINS | 309 |
| IMPORTS | 302 |
| ATTR_ACCESS | 1403 |
| INHERITS | 6 |

---

## Fan-In Ranking

Most-called functions are potential bottlenecks or core functionality. These functions are heavily depended upon across the codebase.

| # | Function | Module | Callers |
|---|----------|--------|---------|
| 1 | `run()` | runpod/build_kg.py | **10** |
| 2 | `info()` | runpod/build_kg.py | **8** |
| 3 | `step()` | runpod/build_kg.py | **7** |
| 4 | `_c()` | runpod/build_kg.py | **4** |
| 5 | `collect_genre_stats()` | src/gutenberg_kg/corpus.py | **4** |
| 6 | `fetch_url()` | src/gutenberg_kg/gutenberg.py | **4** |
| 7 | `edges()` | src/gutenberg_kg/ingest.py | **3** |
| 8 | `nodes()` | src/gutenberg_kg/ingest.py | **3** |
| 9 | `_clear_highlight()` | src/gutenberg_kg/viz3d.py | **3** |
| 10 | `_count_authors()` | src/gutenberg_kg/corpus.py | **3** |
| 11 | `blank()` | runpod/build_kg.py | **3** |
| 12 | `load_snapshots_timeline()` | src/gutenberg_kg/viz_timeline.py | **3** |
| 13 | `fetch_url()` | src/gutenberg_kg/ia.py | **3** |
| 14 | `download_book()` | src/gutenberg_kg/gutenberg.py | **3** |
| 15 | `fmt_duration()` | src/gutenberg_kg/ingest.py | **3** |


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
| `src/gutenberg_kg/viz3d.py` | 8 | 5 | 0 | 0 | 0.00 |
| `src/gutenberg_kg/ingest.py` | 18 | 5 | 3 | 0 | 0.75 |
| `src/gutenberg_kg/corpus.py` | 14 | 1 | 3 | 1 | 0.60 |
| `src/gutenberg_kg/gutenberg.py` | 20 | 0 | 1 | 1 | 0.33 |
| `runpod/build_kg.py` | 19 | 0 | 2 | 0 | 0.67 |
| `src/gutenberg_kg/ia.py` | 18 | 0 | 1 | 1 | 0.33 |
| `docker/chat.py` | 16 | 0 | 0 | 0 | 0.00 |
| `docker/handler.py` | 10 | 0 | 0 | 0 | 0.00 |
| `src/gutenberg_kg/cli/cmd_snapshot.py` | 10 | 0 | 1 | 2 | 0.25 |
| `runpod/handler.py` | 9 | 0 | 0 | 0 | 0.00 |

---

## Key Call Chains

Deepest call chains in the codebase.

No deep call chains detected.

---

## Public API Surface

Identified public APIs (module-level functions with high usage).

| Function | Module | Fan-In | Type |
|----------|--------|--------|------|
| `run()` | runpod/build_kg.py | 10 | function |
| `info()` | runpod/build_kg.py | 8 | function |
| `step()` | runpod/build_kg.py | 7 | function |
| `collect_genre_stats()` | src/gutenberg_kg/corpus.py | 4 | function |
| `fetch_url()` | src/gutenberg_kg/gutenberg.py | 4 | function |
| `blank()` | runpod/build_kg.py | 3 | function |
| `load_snapshots_timeline()` | src/gutenberg_kg/viz_timeline.py | 3 | function |
| `fetch_url()` | src/gutenberg_kg/ia.py | 3 | function |
| `download_book()` | src/gutenberg_kg/gutenberg.py | 3 | function |
| `fmt_duration()` | src/gutenberg_kg/ingest.py | 3 | function |
---

## Docstring Coverage

Docstring coverage directly determines semantic retrieval quality. Nodes without
docstrings embed only structured identifiers (`KIND/NAME/QUALNAME/MODULE`), where
keyword search is as effective as vector embeddings. The semantic model earns its
value only when a docstring is present.

| Kind | Documented | Total | Coverage |
|------|-----------|-------|----------|
| `function` | 163 | 235 | [WARN] 69.4% |
| `method` | 21 | 59 | [LOW] 35.6% |
| `class` | 14 | 15 | [OK] 93.3% |
| `module` | 35 | 37 | [OK] 94.6% |
| **total** | **233** | **346** | **[WARN] 67.3%** |

> **Recommendation:** 113 nodes lack docstrings. Prioritize documenting high-fan-in functions and public API surface first — these have the highest impact on query accuracy.

---

## Structural Importance Ranking (SIR)

Weighted PageRank aggregated by module — reveals architectural spine. Cross-module edges boosted 1.5×; private symbols penalized 0.85×. Node-level detail: `pycodekg centrality --top 25`

| Rank | Score | Members | Module |
|------|-------|---------|--------|
| 1 | 0.171586 | 38 | `src/gutenberg_kg/ingest.py` |
| 2 | 0.143804 | 54 | `src/gutenberg_kg/viz3d.py` |
| 3 | 0.095636 | 21 | `src/gutenberg_kg/corpus.py` |
| 4 | 0.081697 | 20 | `runpod/build_kg.py` |
| 5 | 0.076298 | 21 | `src/gutenberg_kg/gutenberg.py` |
| 6 | 0.054441 | 19 | `src/gutenberg_kg/ia.py` |
| 7 | 0.029781 | 17 | `docker/chat.py` |
| 8 | 0.028465 | 9 | `src/gutenberg_kg/authors.py` |
| 9 | 0.023203 | 9 | `src/gutenberg_kg/build_diaries.py` |
| 10 | 0.022766 | 9 | `src/gutenberg_kg/build_corpus.py` |
| 11 | 0.021452 | 9 | `src/gutenberg_kg/viz_timeline.py` |
| 12 | 0.020081 | 6 | `src/gutenberg_kg/image_gen.py` |
| 13 | 0.020071 | 5 | `src/gutenberg_kg/genres.py` |
| 14 | 0.019537 | 11 | `docker/handler.py` |
| 15 | 0.019441 | 11 | `src/gutenberg_kg/cli/cmd_snapshot.py` |



---

## Code Quality Issues

- [WARN] Moderate docstring coverage (67.3%) — semantic retrieval quality is degraded for undocumented nodes; BM25 is as effective as embeddings without docstrings
- [WARN] `viz3d.py` has 53 functions/methods/classes -- consider splitting into focused submodules
- [WARN] `ingest.py` has 37 functions/methods/classes -- consider splitting into focused submodules

---

## Architectural Strengths

- Well-structured with 15 core functions identified
- No obvious dead code detected
- No god objects or god functions detected

---

## Recommendations

### Immediate Actions
1. **Improve docstring coverage** — 113 nodes lack docstrings; prioritize high-fan-in functions and public APIs first for maximum semantic retrieval gain

### Medium-term Refactoring
1. **Harden high fan-in functions** — `run`, `info`, `step` are widely depended upon; review for thread safety, clear contracts, and stable interfaces
2. **Reduce module coupling** — consider splitting tightly coupled modules or introducing interface boundaries

### Long-term Architecture
1. **Version and stabilize the public API** — document breaking-change policies for `run`, `info`, `step`
2. **Enforce layer boundaries** — add linting or CI checks to prevent unexpected cross-module dependencies as the codebase grows
3. **Monitor hot paths** — instrument the high fan-in functions identified here to catch performance regressions early

---

## Inheritance Hierarchy

**6** INHERITS edges across **6** classes. Max depth: **0**.

| Class | Module | Depth | Parents | Children |
|-------|--------|-------|---------|----------|
| `ImageGenRequest` | docker/image_server.py | 0 | 1 | 0 |
| `GutenbergSnapshotManager` | src/gutenberg_kg/corpus.py | 0 | 1 | 0 |
| `ForestLayout` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |
| `ForestMainWindow` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |
| `GutenbergForestVisualizer` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |
| `TextPopup` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |


---

## Snapshot History

Recent snapshots in reverse chronological order. Δ columns show change vs. the immediately preceding snapshot.

| # | Timestamp | Branch | Version | Nodes | Edges | Coverage | Δ Nodes | Δ Edges | Δ Coverage |
|---|-----------|--------|---------|-------|-------|----------|---------|---------|------------|
| 1 | 2026-06-06 01:27:01 | main | 0.19.2 | 3868 | 3254 | 75.6% | — | — | — |


---

## Appendix: Orphaned Code

Functions with zero callers (potential dead code):

No orphaned functions detected.
---

## CodeRank -- Global Structural Importance

Weighted PageRank over CALLS + IMPORTS + INHERITS edges (test paths excluded). Scores are normalized to sum to 1.0. This ranking seeds Phase 2 fan-in discovery and Phase 15 concern queries.

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.000869 | function | `_c` | runpod/build_kg.py |
| 2 | 0.000455 | method | `GenreSummary.nodes` | src/gutenberg_kg/ingest.py |
| 3 | 0.000455 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 4 | 0.000436 | function | `step` | runpod/build_kg.py |
| 5 | 0.000429 | method | `GenreSummary.elapsed` | src/gutenberg_kg/ingest.py |
| 6 | 0.000390 | function | `run` | runpod/build_kg.py |
| 7 | 0.000386 | function | `info` | runpod/build_kg.py |
| 8 | 0.000372 | method | `ForestMainWindow._clear_highlight` | src/gutenberg_kg/viz3d.py |
| 9 | 0.000327 | function | `survey_repo` | src/gutenberg_kg/gutenberg.py |
| 10 | 0.000327 | function | `_save` | src/gutenberg_kg/genres.py |
| 11 | 0.000298 | method | `BookMeta.db_path` | src/gutenberg_kg/viz3d.py |
| 12 | 0.000285 | function | `slugify` | src/gutenberg_kg/gutenberg.py |
| 13 | 0.000280 | function | `_count_authors` | src/gutenberg_kg/corpus.py |
| 14 | 0.000280 | function | `collect_genre_stats` | src/gutenberg_kg/corpus.py |
| 15 | 0.000265 | function | `_fmt_badge_nodes` | src/gutenberg_kg/cli/cmd_status.py |
| 16 | 0.000263 | function | `blank` | runpod/build_kg.py |
| 17 | 0.000262 | function | `load_snapshots_timeline` | src/gutenberg_kg/viz_timeline.py |
| 18 | 0.000257 | function | `_field` | src/gutenberg_kg/authors.py |
| 19 | 0.000256 | function | `fetch_url` | src/gutenberg_kg/ia.py |
| 20 | 0.000252 | function | `_du` | runpod/build_kg.py |

---

## Concern-Based Hybrid Ranking

Top structurally-dominant nodes per architectural concern (0.60 × semantic + 0.25 × CodeRank + 0.15 × graph proximity).

### Configuration Loading Initialization Setup

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7519 | function | `setup_env` | runpod/build_kg.py |
| 2 | 0.7372 | function | `_load_model` | docker/image_gen.py |
| 3 | 0.7188 | function | `install_system_deps` | runpod/build_kg.py |
| 4 | 0.7171 | function | `_load_model` | src/gutenberg_kg/image_gen.py |
| 5 | 0.717 | function | `_load_catalog` | runpod/handler.py |

### Data Persistence Storage Database

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.75 | method | `GutenbergSnapshotManager.save_snapshot` | src/gutenberg_kg/corpus.py |
| 2 | 0.7439 | function | `snapshot_save` | src/gutenberg_kg/cli/cmd_snapshot.py |
| 3 | 0.7274 | method | `GutenbergSnapshotManager.capture` | src/gutenberg_kg/corpus.py |
| 4 | 0.7235 | function | `snapshot_save` | src/gutenberg_kg/corpus.py |
| 5 | 0.7193 | function | `_dir_size_mb` | src/gutenberg_kg/build_corpus.py |

### Query Search Retrieval Semantic

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7514 | function | `_query_corpus` | src/gutenberg_kg/cli/cmd_imagine.py |
| 2 | 0.75 | function | `ia_search` | src/gutenberg_kg/cli/cmd_ia.py |
| 3 | 0.7408 | function | `download_search` | src/gutenberg_kg/cli/cmd_download.py |
| 4 | 0.7319 | function | `search_ia` | src/gutenberg_kg/ia.py |
| 5 | 0.7232 | function | `run_search` | src/gutenberg_kg/gutenberg.py |

### Graph Traversal Node Edge

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7819 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 2 | 0.7501 | function | `create_forest_visualization` | src/gutenberg_kg/viz3d.py |
| 3 | 0.75 | method | `ForestLayout.compute` | src/gutenberg_kg/viz3d.py |
| 4 | 0.722 | function | `_load_book_graph` | src/gutenberg_kg/viz3d.py |
| 5 | 0.7211 | method | `GutenbergForestVisualizer.load_selected` | src/gutenberg_kg/viz3d.py |



---

*Report generated by PyCodeKG Thorough Analysis Tool — analysis completed in 6.7s*
