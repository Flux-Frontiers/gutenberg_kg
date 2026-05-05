> **Analysis Report Metadata**
> - **Generated:** 2026-05-05T22:14:14Z
> - **Version:** pycode-kg 0.19.0
> - **Commit:** e752d88b (develop)
> - **Platform:** macOS 26.4.1 | arm64 (arm) | turing | Python 3.13.12
> - **Graph:** 1731 nodes · 1411 edges (115 meaningful)
> - **Included directories:** src
> - **Excluded directories:** none
> - **Elapsed time:** 3s

# gutenberg_kg Analysis

**Generated:** 2026-05-05 22:14:14 UTC

---

## Executive Summary

This report provides a comprehensive architectural analysis of the **gutenberg_kg** repository using PyCodeKG's knowledge graph. The analysis covers complexity hotspots, module coupling, key call chains, and code quality signals to guide refactoring and architecture decisions.

| Overall Quality | Grade | Score |
|----------------|-------|-------|
| [A] **Excellent** | **A** | 100 / 100 |

---

## Baseline Metrics

| Metric | Value |
|--------|-------|
| **Total Nodes** | 1731 |
| **Total Edges** | 1411 |
| **Modules** | 15 (of 15 total) |
| **Functions** | 90 |
| **Classes** | 3 |
| **Methods** | 7 |

### Edge Distribution

| Relationship Type | Count |
|-------------------|-------|
| CALLS | 661 |
| CONTAINS | 100 |
| IMPORTS | 85 |
| ATTR_ACCESS | 398 |
| INHERITS | 0 |

---

## Fan-In Ranking

Most-called functions are potential bottlenecks or core functionality. These functions are heavily depended upon across the codebase.

| # | Function | Module | Callers |
|---|----------|--------|---------|
| 1 | `fetch_url()` | src/gutenberg_kg/gutenberg.py | **4** |
| 2 | `edges()` | src/gutenberg_kg/ingest.py | **3** |
| 3 | `elapsed()` | src/gutenberg_kg/ingest.py | **3** |
| 4 | `nodes()` | src/gutenberg_kg/ingest.py | **3** |
| 5 | `fetch_url()` | src/gutenberg_kg/ia.py | **3** |
| 6 | `download_book()` | src/gutenberg_kg/gutenberg.py | **3** |
| 7 | `fmt_duration()` | src/gutenberg_kg/ingest.py | **3** |
| 8 | `failed()` | src/gutenberg_kg/ingest.py | **3** |
| 9 | `_save()` | src/gutenberg_kg/genres.py | **2** |
| 10 | `slugify()` | src/gutenberg_kg/gutenberg.py | **2** |
| 11 | `_slugify()` | src/gutenberg_kg/authors.py | **2** |
| 12 | `_load()` | src/gutenberg_kg/genres.py | **2** |
| 13 | `search_gutenberg()` | src/gutenberg_kg/gutenberg.py | **2** |
| 14 | `_coerce_str()` | src/gutenberg_kg/ia.py | **2** |
| 15 | `built()` | src/gutenberg_kg/ingest.py | **2** |


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
| `src/gutenberg_kg/ingest.py` | 14 | 3 | 1 | 0 | 0.50 |
| `src/gutenberg_kg/gutenberg.py` | 20 | 0 | 1 | 0 | 0.50 |
| `src/gutenberg_kg/ia.py` | 18 | 0 | 1 | 0 | 0.50 |
| `src/gutenberg_kg/authors.py` | 8 | 0 | 1 | 0 | 0.50 |
| `src/gutenberg_kg/cli/cmd_download.py` | 6 | 0 | 1 | 2 | 0.25 |
| `src/gutenberg_kg/cli/options.py` | 6 | 0 | 0 | 0 | 0.00 |
| `src/gutenberg_kg/cli/cmd_ia.py` | 5 | 0 | 1 | 2 | 0.25 |
| `src/gutenberg_kg/cli/cmd_genres.py` | 4 | 0 | 1 | 2 | 0.25 |
| `src/gutenberg_kg/genres.py` | 4 | 0 | 1 | 0 | 0.50 |
| `src/gutenberg_kg/cli/cmd_ingest.py` | 2 | 0 | 1 | 2 | 0.25 |

---

## Key Call Chains

Deepest call chains in the codebase.

