> **Analysis Report Metadata**
> - **Generated:** 2026-05-13T00:42:42Z
> - **Version:** pycode-kg 0.19.0
> - **Commit:** 76ea9f4 (main)
> - **Platform:** macOS 26.4.1 | arm64 (arm) | turing | Python 3.12.13
> - **Graph:** 3305 nodes · 2774 edges (215 meaningful)
> - **Included directories:** src
> - **Excluded directories:** none
> - **Elapsed time:** 7s

# gutenberg_kg Analysis

**Generated:** 2026-05-13 00:42:42 UTC

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
| **Total Nodes** | 3305 |
| **Total Edges** | 2774 |
| **Modules** | 22 (of 22 total) |
| **Functions** | 138 |
| **Classes** | 8 |
| **Methods** | 47 |

### Edge Distribution

| Relationship Type | Count |
|-------------------|-------|
| CALLS | 1204 |
| CONTAINS | 193 |
| IMPORTS | 175 |
| ATTR_ACCESS | 893 |
| INHERITS | 4 |

---

## Fan-In Ranking

Most-called functions are potential bottlenecks or core functionality. These functions are heavily depended upon across the codebase.

| # | Function | Module | Callers |
|---|----------|--------|---------|
| 1 | `fetch_url()` | src/gutenberg_kg/gutenberg.py | **4** |
| 2 | `edges()` | src/gutenberg_kg/ingest.py | **3** |
| 3 | `nodes()` | src/gutenberg_kg/ingest.py | **3** |
| 4 | `_clear_highlight()` | src/gutenberg_kg/viz3d.py | **3** |
| 5 | `load_snapshots_timeline()` | src/gutenberg_kg/viz_timeline.py | **3** |
| 6 | `fetch_url()` | src/gutenberg_kg/ia.py | **3** |
| 7 | `collect_genre_stats()` | src/gutenberg_kg/corpus.py | **3** |
| 8 | `download_book()` | src/gutenberg_kg/gutenberg.py | **3** |
| 9 | `fmt_duration()` | src/gutenberg_kg/ingest.py | **3** |
| 10 | `failed()` | src/gutenberg_kg/ingest.py | **3** |
| 11 | `reset_camera()` | src/gutenberg_kg/viz3d.py | **3** |
| 12 | `elapsed()` | src/gutenberg_kg/ingest.py | **2** |
| 13 | `_save()` | src/gutenberg_kg/genres.py | **2** |
| 14 | `db_path()` | src/gutenberg_kg/viz3d.py | **2** |
| 15 | `slugify()` | src/gutenberg_kg/gutenberg.py | **2** |


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
| `src/gutenberg_kg/ingest.py` | 14 | 3 | 1 | 0 | 0.50 |
| `src/gutenberg_kg/gutenberg.py` | 20 | 0 | 1 | 0 | 0.50 |
| `src/gutenberg_kg/ia.py` | 18 | 0 | 1 | 0 | 0.50 |
| `src/gutenberg_kg/corpus.py` | 13 | 0 | 3 | 0 | 0.75 |
| `src/gutenberg_kg/cli/cmd_snapshot.py` | 9 | 0 | 1 | 2 | 0.25 |
| `src/gutenberg_kg/authors.py` | 8 | 0 | 1 | 0 | 0.50 |
| `src/gutenberg_kg/cli/cmd_status.py` | 8 | 0 | 1 | 2 | 0.25 |
| `src/gutenberg_kg/viz_timeline.py` | 8 | 0 | 0 | 1 | 0.00 |
| `src/gutenberg_kg/cli/cmd_download.py` | 6 | 0 | 1 | 2 | 0.25 |

---

## Key Call Chains

Deepest call chains in the codebase.

**Chain 1** (depth: 3)

```
create_timeline_figure → load_snapshots_timeline → snapshot_list
```

---

## Public API Surface

Identified public APIs (module-level functions with high usage).

| Function | Module | Fan-In | Type |
|----------|--------|--------|------|
| `fetch_url()` | src/gutenberg_kg/gutenberg.py | 4 | function |
| `load_snapshots_timeline()` | src/gutenberg_kg/viz_timeline.py | 3 | function |
| `fetch_url()` | src/gutenberg_kg/ia.py | 3 | function |
| `collect_genre_stats()` | src/gutenberg_kg/corpus.py | 3 | function |
| `download_book()` | src/gutenberg_kg/gutenberg.py | 3 | function |
| `fmt_duration()` | src/gutenberg_kg/ingest.py | 3 | function |
| `build()` | src/gutenberg_kg/authors.py | 2 | function |
| `slugify()` | src/gutenberg_kg/gutenberg.py | 2 | function |
| `launch()` | src/gutenberg_kg/viz3d.py | 1 | function |
| `cli()` | src/gutenberg_kg/cli/main.py | 0 | function |
---

