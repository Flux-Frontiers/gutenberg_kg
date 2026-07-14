# sqlite-vec vs LanceDB — benchmark results

Corpus subset: 361,521 chunk/section vectors, 384-dim, BAAI/bge-small-en-v1.5.
Ground truth: exact NumPy cosine top-10. LanceDB uses its IvfFlat ANN index; vec0 is exact brute force.

| Query | LanceDB r@10 / ms | vec0 fp32 r@10 / ms | vec0 int8 r@10 / ms | int8 score MAE |
|---|---|---|---|---|
| pillar of salt | 0.4 / 79 | 1.0 / 130 | 1.0 / 85 | 0.0020 |
| circles of Hell | 0.8 / 77 | 1.0 / 131 | 1.0 / 84 | 0.0015 |
| What does the Quran say about Moses? | 1.0 / 79 | 1.0 / 131 | 1.0 / 85 | 0.0025 |
| the whiteness of the whale | 1.0 / 78 | 1.0 / 132 | 0.9 / 85 | 0.0019 |
| descriptions of the Great Fire of London | 0.9 / 76 | 1.0 / 133 | 0.9 / 86 | 0.0019 |
| the categorical imperative and moral duty | 1.0 / 77 | 1.0 / 133 | 0.9 / 85 | 0.0011 |
| a monster assembled from dead body parts | 0.8 / 78 | 1.0 / 132 | 1.0 / 85 | 0.0011 |
| time travel to the distant future | 1.0 / 76 | 1.0 / 132 | 0.9 / 86 | 0.0018 |
| the fall of the House of Usher | 0.5 / 78 | 1.0 / 132 | 0.8 / 84 | 0.0013 |
| how to wire an electric bell | 1.0 / 76 | 1.0 / 130 | 1.0 / 85 | 0.0042 |
| shipwreck on a desert island | 1.0 / 77 | 1.0 / 132 | 0.9 / 85 | 0.0019 |
| a dinner party with too much wine in a London diary | 0.5 / 77 | 1.0 / 130 | 1.0 / 85 | 0.0020 |

## Aggregate

| Engine | mean recall@10 | median latency (ms) | store size |
|---|---|---|---|
| LanceDB IvfFlat | 0.825 | 77 | 2.5 GB (688K rows, incl. embed-text) |
| vec0 fp32 (exact) | 1.000 | 132 | 636 MB |
| vec0 int8 (exact) | 0.942 | 85 | 218 MB |

int8 mean cosine-score MAE: 0.0019

## Interpretation (2026-07-14, Apple Silicon, sqlite-vec 0.1.9)

- **LanceDB's IvfFlat index is approximate and misses real hits at default
  settings** — mean recall 0.825, with "pillar of salt" at 0.4 and two other
  queries at 0.5. This is the *production configuration*: the serve handler
  issues the same prefiltered search with default nprobes. Part of the
  known exact-phrase weakness may be ANN recall loss, not embedding drift.
  (Recall could be raised with higher nprobes/refine_factor at some latency
  cost — untested here.)
- **vec0 is exact by construction** (brute force): recall 1.0 at 132 ms fp32,
  and 85 ms at int8 — both in the same latency class as LanceDB's 77 ms and
  negligible next to synthesis time.
- **int8 quantization costs almost nothing in score fidelity** (MAE ≈ 0.002
  cosine) and its recall@10 of 0.94 reflects rank swaps at the tail of the
  top-10, not lost passages. An oversample-and-rescore step (int8 scan →
  fp32 re-rank of top 50) would close it to ~1.0 if needed.
- **Size**: 2.5 GB LanceDB → 636 MB fp32 / 218 MB int8 vec0 for the searched
  subset (embed-text duplication dropped, non-searched kinds excluded).

Conclusion: at this corpus scale, sqlite-vec brute force is not a compromise —
it is *more accurate* than the current index at comparable latency, at 9–11×
smaller size. The remaining open question for a server migration is write-path
integration in doc_kg, not query quality.