No deep call chains detected.

---

## Public API Surface

Identified public APIs (module-level functions with high usage).

| Function | Module | Fan-In | Type |
|----------|--------|--------|------|
| `fetch_url()` | src/gutenberg_kg/gutenberg.py | 4 | function |
| `fetch_url()` | src/gutenberg_kg/ia.py | 3 | function |
| `download_book()` | src/gutenberg_kg/gutenberg.py | 3 | function |
| `fmt_duration()` | src/gutenberg_kg/ingest.py | 3 | function |
| `slugify()` | src/gutenberg_kg/gutenberg.py | 2 | function |
| `search_gutenberg()` | src/gutenberg_kg/gutenberg.py | 2 | function |
| `build()` | src/gutenberg_kg/authors.py | 1 | function |
| `cli()` | src/gutenberg_kg/cli/main.py | 0 | function |
---

## Docstring Coverage

Docstring coverage directly determines semantic retrieval quality. Nodes without
docstrings embed only structured identifiers (`KIND/NAME/QUALNAME/MODULE`), where
keyword search is as effective as vector embeddings. The semantic model earns its
value only when a docstring is present.

| Kind | Documented | Total | Coverage |
|------|-----------|-------|----------|
| `function` | 84 | 90 | [OK] 93.3% |
| `method` | 7 | 7 | [OK] 100.0% |
| `class` | 3 | 3 | [OK] 100.0% |
| `module` | 13 | 15 | [OK] 86.7% |
| **total** | **107** | **115** | **[OK] 93.0%** |

---

## Structural Importance Ranking (SIR)

Weighted PageRank aggregated by module — reveals architectural spine. Cross-module edges boosted 1.5×; private symbols penalized 0.85×. Node-level detail: `pycodekg centrality --top 25`

| Rank | Score | Members | Module |
|------|-------|---------|--------|
| 1 | 0.277530 | 25 | `src/gutenberg_kg/ingest.py` |
| 2 | 0.227725 | 21 | `src/gutenberg_kg/gutenberg.py` |
| 3 | 0.166062 | 19 | `src/gutenberg_kg/ia.py` |
| 4 | 0.074847 | 9 | `src/gutenberg_kg/authors.py` |
| 5 | 0.057351 | 5 | `src/gutenberg_kg/genres.py` |
| 6 | 0.037959 | 7 | `src/gutenberg_kg/cli/options.py` |
| 7 | 0.036378 | 7 | `src/gutenberg_kg/cli/cmd_download.py` |
| 8 | 0.031342 | 6 | `src/gutenberg_kg/cli/cmd_ia.py` |
| 9 | 0.026276 | 5 | `src/gutenberg_kg/cli/cmd_genres.py` |
| 10 | 0.022174 | 2 | `src/gutenberg_kg/cli/main.py` |
| 11 | 0.016016 | 3 | `src/gutenberg_kg/cli/cmd_ingest.py` |
| 12 | 0.011181 | 2 | `src/gutenberg_kg/cli/cmd_rebuild.py` |
| 13 | 0.010799 | 2 | `src/gutenberg_kg/cli/cmd_authors.py` |
| 14 | 0.004110 | 1 | `src/gutenberg_kg/__init__.py` |
| 15 | 0.004110 | 1 | `src/gutenberg_kg/cli/__init__.py` |



---

## Code Quality Issues

- No major issues detected

---

## Architectural Strengths

- Well-structured with 15 core functions identified
- No obvious dead code detected
- No god objects or god functions detected
- Good docstring coverage: 93.0% of functions/methods/classes/modules documented

---

## Recommendations

### Medium-term Refactoring
1. **Harden high fan-in functions** — `fetch_url`, `edges`, `elapsed` are widely depended upon; review for thread safety, clear contracts, and stable interfaces
2. **Reduce module coupling** — consider splitting tightly coupled modules or introducing interface boundaries

### Long-term Architecture
1. **Version and stabilize the public API** — document breaking-change policies for `fetch_url`, `fetch_url`, `download_book`
2. **Enforce layer boundaries** — add linting or CI checks to prevent unexpected cross-module dependencies as the codebase grows
3. **Monitor hot paths** — instrument the high fan-in functions identified here to catch performance regressions early

---

## Inheritance Hierarchy