## Docstring Coverage

Docstring coverage directly determines semantic retrieval quality. Nodes without
docstrings embed only structured identifiers (`KIND/NAME/QUALNAME/MODULE`), where
keyword search is as effective as vector embeddings. The semantic model earns its
value only when a docstring is present.

| Kind | Documented | Total | Coverage |
|------|-----------|-------|----------|
| `function` | 122 | 138 | [OK] 88.4% |
| `method` | 17 | 47 | [LOW] 36.2% |
| `class` | 8 | 8 | [OK] 100.0% |
| `module` | 20 | 22 | [OK] 90.9% |
| **total** | **167** | **215** | **[WARN] 77.7%** |

> **Recommendation:** 48 nodes lack docstrings. Prioritize documenting high-fan-in functions and public API surface first — these have the highest impact on query accuracy.

---

## Structural Importance Ranking (SIR)

Weighted PageRank aggregated by module — reveals architectural spine. Cross-module edges boosted 1.5×; private symbols penalized 0.85×. Node-level detail: `pycodekg centrality --top 25`

| Rank | Score | Members | Module |
|------|-------|---------|--------|
| 1 | 0.265165 | 54 | `src/gutenberg_kg/viz3d.py` |
| 2 | 0.149321 | 25 | `src/gutenberg_kg/ingest.py` |
| 3 | 0.124448 | 21 | `src/gutenberg_kg/gutenberg.py` |
| 4 | 0.090086 | 19 | `src/gutenberg_kg/ia.py` |
| 5 | 0.086899 | 14 | `src/gutenberg_kg/corpus.py` |
| 6 | 0.045680 | 9 | `src/gutenberg_kg/authors.py` |
| 7 | 0.034497 | 9 | `src/gutenberg_kg/viz_timeline.py` |
| 8 | 0.031040 | 5 | `src/gutenberg_kg/genres.py` |
| 9 | 0.026362 | 10 | `src/gutenberg_kg/cli/cmd_snapshot.py` |
| 10 | 0.025398 | 9 | `src/gutenberg_kg/cli/cmd_status.py` |
| 11 | 0.020624 | 7 | `src/gutenberg_kg/cli/options.py` |
| 12 | 0.019576 | 7 | `src/gutenberg_kg/cli/cmd_download.py` |
| 13 | 0.016846 | 6 | `src/gutenberg_kg/cli/cmd_ia.py` |
| 14 | 0.016434 | 2 | `src/gutenberg_kg/cli/main.py` |
| 15 | 0.014099 | 5 | `src/gutenberg_kg/cli/cmd_genres.py` |



---

## Code Quality Issues

- [WARN] Moderate docstring coverage (77.7%) — semantic retrieval quality is degraded for undocumented nodes; BM25 is as effective as embeddings without docstrings
- [WARN] `viz3d.py` has 53 functions/methods/classes -- consider splitting into focused submodules

---

## Architectural Strengths

- Well-structured with 15 core functions identified
- No obvious dead code detected
- No god objects or god functions detected

---

## Recommendations

### Immediate Actions
1. **Improve docstring coverage** — 48 nodes lack docstrings; prioritize high-fan-in functions and public APIs first for maximum semantic retrieval gain

### Medium-term Refactoring
1. **Harden high fan-in functions** — `fetch_url`, `edges`, `nodes` are widely depended upon; review for thread safety, clear contracts, and stable interfaces
2. **Reduce module coupling** — consider splitting tightly coupled modules or introducing interface boundaries
3. **Add tests for key call chains** — the identified call chains represent well-traveled execution paths that benefit most from regression coverage

### Long-term Architecture
1. **Version and stabilize the public API** — document breaking-change policies for `fetch_url`, `load_snapshots_timeline`, `fetch_url`
2. **Enforce layer boundaries** — add linting or CI checks to prevent unexpected cross-module dependencies as the codebase grows
3. **Monitor hot paths** — instrument the high fan-in functions identified here to catch performance regressions early

---

## Inheritance Hierarchy

**4** INHERITS edges across **4** classes. Max depth: **0**.

| Class | Module | Depth | Parents | Children |
|-------|--------|-------|---------|----------|
| `ForestLayout` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |
| `ForestMainWindow` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |
| `GutenbergForestVisualizer` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |
| `TextPopup` | src/gutenberg_kg/viz3d.py | 0 | 1 | 0 |


---

## Snapshot History

