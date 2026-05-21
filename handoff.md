# Handoff: SIMILAR_TO Evaluation + Corpus Quality (May 21, 2026)

## What Was Accomplished This Session

### 1. Sci-fi corpus bug fixed (critical)

Three science-fiction books had wrong Gutenberg IDs in the catalog files, causing
completely wrong books to be downloaded and ingested.

| Book dir | Wrong ID | Wrong content | Correct ID |
|---|---|---|---|
| The Lost World | 29808 | Robert Herrick novel | **139** (Doyle) |
| The Gods of Mars | 364 | ERB's The Mad King | **64** (Burroughs) |
| Pellucidar (Burroughs) | 4358 | L. Frank Baum Oz book | **605** (Burroughs) |

Fixed: `scripts/catalogs/science-fiction.txt` (IDs 29808→139, 364→64) and
`scripts/catalogs/science-fiction-additions.txt` (4358→605). Wrong content wiped,
correct books re-downloaded and ingested.

### 2. Johnson's Life of Samuel Johnson — DocKG built

`corpus/biography/The Life of Samuel Johnson — James Boswell/.dockg/` was missing.
Built via `gutenkg ingest --genre biography`. Now part of the eval set.

### 3. Labeled evaluation run (Step 2 of handoff)

Built 36-query gold set and ran `scripts/evaluate_similar_to_value.py`. Results:

| Condition | MRR@15 | nDCG@15 | Recall@15 | Build time | SIMILAR_TO edges |
|---|---|---|---|---|---|
| none | 0.2300 | 0.1283 | 0.120 | 0.40s | 0 |
| cap 8 | 0.2367 | 0.1355 | 0.134 | 3.86s | 2,851 |
| cap 15 | 0.2369 | 0.1356 | 0.134 | 3.85s | 3,894 |

Evaluator output: `analysis/similar_to_value_eval_*_20260521_024749.*`

Recommendation block: `adopt_default = true`, best_condition = "8", nDCG gain +5.6%.

Full memo written: `docs/SIMILAR_TO_CAP_RECOMMENDATION.md`

### 4. Gold-set calibration problem diagnosed

**The absolute MRR numbers (~0.23) are artificially depressed. Two causes:**

**Cause A — Node type dilution.** `kg.query()` returns 15 nodes but only ~4-6 are
`chunk:` nodes; the rest are `entity:`, `keyword:`, `topic:` nodes. All gold IDs
are `chunk:` IDs, so 9-11 slots can never score.

**Cause B — Keyword search ≠ semantic search.** The keyword-matched gold chunks
are not the ones semantic retrieval seeds on. Example: Meditations Q0014
("tranquility/death") seeds on the editor's introduction (chunks 0062–0068) but
the gold set contained aphorism chunks 0453–0586. Both are topically right but
semantic retrieval found a different region.

**Implication for the recommendation:** The *relative* delta between conditions is
still valid (same calibration error across all conditions). Cap 8 recommendation
stands. Absolute numbers are a lower bound, not a true quality score.

**Confirmed:** Higher caps do not help. Cap 0→50 sweep shows completely flat MRR.
The bottleneck is gold-set calibration, not edge count.

### 5. Run-then-validate gold set tool written

`scripts/build_gold_from_retrieval.py` — interactive terminal session that:
- Runs each query under BASE (no SIMILAR_TO) and SIM (cap 8) conditions
- Pools returned chunk nodes, tags each [BASE] / [SIM ] / [BOTH]
- Shows full chunk text + query before every candidate
- Prompts y / n / s (skip) / q (quit)
- Writes validated IDs back to template CSV immediately after each query
- Resumes from where it left off (skips rows with `assessor=human`)

Current template state: 10 human-validated, 26 claude-keyword, 2 empty.

Usage:
```bash
poetry run python scripts/build_gold_from_retrieval.py          # resume
poetry run python scripts/build_gold_from_retrieval.py --force  # redo all
```

### 6. Corpus quality observation — intro/preface contamination

**Key finding:** Retrieval hits are heavily skewed toward introductory and prefatory
chunks rather than the main text. Examples seen:

- Meditations Q0014: returned chunks 0062–0068 (editor's intro about Aurelius's life)
  instead of the actual aphorisms
