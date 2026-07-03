> **Analysis Report Metadata**
> - **Generated:** 2026-07-03T00:08:55Z
> - **Version:** pycode-kg 0.19.3
> - **Commit:** 865a907 (main)
> - **Platform:** macOS 27.0 | arm64 (arm) | turing | Python 3.12.13
> - **Graph:** 6173 nodes · 5245 edges (412 meaningful)
> - **Included directories:** docker, runpod, src
> - **Excluded directories:** none
> - **Elapsed time:** 6s

# gutenberg_kg Analysis

**Generated:** 2026-07-03 00:08:55 UTC

---

## Executive Summary

This report provides a comprehensive architectural analysis of the **gutenberg_kg** repository using PyCodeKG's knowledge graph. The analysis covers complexity hotspots, module coupling, key call chains, and code quality signals to guide refactoring and architecture decisions.

| Overall Quality | Grade | Score |
|----------------|-------|-------|
| [A] **Excellent** | **A** | 90 / 100 |

---

## Baseline Metrics

| Metric | Value |
|--------|-------|
| **Total Nodes** | 6173 |
| **Total Edges** | 5245 |
| **Modules** | 44 (of 44 total) |
| **Functions** | 271 |
| **Classes** | 24 |
| **Methods** | 73 |

### Edge Distribution

| Relationship Type | Count |
|-------------------|-------|
| CALLS | 2256 |
| CONTAINS | 368 |
| IMPORTS | 347 |
| ATTR_ACCESS | 1608 |
| INHERITS | 10 |

---

## Fan-In Ranking

Most-called functions are potential bottlenecks or core functionality. These functions are heavily depended upon across the codebase.

| # | Function | Module | Callers |
|---|----------|--------|---------|
| 1 | `run()` | runpod/build_kg.py | **10** |
| 2 | `info()` | runpod/build_kg.py | **8** |
| 3 | `step()` | runpod/build_kg.py | **7** |
| 4 | `_c()` | runpod/build_kg.py | **4** |
| 5 | `_month_num()` | src/gutenberg_kg/diary/parser.py | **4** |
| 6 | `collect_genre_stats()` | src/gutenberg_kg/corpus.py | **4** |
| 7 | `fetch_url()` | src/gutenberg_kg/gutenberg.py | **4** |
| 8 | `slugify()` | src/gutenberg_kg/ingest.py | **4** |
| 9 | `fmt_duration()` | src/gutenberg_kg/ingest.py | **4** |
| 10 | `edges()` | src/gutenberg_kg/ingest.py | **3** |
| 11 | `nodes()` | src/gutenberg_kg/ingest.py | **3** |
| 12 | `_clear_highlight()` | src/gutenberg_kg/viz3d.py | **3** |
| 13 | `_count_authors()` | src/gutenberg_kg/corpus.py | **3** |
| 14 | `blank()` | runpod/build_kg.py | **3** |
| 15 | `load_snapshots_timeline()` | src/gutenberg_kg/viz_timeline.py | **3** |


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
| `src/gutenberg_kg/ingest.py` | 20 | 5 | 5 | 0 | 0.83 |
| `src/gutenberg_kg/diary/parser.py` | 7 | 5 | 4 | 0 | 0.80 |
| `src/gutenberg_kg/corpus.py` | 14 | 1 | 3 | 1 | 0.60 |
| `src/gutenberg_kg/gutenberg.py` | 20 | 0 | 1 | 2 | 0.25 |
| `runpod/build_kg.py` | 19 | 0 | 2 | 0 | 0.67 |
| `src/gutenberg_kg/ia.py` | 18 | 0 | 1 | 2 | 0.25 |
| `docker/handler.py` | 17 | 0 | 0 | 1 | 0.00 |
| `docker/chat.py` | 16 | 0 | 0 | 0 | 0.00 |
| `runpod/handler.py` | 15 | 0 | 0 | 1 | 0.00 |

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
| `slugify()` | src/gutenberg_kg/ingest.py | 4 | function |
| `fmt_duration()` | src/gutenberg_kg/ingest.py | 4 | function |
| `parse()` | src/gutenberg_kg/diary/parser.py | 3 | function |
| `blank()` | runpod/build_kg.py | 3 | function |
| `load_snapshots_timeline()` | src/gutenberg_kg/viz_timeline.py | 3 | function |
---

## Docstring Coverage

