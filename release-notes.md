# GutenbergKG v1.4.0 — The Expanded Press

**245 books · 1,236,169 nodes · 5,321,000 edges · 18 genres**

This release is the largest corpus expansion in project history — five new genres,
42 books, and a full fresh-build of every index. It pairs the corpus growth with
a substantially improved ingestion experience and the first rigorous retrieval
quality study: a labeled SIMILAR_TO evaluation that quantifies the edge-type's
value and establishes a principled default.

---

## What's New

### Five new genres — 42 books

The corpus grows from 203 to **245 books** across 18 genres, adding five
entirely new literary domains: biography, drama, epistolary literature,
natural history, and travel writing.

| Genre | Books | Notable titles |
|---|---:|---|
| `biography` | 11 | Franklin · Douglass · Rousseau · Augustine · Cellini · Mill · Jacobs · Washington · Grant Vol. 1 · Henry Adams · Boswell's Johnson |
| `drama` | 11 | Ibsen × 3 · Marlowe × 2 · Shaw × 2 · Chekhov × 2 · Wilde · Webster |
| `letters` | 7 | Byron · Keats · Pliny · Chesterfield · Voltaire · Montagu · Lamb |
| `natural-history` | 7 | Darwin × 3 (Origin · Descent · Beagle) · Huxley · Faraday · Wallace |
| `travel` | 6 | Twain · Marco Polo · Isabella Bird · Mungo Park · Dana · Melville |

All 42 Gutenberg IDs were verified live before download. Each title ships as a
Markdown-converted `.md` file plus a structured `reference.md` metadata stub.
Full genre catalogs live in `scripts/catalogs/` for reproducible re-download.

### Two-pane Rich display for `gutenkg ingest`

Long corpus builds now display a live **two-pane terminal UI** powered by Rich:

- **Top pane** — yellow progress bar with spinner, current `genre › book`,
  `M/N` book counter, elapsed time, and ETA.
- **Bottom pane** — scrolling log of the last 24 build output lines, refreshed
  at 4 Hz. Uses an `os.dup2` stdout redirect so output from Rich `Console()`
  instances deep inside `doc_kg` is captured alongside plain `print()` calls —
  no output is lost.

The two-pane display replaces the old flat terminal spew that made it impossible
to track overall progress during multi-hour corpus builds.

### `--quiet` flag for `gutenkg ingest`

```bash
gutenkg ingest --quiet
gutenkg ingest --genre philosophy --quiet
```

Suppresses the per-book DocKG progress bars (parsing, embedding, indexing) while
keeping the two-pane overall display running. Wired all the way through
`IngestOptions → build_dockg() → DocKG.build_graph()`,
`build_embeddings()`, and `build_index_from_cache()`.

### SIMILAR_TO empirical evaluation

The SIMILAR_TO edge type (`discover_similar`) had no principled default — it was
off by default because its benefit was unquantified. This release delivers the
evidence:

**Study design:** 36 labeled queries across 12 books (4 genres × 3 size tiers),
each query annotated with relevant/non-relevant ground truth. Evaluated at cap
values 0 (off), 8, and 15 using MRR@15, nDCG@15, and Recall@15.

| Condition | MRR@15 | nDCG@15 | Recall@15 |
|---|---|---|---|
| SIMILAR_TO off | 0.2300 | 0.1283 | 0.120 |
| cap 8 | 0.2367 | **0.1355** | 0.134 |
| cap 15 | 0.2369 | 0.1356 | 0.134 |

Cap 8 and cap 15 are statistically indistinguishable (+0.001 nDCG), but cap 15
carries 37% more edges for zero measurable gain. **Decision: SIMILAR_TO default-on
at `similar_max_degree=8`.** The nDCG gain of +5.6% clears the ≥5% threshold on a
real labeled evaluation across 4 genres.

Evaluation scripts (`run_similar_to_cap_sweep.py`, `run_retrieval_cap_ab.py`,
`evaluate_similar_to_value.py`) and all result artifacts are committed to
`analysis/` for full reproducibility.

### Front-matter contamination assessment

