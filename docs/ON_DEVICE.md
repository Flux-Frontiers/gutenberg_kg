# On-device corpus packs

The native app can write its answers with the language model built into
iOS 26 / macOS 26, but an answer is only as good as the passages behind it —
and those live in a 5.7 GB bundle. `gutenkg export-swift` turns that bundle
into three SQLite files a phone can hold, so retrieval stops being a network
call.

```sh
gutenkg export-swift              # bundles/gutenberg-all → bundles/gutenberg-all/swift
```

## What comes out

| File | Holds | Rough size |
|---|---|---:|
| `core.pack` | genres, books, authors, the Browse entry points | ~5 MB |
| `gutenberg.pack` | 364 K chunk/section passages, their FTS5 index, their vectors | ~0.9–1.3 GB |
| `diaries.pack` | the four diaries, same schema plus `timestamp` | ~120 MB |
| `manifest.json` | versions, checksums, and the embedder the packs require | — |
| `golden.json` | reference top-k per query — the Swift parity gate | — |

## What is left behind, and why that is safe

The served query path (`serve/handler.py:_semantic_search`) is a dense kNN, an
FTS5/BM25 query, and a reciprocal-rank fusion over `kind IN ('chunk','section')`,
with passage text hydrated from SQLite afterwards. It never walks the graph. So
the packs carry chunks and sections and nothing else:

- **324 K topic, entity and keyword nodes** — never read by a query.
- **every edge** — 5.1 M of them, and the query path hops none.
- **the embed-text duplicate** of each passage — the `KIND:/TITLE:/FILE:/TEXT:`
  form that was embedded. The packs store the clean passage the reader sees.

Vectors are re-encoded from fp32 to int8, which is where most of the remaining
size goes. Cosine distance is scale-invariant, so vectors are L2-normalised
first and the `×127` scaling lands inside int8 range rather than clipping.

## Options worth knowing

```sh
gutenkg export-swift --verify        # measure int8 recall against exact fp32 truth
gutenkg export-swift --dtype float   # ~3x larger, exact — if recall disappoints
gutenkg export-swift --no-diaries    # books only
gutenkg export-swift --no-vectors --no-golden   # fast schema-only pass
```

`--verify` computes the true top-k by brute force over the source vectors and
compares it with what the pack returns, reporting recall@10 and the mean score
delta. The benchmark that motivated the store choice
(`benchmarks/bench_sqlite_vec.py`) measured **recall@10 = 1.0 for fp32 and 0.94
for int8** on the real 361 K-vector subset, against 0.825 for the production
LanceDB IvfFlat index — so the packs are not a mobile compromise. Below 0.9,
the command says so and points at `--dtype float`.

## The pack schema

`passages.rowid` and `vec_nodes.rowid` are the same integer, which makes a
dense search one join and a genre filter a plain `WHERE`:

```sql
SELECT p.id, p.content, v.distance
  FROM vec_nodes v JOIN passages p ON p.rowid = v.rowid
 WHERE v.embedding MATCH vec_int8(?) AND k = ?
   AND v.rowid IN (SELECT rowid FROM passages
                    WHERE kind IN ('chunk','section') AND genre = ?)
 ORDER BY distance
```

Two title columns are deliberate. `title` is the **work's** title, which hit
cards show; `node_title` is the node's own — a section's chapter name, which
the Browse tab lists. Collapsing them loses the chapter list.

Empty chunks are dropped. Empty *sections* are not: they carry no prose, but
they are the chapter markers `get_chapters` lists and `get_chapter` slices
between.

## The parity gate

`golden.json` records what the packs themselves return for twelve queries —
genre coverage plus the known-hard cases, like "circles of Hell", where the
embedder drifts toward *Paradiso* and only BM25 pins the literal *Inferno*
passages. The Swift retrieval engine is correct when it reproduces that file:
the same node ids in roughly the same order (rank overlap ≥ 0.9), the same
scores to two decimal places (delta ≤ 0.02).

Those two tolerances localise a failure to one of two places — the WordPiece
tokenizer in front of the Core ML embedder, or the int8 quantisation — which is
the whole reason to generate the file rather than eyeball a few answers.

The FTS5 index is **rebuilt** here over clean passage text rather than copied,
because the worker's `nodes_fts` indexes the embed-text form. Lexical results
will therefore not match the worker's token for token. That is why the golden
file is generated from the pack: it is the contract Swift must reproduce, not a
record of what the worker happened to return.

## What still has to happen on the Swift side

The packs are half of Phase 2. The other half is the query embedder: the pack's
vectors are `bge-small-en-v1.5`, and a query embedded by any other model —
including Apple's own `NLContextualEmbedding` — lands in a different space and
returns noise. `manifest.json` names the model and dimension so the app can
assert the match before it searches anything.

Converting `bge-small` to Core ML (~65 MB fp16, Neural Engine) and pairing it
with a BERT WordPiece tokenizer is the remaining work, tracked as Phase 2 in
[`analysis/APP_ARCHITECTURE.md`](https://github.com/Flux-Frontiers/gutenberg_kg/blob/main/analysis/APP_ARCHITECTURE.md).