Docstring coverage directly determines semantic retrieval quality. Nodes without
docstrings embed only structured identifiers (`KIND/NAME/QUALNAME/MODULE`), where
keyword search is as effective as vector embeddings. The semantic model earns its
value only when a docstring is present.

| Kind | Documented | Total | Coverage |
|------|-----------|-------|----------|
| `function` | 262 | 271 | [OK] 96.7% |
| `method` | 66 | 73 | [OK] 90.4% |
| `class` | 23 | 24 | [OK] 95.8% |
| `module` | 42 | 44 | [OK] 95.5% |
| **total** | **393** | **412** | **[OK] 95.4%** |

---

## Structural Importance Ranking (SIR)

Weighted PageRank aggregated by module — reveals architectural spine. Cross-module edges boosted 1.5×; private symbols penalized 0.85×. Node-level detail: `pycodekg centrality --top 25`

| Rank | Score | Members | Module |
|------|-------|---------|--------|
| 1 | 0.151067 | 40 | `src/gutenberg_kg/ingest.py` |
| 2 | 0.122338 | 54 | `src/gutenberg_kg/viz3d.py` |
| 3 | 0.081871 | 21 | `src/gutenberg_kg/corpus.py` |
| 4 | 0.069848 | 20 | `runpod/build_kg.py` |
| 5 | 0.064971 | 21 | `src/gutenberg_kg/gutenberg.py` |
| 6 | 0.061611 | 23 | `src/gutenberg_kg/diary/parser.py` |
| 7 | 0.046270 | 19 | `src/gutenberg_kg/ia.py` |
| 8 | 0.027964 | 13 | `src/gutenberg_kg/audit.py` |
| 9 | 0.026736 | 18 | `docker/handler.py` |
| 10 | 0.025573 | 17 | `docker/chat.py` |
| 11 | 0.025535 | 9 | `src/gutenberg_kg/authors.py` |
| 12 | 0.024255 | 16 | `runpod/handler.py` |
| 13 | 0.022700 | 9 | `src/gutenberg_kg/build_diaries.py` |
| 14 | 0.022030 | 10 | `src/gutenberg_kg/build_corpus.py` |
| 15 | 0.018418 | 9 | `src/gutenberg_kg/viz_timeline.py` |



---

## Code Quality Issues

- [WARN] 2 orphaned functions found (`_clean`, `ParsedEntry`) -- consider archiving or documenting
- [WARN] `viz3d.py` has 53 functions/methods/classes -- consider splitting into focused submodules
- [WARN] `ingest.py` has 39 functions/methods/classes -- consider splitting into focused submodules

---

## Architectural Strengths

- Well-structured with 15 core functions identified
- No god objects or god functions detected
- Good docstring coverage: 95.4% of functions/methods/classes/modules documented

---

## Recommendations

### Immediate Actions
1. **Remove or archive orphaned functions** — `_clean`, `ParsedEntry` have zero callers and add maintenance burden

### Medium-term Refactoring
1. **Harden high fan-in functions** — `run`, `info`, `step` are widely depended upon; review for thread safety, clear contracts, and stable interfaces
2. **Reduce module coupling** — consider splitting tightly coupled modules or introducing interface boundaries

### Long-term Architecture
1. **Version and stabilize the public API** — document breaking-change policies for `run`, `info`, `step`
2. **Enforce layer boundaries** — add linting or CI checks to prevent unexpected cross-module dependencies as the codebase grows
3. **Monitor hot paths** — instrument the high fan-in functions identified here to catch performance regressions early

---

## Inheritance Hierarchy

**10** INHERITS edges across **10** classes. Max depth: **1**.

| Class | Module | Depth | Parents | Children |
|-------|--------|-------|---------|----------|
| `BoswellParser` | src/gutenberg_kg/diary/parser.py | 1 | 1 | 0 |
| `EvelynParser` | src/gutenberg_kg/diary/parser.py | 1 | 1 | 0 |
| `PepysParser` | src/gutenberg_kg/diary/parser.py | 1 | 1 | 0 |
| `ImageGenRequest` | docker/image_server.py | 0 | 1 | 0 |
| `GutenbergSnapshotManager` | src/gutenberg_kg/corpus.py | 0 | 1 | 0 |
| `BaseDiaryParser` | src/gutenberg_kg/diary/parser.py | 0 | 1 | 3 |
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

| Function | Module | Lines |
|----------|--------|-------|
| `ParsedEntry()` | src/gutenberg_kg/diary/parser.py | 5 |
| `_clean()` | src/gutenberg_kg/diary/parser.py | 4 |
---