No inheritance edges (no class hierarchies).


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
| 1 | 0.001414 | method | `GenreSummary.elapsed` | src/gutenberg_kg/ingest.py |
| 2 | 0.001414 | method | `GenreSummary.nodes` | src/gutenberg_kg/ingest.py |
| 3 | 0.001414 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 4 | 0.001008 | function | `survey_repo` | src/gutenberg_kg/gutenberg.py |
| 5 | 0.001008 | function | `_save` | src/gutenberg_kg/genres.py |
| 6 | 0.000880 | function | `slugify` | src/gutenberg_kg/gutenberg.py |
| 7 | 0.000792 | function | `_field` | src/gutenberg_kg/authors.py |
| 8 | 0.000789 | function | `fetch_url` | src/gutenberg_kg/ia.py |
| 9 | 0.000762 | function | `fetch_url` | src/gutenberg_kg/gutenberg.py |
| 10 | 0.000734 | function | `_slugify` | src/gutenberg_kg/authors.py |
| 11 | 0.000712 | function | `download_book` | src/gutenberg_kg/gutenberg.py |
| 12 | 0.000699 | function | `_load` | src/gutenberg_kg/genres.py |
| 13 | 0.000695 | function | `search_gutenberg` | src/gutenberg_kg/gutenberg.py |
| 14 | 0.000677 | function | `parse_catalog` | src/gutenberg_kg/gutenberg.py |
| 15 | 0.000675 | function | `_coerce_str` | src/gutenberg_kg/ia.py |
| 16 | 0.000660 | function | `fmt_duration` | src/gutenberg_kg/ingest.py |
| 17 | 0.000659 | function | `find_text_file` | src/gutenberg_kg/ia.py |
| 18 | 0.000652 | function | `_survey_book_dir` | src/gutenberg_kg/gutenberg.py |
| 19 | 0.000652 | function | `_check_mark` | src/gutenberg_kg/gutenberg.py |
| 20 | 0.000644 | method | `GenreSummary.failed` | src/gutenberg_kg/ingest.py |

---

## Concern-Based Hybrid Ranking

Top structurally-dominant nodes per architectural concern (0.60 × semantic + 0.25 × CodeRank + 0.15 × graph proximity).

### Configuration Loading Initialization Setup

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7382 | function | `_load` | src/gutenberg_kg/genres.py |
| 2 | 0.7288 | function | `ingest` | src/gutenberg_kg/cli/cmd_ingest.py |
| 3 | 0.7125 | function | `force_build_option` | src/gutenberg_kg/cli/options.py |

### Data Persistence Storage Database

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.75 | function | `build` | src/gutenberg_kg/authors.py |
| 2 | 0.7478 | function | `ensure_corpus` | src/gutenberg_kg/ingest.py |
| 3 | 0.7445 | function | `write_reference` | src/gutenberg_kg/gutenberg.py |
| 4 | 0.7412 | function | `is_sqlite_valid` | src/gutenberg_kg/ingest.py |
| 5 | 0.7411 | function | `write_reference` | src/gutenberg_kg/ia.py |

### Query Search Retrieval Semantic

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.7598 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 2 | 0.75 | function | `ia_search` | src/gutenberg_kg/cli/cmd_ia.py |
| 3 | 0.7408 | function | `download_search` | src/gutenberg_kg/cli/cmd_download.py |
| 4 | 0.7319 | function | `search_ia` | src/gutenberg_kg/ia.py |
| 5 | 0.7232 | function | `run_search` | src/gutenberg_kg/gutenberg.py |

### Graph Traversal Node Edge

| Rank | Score | Kind | Name | Module |
|------|-------|------|------|--------|
| 1 | 0.8269 | method | `GenreSummary.edges` | src/gutenberg_kg/ingest.py |
| 2 | 0.7941 | method | `GenreSummary.nodes` | src/gutenberg_kg/ingest.py |
| 3 | 0.7047 | function | `_sqlite_counts` | src/gutenberg_kg/ingest.py |
| 4 | 0.6982 | function | `download_group` | src/gutenberg_kg/cli/cmd_download.py |
| 5 | 0.6978 | function | `_detect_toc` | src/gutenberg_kg/gutenberg.py |



---

*Report generated by PyCodeKG Thorough Analysis Tool — analysis completed in 3.6s*