A new analysis tool — `scripts/assess_front_matter.py` — scans all corpus
Markdown files for introduction, preface, editor note, and similar front-matter
sections using position-gated heading heuristics.

Results across 241 books (`analysis/front_matter_assessment.json`):

- **63 books** contain detected front matter (26% of corpus)
- **Mean front-matter fraction:** 6.6% of chunk tokens
- **Maximum:** 39.8% (heavily edited critical editions)

This establishes the baseline for the corpus-quality work planned in v1.5.0:
front-matter filtering at ingest time to prevent intro/preface chunks from
dominating retrieval results.

---

## Fixes

- **Three wrong Gutenberg IDs in `science-fiction`** — books were downloading
  completely wrong texts because the catalog contained bad IDs:
  - *The Lost World*: `29808` → `139` (was fetching a Robert Herrick anthology)
  - *The Gods of Mars*: `364` → `64` (was fetching Burroughs' *The Mad King*)
  - *Pellucidar*: `4358` → `605` (was fetching an L. Frank Baum Oz title)
  All three texts have been re-downloaded with correct IDs and re-indexed.

- **RunPod build pod now prefers curated catalog files** — `runpod/build_kg.py`
  now checks for `scripts/catalogs/<genre>.txt` before falling back to
  `fetch-genre --max-results 200`. This ensures the pod corpus matches the
  locally curated catalog rather than a live Gutenberg search result.

- **`gutenkg status` and `snapshot` blind to the 5 new genres** — `GENRE_LABELS`
  in `corpus.py` was a hardcoded dict that was never updated when the new genres
  were added. Both commands silently reported 203 books instead of 245. Fixed
  properly: `GENRE_LABELS` is now built dynamically from `corpus/genres.json` via
  `genres.ALL_GENRES`, so adding a genre with `gutenkg genres add` automatically
  flows through to `status`, `snapshot`, and the corpus table — no code change
  required.

- **Ingest summary box column misalignment** — replaced double-width Unicode
  emoji (`✅`, `⚪`, `⚠️`) in the per-book status table with ASCII tokens
  (`[ok]`, `[~]`, `[!]`) that render correctly in all terminal fonts.

---

## Corpus

| Genre | Books | Nodes | Edges |
|---|---:|---:|---:|
| Philosophy | 48 | 241,471 | 918,796 |
| English Literature | 37 | 187,058 | 927,902 |
| Ancient & Classical | 26 | 137,857 | 579,264 |
| American Literature | 23 | 90,481 | 370,090 |
| Russian Literature | 13 | 90,191 | 462,058 |
| French Literature | 12 | 89,511 | 447,009 |
| Biography | 11 | 69,535 | 314,775 |
| Drama | 11 | 25,602 | 101,637 |
| Science Fiction | 19 | 73,199 | 268,940 |
| Travel | 6 | 51,693 | 205,555 |
| Natural History | 7 | 44,747 | 172,992 |
| Sacred Texts | 7 | 32,942 | 175,701 |
| Letters | 7 | 27,029 | 98,526 |
| World Literature | 5 | 21,185 | 83,696 |
| German Literature | 5 | 13,066 | 50,830 |
| Technical Reference (IA) | 3 | 22,920 | 62,506 |
| Spanish Literature | 1 | 11,422 | 57,980 |
| Shakespeare | 4 | 6,260 | 22,743 |
| **Total** | **245** | **1,236,169** | **5,321,000** |

Corpus grew by **42 books (+21%)**, nodes by **+218,606 (+21%)**, edges by
**+893,485 (+20%)** since v1.3.0 (baseline: 203 books · 1,017,563 nodes · 4,427,515 edges, key `03a399124ed6`).

---

## Upgrade

```bash
git pull
poetry install

# Rebuild all indices with SIMILAR_TO now default-on
gutenkg ingest --force-build

# Or rebuild a single genre
gutenkg ingest --force-build --genre science-fiction
```

> **Note:** Existing `.dockg/` indices do not contain SIMILAR_TO edges unless
> they were built after this release. A `--force-build` is recommended to get
> the full +5.6% nDCG benefit.

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