## CodeRank -- Global Structural Importance

Weighted PageRank over CALLS + IMPORTS + INHERITS edges (test paths excluded). Scores are normalized to sum to 1.0. This ranking seeds Phase 2 fan-in discovery and Phase 15 concern queries.

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.000754 | function | `_c` | runpod/build_kg.py |
| 2 | 0.000391 | method | `GenreSummary.nodes` | src/gutenberg_kg/ingest.py |
| 3 | 0.000391 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 4 | 0.000379 | function | `step` | runpod/build_kg.py |
| 5 | 0.000369 | method | `GenreSummary.elapsed` | src/gutenberg_kg/ingest.py |
| 6 | 0.000354 | function | `_month_num` | src/gutenberg_kg/diary/parser.py |
| 7 | 0.000339 | function | `run` | runpod/build_kg.py |
| 8 | 0.000335 | function | `info` | runpod/build_kg.py |
| 9 | 0.000323 | method | `ForestMainWindow._clear_highlight` | src/gutenberg_kg/viz3d.py |
| 10 | 0.000283 | function | `survey_repo` | src/gutenberg_kg/gutenberg.py |
| 11 | 0.000283 | function | `_save` | src/gutenberg_kg/genres.py |
| 12 | 0.000258 | method | `BookMeta.db_path` | src/gutenberg_kg/viz3d.py |
| 13 | 0.000247 | function | `slugify` | src/gutenberg_kg/gutenberg.py |
| 14 | 0.000243 | function | `_count_authors` | src/gutenberg_kg/corpus.py |
| 15 | 0.000243 | function | `collect_genre_stats` | src/gutenberg_kg/corpus.py |
| 16 | 0.000238 | class | `PepysParser` | src/gutenberg_kg/diary/parser.py |
| 17 | 0.000230 | function | `_fmt_badge_nodes` | src/gutenberg_kg/cli/cmd_status.py |
| 18 | 0.000228 | function | `blank` | runpod/build_kg.py |
| 19 | 0.000228 | function | `load_snapshots_timeline` | src/gutenberg_kg/viz_timeline.py |
| 20 | 0.000223 | function | `_field` | src/gutenberg_kg/authors.py |

---

## Concern-Based Hybrid Ranking

Top structurally-dominant nodes per architectural concern (0.60 × semantic + 0.25 × CodeRank + 0.15 × graph proximity).

### Configuration Loading Initialization Setup

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7518 | function | `setup_env` | runpod/build_kg.py |
| 2 | 0.7357 | function | `_load_model` | docker/image_gen.py |
| 3 | 0.7327 | function | `_init_state` | docker/chat.py |
| 4 | 0.7153 | function | `_load_model` | src/gutenberg_kg/image_gen.py |
| 5 | 0.7144 | function | `install_system_deps` | runpod/build_kg.py |

### Data Persistence Storage Database

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7526 | function | `_save` | src/gutenberg_kg/genres.py |
| 2 | 0.75 | method | `GutenbergSnapshotManager.save_snapshot` | src/gutenberg_kg/corpus.py |
| 3 | 0.7417 | method | `BookMeta.has_kg` | src/gutenberg_kg/viz3d.py |
| 4 | 0.7414 | function | `snapshot_save` | src/gutenberg_kg/cli/cmd_snapshot.py |
| 5 | 0.7332 | function | `_attach_diary_fields` | docker/handler.py |

### Query Search Retrieval Semantic

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7519 | function | `_semantic_search` | docker/handler.py |
| 2 | 0.722 | function | `_semantic_search_diaries` | docker/handler.py |
| 3 | 0.7121 | function | `_semantic_search` | runpod/handler.py |
| 4 | 0.7011 | function | `_query_corpus` | src/gutenberg_kg/cli/cmd_imagine.py |
| 5 | 0.6997 | function | `ia_search` | src/gutenberg_kg/cli/cmd_ia.py |

### Graph Traversal Node Edge

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.776 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 2 | 0.75 | method | `ForestLayout.compute` | src/gutenberg_kg/viz3d.py |
| 3 | 0.7489 | function | `create_forest_visualization` | src/gutenberg_kg/viz3d.py |
| 4 | 0.7216 | method | `GutenbergForestVisualizer.load_selected` | src/gutenberg_kg/viz3d.py |
| 5 | 0.7204 | function | `_load_book_graph` | src/gutenberg_kg/viz3d.py |



---

*Report generated by PyCodeKG Thorough Analysis Tool — analysis completed in 6.1s*
