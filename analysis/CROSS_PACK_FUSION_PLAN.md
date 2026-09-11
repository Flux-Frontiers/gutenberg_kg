# Cross-pack fusion: stop giving the diaries half the context

Status: **proposed**, nothing implemented.
Measured 2026-09-10 against `bundles/gutenberg-all/swift` (241 books, 4 diaries).

## The observation

"categorical imperative", `corpus=all`, k=12, on the real packs:

```
 1  cos=0.7698  Kant, Groundwork          7  cos=0.7829  Kant, Groundwork
 2  cos=0.6351  Boswell, Hebrides         8  cos=0.6540  Pepys, Diary
 3  cos=0.7777  Kant, Groundwork          9  cos=0.7344  Kant, Groundwork
 4  cos=0.6548  Pepys, Diary             10  cos=0.6537  Boswell, Hebrides
 5  cos=0.7692  Kant, Groundwork         11  cos=0.7424  Kant, Groundwork
 6  cos=0.5747  Evelyn, Diary            12  cos=0.6415  Boswell, Hebrides
```

Strict alternation. Every books hit scores 0.72-0.78, every diary hit
0.57-0.65, and the two lists interleave regardless. Five of the top ten slots
go to the diaries. Scoped to `gutenberg` the same query returns Kant passages
at 0.764, 0.731 and 0.722 and a relevant Nietzsche at 0.714 -- all four
displaced from the `all` top ten by diary passages that score lower than every
one of them.

The passages that win those slots are not close calls. Pepys #4 is a Greek
speech and the blessing of bells, containing neither query term; Evelyn #6
matched `Imperator Byzantiorum`.

On the on-device budget (`maxPassages: 5`) this means the model answering a
question about Kant gets two or three Kant passages and two or three diary
entries. Raising the cap to 10 was measured and does not help: it buys five
more slots and the interleave hands roughly half of them back to the diaries.

## Why it happens

`LocalRetrieval.mergeByFusedRank` (Swift) and `serve.fusion.merge_by_rank`
(Python) are the same arithmetic. Each hit contributes `1 / (rrf_k + rank)`
from the list it came from, and node ids never repeat across the two corpora,
so **every hit scores from exactly one list**. Books rank-0 and diaries rank-0
both score `1/60`; they tie, and the tie breaks on first-seen order. Rank 1
ties with rank 1, and so on down.

The merge therefore has no access to quality at all. It is a round-robin
wearing RRF's clothes. Within a pack RRF is doing real work -- it reconciles
two genuinely incommensurable scales, BM25 and cosine. Across packs the scale
is identical: same embedder, same normalised space, directly comparable. RRF
there discards information it could have used.

## Why the obvious fix is wrong

Sorting the union by cosine regresses a bug that is already fixed, and
`fusion.py` says so:

> a literal BM25 match owes its rank to that channel precisely because the
> dense one buried it, so its score is low by construction and a score sort
> drops it out of the top `k` entirely.

The worked case is "pillar of salt": the Lot's-wife verse fuses to the top of
the books at cosine 0.59 while every diary chunk scores about 0.70. Sorting
the union on score does not demote the verse, it removes it. The better the
lexical channel works, the more reliably a score sort throws its result away.

So the two cases pull opposite ways:

| query | truth | rank merge |
|---|---|---|
| pillar of salt | the right hit has *lower* cosine than the other pack's | correct, protects it |
| categorical imperative | one pack is better on *both* channels | wrong, splits the slots anyway |

## The distinction that separates them

Whether a hit **owes its rank to the lexical channel**.

That is knowable and currently thrown away. `searchOnePack` computes
`scoredLexical` and `denseIDs` separately and then merges them; after `fuse`
returns, nothing records which channel carried a given hit. A rescued hit and
a merely-mediocre hit are indistinguishable by the time `mergeByFusedRank`
sees them, so the merge protects both -- and protecting the second is the
whole cost being measured here.

## Proposed rule

Carry the provenance, then merge on it:

1. A hit is **lexically rescued** if it appears in the lexical list and either
   is absent from the dense list or ranks materially lower in it (proposed:
   outside the dense top `k`).
2. Cross-pack merge keeps rescued hits at their fused rank, exactly as today.
3. Every other hit competes on cosine, across packs, since the scale is shared.
4. Ties and the within-pack fusion are untouched.

"pillar of salt" keeps working because the verse is rescued by rule 1 and
protected by rule 2. "categorical imperative" improves because no diary hit is
rescued -- they are ordinary dense hits that happen to rank high within a much
weaker list -- so rule 3 sorts them below Kant on cosine.

## Work, in order

Each step is separately reviewable; steps 1-2 change no behaviour.

1. **Measurement harness, first.** A committed diagnostic that prints the
   merged ranking with per-hit cosine and pack for a list of queries, run
   against `GUTENBERG_PACKS`. Both findings in this document came from a
   throwaway version of this; it should exist so the change can be judged
   rather than asserted. Extend the golden set with `corpus=all` queries --
   `golden.json` currently records one pack at a time, so **the cross-pack
   merge has no test at all today**, which is why this shipped unnoticed.
2. **Baseline.** Record present behaviour for a query set spanning both cases:
   lexical-rescue queries ("pillar of salt", "circles of Hell") and
   single-domain queries ("categorical imperative", "the categorical
   imperative in Kant"). This is the before half of the comparison.
3. **Provenance through fusion.** Have `fuse` return, alongside the ordered
   ids, the set that was lexically rescued. Swift and Python both. Internal --
   no change to `Hit`, the pack schema, or the wire format, so no corpus
   rebuild and no manifest bump.
4. **Merge rule.** Implement 1-4 above in `mergeByFusedRank` and
   `merge_by_rank` together, with unit tests over synthetic lists for: a
   rescued low-cosine hit held at rank; an unrescued low-cosine hit demoted;
   an all-rescued list behaving exactly as today.
5. **Re-measure** with the step-1 harness against the step-2 baseline. Accept
   only if the rescue queries are unchanged and the single-domain queries
   improve.
6. **Revisit `maxPassages`.** Deferred deliberately. At 5 the on-device model
   currently gets 2-3 relevant passages; with the merge fixed, the first 5 are
   worth more and 10 may be worth having. That decision needs the fixed merge
   underneath it or it just buys more noise.

## Open questions

- **Rule 1's threshold.** "Outside the dense top k" is a proposal, not a
  measurement. It may want to be a cosine gap instead, or simply "absent from
  the dense list", which is stricter and simpler. Step 1's harness should
  settle it.
- **Parity.** Swift and Python must change together -- `LocalRetrieval` is
  documented as "arithmetic for arithmetic" against the handler, and the
  on-device and worker answers are supposed to agree. Nothing currently tests
  that agreement across packs; step 1 should.
- **Whether the diaries belong in `all` at scale.** Four diaries against 241
  books is a lopsided merge under any rule. A better ranking may still leave
  the question of whether an unscoped search should weight corpora by size.
  Out of scope here; worth its own decision.