- Multiple queries hit `reference.md` chunks (bibliographic metadata) which score
  semantically relevant because they summarise the whole book

**Root cause:** Introductory text, prefaces, editor's notes, and `reference.md`
summaries are short, dense, thematically broad, and often contain exactly the
vocabulary of a well-formed query. They therefore dominate semantic seeds.

**Needed fix (general corpus quality task):**
Scan all markdown files and either:
1. Strip or separate intro/preface sections into a non-indexed node type, OR
2. Tag those chunks with `content_type=front_matter` and exclude them from semantic
   seeding (but keep for graph traversal context), OR
3. Implement a simple heuristic: exclude chunks from the first N% of a book's
   chunk sequence from seeding (configurable)

This affects retrieval quality across the entire corpus, not just this evaluation.

---

## Current Decision Status

**SIMILAR_TO recommendation: adopt_default = true, cap 8**
- Evidence is sufficient even with calibration caveats
- Memo written at `docs/SIMILAR_TO_CAP_RECOMMENDATION.md`
- Rollout plan is in that doc

**NOT yet done:**
- Complete human validation of gold set (10/36 done)
- Re-run evaluator after full human validation to get clean numbers
- Front-matter/preface contamination fix in corpus pipeline
- Commit the sci-fi catalog fixes and new scripts

---

## Next Steps (priority order)

### Step 1: Complete gold set validation

Run:
```bash
poetry run python scripts/build_gold_from_retrieval.py
```
~25 remaining queries. Takes 10–15 min. `q` exits cleanly, progress saved.

### Step 2: Re-run evaluator with human-validated gold set

```bash
poetry run python scripts/evaluate_similar_to_value.py --conditions none,8,15
```
This will give clean MRR/nDCG numbers without calibration distortion.

### Step 3: Front-matter contamination fix

Investigate `src/gutenberg_kg/ingest.py` and the DocKG parser pipeline.
Look for where chunks are produced from markdown and add a `content_type`
or `is_front_matter` flag on the first ~5% of chunks per document.
Alternatively: filter `reference.md` chunks out of semantic seeding in
the DocKG query path.

### Step 4: Commit corpus fixes

```bash
git add scripts/catalogs/science-fiction.txt \
        scripts/catalogs/science-fiction-additions.txt \
        scripts/build_gold_from_retrieval.py \
        scripts/evaluate_similar_to_value.py \
        analysis/similar_to_query_template.csv \
        docs/SIMILAR_TO_CAP_RECOMMENDATION.md
git commit -m "fix(corpus): correct sci-fi Gutenberg IDs; add gold-set validator"
```

---

## Memory KG Quality Techniques (from ../memory_kg work)

The user noted that `../memory_kg` (episodic/conversational memory retrieval) developed
techniques that boosted overall retrieval quality significantly. Those techniques are
directly applicable here:

- **Retrieval boosting methods** used in memory_kg should be reviewed and ported to
  the DocKG query path where appropriate
- This is a cross-repo opportunity: the same node-type dilution and front-matter
  contamination problems likely exist there too, or were already solved

Consult the memory_kg repo / its handoff docs before implementing the front-matter
fix — they may have already found the right solution.

---

## Files Modified This Session

| File | Change |
|---|---|
| `scripts/catalogs/science-fiction.txt` | IDs 29808→139, 364→64 |
| `scripts/catalogs/science-fiction-additions.txt` | ID 4358→605 |
| `scripts/build_gold_from_retrieval.py` | New — interactive gold-set validator |
| `analysis/similar_to_query_template.csv` | 36 queries filled; 10 human-validated |
| `docs/SIMILAR_TO_CAP_RECOMMENDATION.md` | New — final decision memo |
| `handoff.md` | This file |

## Key Artifacts

| File | Description |
|---|---|
| `analysis/similar_to_value_eval_20260521_024749.json` | Full eval JSON with recommendation block |
| `analysis/similar_to_value_eval_summary_20260521_024749.csv` | Condition summary |
| `docs/SIMILAR_TO_CAP_RECOMMENDATION.md` | Decision memo with rollout plan |
| `analysis/similar_to_query_template.csv` | Gold-set template (partially human-validated) |
