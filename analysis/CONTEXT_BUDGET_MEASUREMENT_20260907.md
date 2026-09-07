# The on-device passage cap is correct: a measured negative result

| Field | Value |
|---|---|
| **Author** | Eric G. Suchanek, PhD (Flux-Frontiers) |
| **Date** | 2026-09-07 |
| **Status** | Closed. `maxPassages: 5` stands as measured. |
| **Subject** | `ContextBudgeter.Budget.onDevice` |
| **Method** | Apple on-device model, temperature 0, macOS 27.0, corpus of 2026-09-07 |

---

## The question

Synthesis reports "5 of 25 in context" on every query. The on-device window is 4,096
tokens and a real prompt measured 777, so the budget looked five times more
conservative than its own arithmetic allowed:

```
passageAllowance = 4096 - 512 (response) - 240 (overhead) = 3344 tokens
actually spent by 5 passages                              =  533 tokens   (16%)
theoretical maximum at 5 passages x 500 characters        =  720 tokens   (22%)
```

The drops were not the token check. `pack()` tests `packed.count < budget.maxPassages`
first, so all 20 dropped passages hit the hard cap with 2,800 tokens still unspent.

That looked like free headroom. It is not.

## Result

More context makes the answer worse, in every configuration tried. Query
`circles of Hell`, scoped to `world-literature` unless noted.

| Configuration | Passages | Prompt tokens | Answer |
|---|---|---|---|
| **Baseline, current settings** | 5 | 777 | **847 chars, four distinct circles, correct** |
| Wider | 8 | 1,083 | 515 chars, pairs every claim with its Longfellow equivalent |
| Wider | 12 | 1,516 | 1,059 chars, largely a comparison of translations |
| Wider | 20 | 2,227 | 1,140 chars, drifts into Paradiso on virtue distribution |
| Embedding dedupe, then widen | n/a | n/a | not viable, see below |
| Per-work cap 2, then widen to 12 | 12 | 1,464 | 519 chars, scattered across unrelated works |
| Per-work cap 1, held at 5 | 5 | 769 | 833 chars, leads with a passing Les Miserables reference |

No configuration overflowed the window. 20 passages fit in 2,227 tokens against an
allowance of 3,344. The constraint is not capacity; it is that the roughly 3B on-device
model produces a worse answer when given more evidence.

`maxCharactersPerPassage: 500` is inert for this query: verse chunks are already shorter
than the cap. It would bind on prose genres, so it should not be tuned against poetry.

## Why embedding dedupe cannot work here

The corpus carries two translations of the Divine Comedy, and an unscoped 25-hit result
set for a Dante question is about half duplicate content by meaning. Suppressing that by
embedding cosine was the obvious fix. It fails because the embedder does not encode
translation-equivalence:

| Cosine | Pair |
|---|---|
| 0.8335 | Cary "Call'd Malebolge, all of rock dark-stain'd" / Longfellow "There is a place in Hell called Malebolge" |
| 0.8279 | Cary "Are three close circles in gradation plac'd" / Longfellow "are three small circles, From grade to grade" |
| 0.8278 | Cary "From the first circle I descended thus" / Longfellow "Thus I descended out of the first circle" |
| 0.7942 | a fourth true pair |
| **0.7249** | **two unrelated passages** |

True duplicates span 0.79 to 0.83; unrelated content reaches 0.72. Catching every
duplicate means cutting below 0.79, which is close enough to 0.72 to start discarding
real evidence. Across all 12 golden queries, a 0.85 threshold removed 0.3 passages on
average out of 25: it does nothing at safe settings and is unsafe where it does anything.

## Why this is not a defect

Retrieval returns 25 so the reader gets a full "Source passages" list to browse.
Synthesis deliberately consumes a curated few. Those are different jobs against
different budgets, and the split is sound. The cap is doing real work: it truncates
before the second translation enters, which is why the baseline answer describes the
circles instead of comparing translators.

## What the real lever is

Scope, not budget. Unscoped, `circles of Hell` retrieves Les Miserables and *At the
Mountains of Madness* alongside Dante; scoped to `world-literature` it retrieves Dante.
That difference dominates anything budget tuning achieved here, which makes the scope
persistence fix (`25464d2`) more valuable than it looked when written.

## Scope of this finding

Measured against one model, one corpus, one packing strategy. It says nothing about the
`.worker` and `.privateCloudCompute` budgets, which sit at 12 passages and 2,000
characters against 32,768-token windows and were not exercised. A server-class model may
well use wider context productively; do not generalise this result onto them without
repeating the measurement.

## Reproducing

The measurements came from a throwaway SwiftPM executable depending on the local
`GutenbergKGKit` package, driving `LocalRetrieval` and `OnDeviceSynthesis` directly
against the installed packs in `Application Support/Corpus`. Temperature 0 makes runs
byte-reproducible, verified over three consecutive identical runs before any conclusion
was drawn from a single sample.