No snapshots found. Run `pycodekg snapshot save <version>` to capture one.


---

## Appendix: Orphaned Code

Functions with zero callers (potential dead code):

No orphaned functions detected.
---

## CodeRank -- Global Structural Importance

Weighted PageRank over CALLS + IMPORTS + INHERITS edges (test paths excluded). Scores are normalized to sum to 1.0. This ranking seeds Phase 2 fan-in discovery and Phase 15 concern queries.

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.000742 | method | `GenreSummary.nodes` | src/gutenberg_kg/ingest.py |
| 2 | 0.000742 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 3 | 0.000699 | method | `GenreSummary.elapsed` | src/gutenberg_kg/ingest.py |
| 4 | 0.000604 | method | `ForestMainWindow._clear_highlight` | src/gutenberg_kg/viz3d.py |
| 5 | 0.000530 | function | `survey_repo` | src/gutenberg_kg/gutenberg.py |
| 6 | 0.000530 | function | `_save` | src/gutenberg_kg/genres.py |
| 7 | 0.000483 | method | `BookMeta.db_path` | src/gutenberg_kg/viz3d.py |
| 8 | 0.000462 | function | `slugify` | src/gutenberg_kg/gutenberg.py |
| 9 | 0.000430 | function | `_fmt_badge_nodes` | src/gutenberg_kg/cli/cmd_status.py |
| 10 | 0.000425 | function | `load_snapshots_timeline` | src/gutenberg_kg/viz_timeline.py |
| 11 | 0.000416 | function | `_field` | src/gutenberg_kg/authors.py |
| 12 | 0.000415 | function | `fetch_url` | src/gutenberg_kg/ia.py |
| 13 | 0.000408 | method | `GutenbergForestVisualizer._load_catalogue` | src/gutenberg_kg/viz3d.py |
| 14 | 0.000401 | function | `fetch_url` | src/gutenberg_kg/gutenberg.py |
| 15 | 0.000390 | method | `BookMeta.slug` | src/gutenberg_kg/viz3d.py |
| 16 | 0.000386 | function | `_slugify` | src/gutenberg_kg/authors.py |
| 17 | 0.000385 | function | `_count_authors` | src/gutenberg_kg/corpus.py |
| 18 | 0.000385 | function | `_git_info` | src/gutenberg_kg/corpus.py |
| 19 | 0.000385 | function | `collect_genre_stats` | src/gutenberg_kg/corpus.py |
| 20 | 0.000384 | method | `ForestMainWindow.cleanup` | src/gutenberg_kg/viz3d.py |

---

## Concern-Based Hybrid Ranking

Top structurally-dominant nodes per architectural concern (0.60 × semantic + 0.25 × CodeRank + 0.15 × graph proximity).

### Configuration Loading Initialization Setup

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7376 | function | `_load` | src/gutenberg_kg/genres.py |
| 2 | 0.7288 | function | `ingest` | src/gutenberg_kg/cli/cmd_ingest.py |
| 3 | 0.7125 | function | `force_build_option` | src/gutenberg_kg/cli/options.py |

### Data Persistence Storage Database

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.75 | function | `build` | src/gutenberg_kg/authors.py |
| 2 | 0.7476 | function | `ensure_corpus` | src/gutenberg_kg/ingest.py |
| 3 | 0.7443 | function | `write_reference` | src/gutenberg_kg/gutenberg.py |
| 4 | 0.741 | function | `is_sqlite_valid` | src/gutenberg_kg/ingest.py |
| 5 | 0.7409 | function | `write_reference` | src/gutenberg_kg/ia.py |

### Query Search Retrieval Semantic

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7561 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 2 | 0.75 | function | `ia_search` | src/gutenberg_kg/cli/cmd_ia.py |
| 3 | 0.7408 | function | `download_search` | src/gutenberg_kg/cli/cmd_download.py |
| 4 | 0.7319 | function | `search_ia` | src/gutenberg_kg/ia.py |
| 5 | 0.7232 | function | `run_search` | src/gutenberg_kg/gutenberg.py |

### Graph Traversal Node Edge

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.8174 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 2 | 0.7845 | method | `GenreSummary.nodes` | src/gutenberg_kg/ingest.py |
| 3 | 0.7042 | function | `_sqlite_counts` | src/gutenberg_kg/ingest.py |
| 4 | 0.6982 | function | `download_group` | src/gutenberg_kg/cli/cmd_download.py |
| 5 | 0.6974 | function | `_detect_toc` | src/gutenberg_kg/gutenberg.py |



---

*Report generated by PyCodeKG Thorough Analysis Tool — analysis completed in 7.4s*
