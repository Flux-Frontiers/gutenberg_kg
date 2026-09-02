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
| `gutenberg.pack` | 364 K chunk/section passages and their FTS5 index | ~600 MB |
| `gutenberg.vectors` | their embeddings, row-major, memory-mappable | ~140 MB |
| `diaries.pack` | the four diaries, same schema plus `timestamp` | ~100 MB |
| `diaries.vectors` | their embeddings | ~20 MB |
| `manifest.json` | versions, checksums, and the embedder the packs require | — |
| `golden.json` | reference top-k per query — the Swift parity gate | — |

You also need the query embedder, which is a separate command:

```sh
poetry run pip install torch transformers coremltools   # not project deps
gutenkg export-embedder                                 # → the same directory
```

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

## Why the vectors sit beside the pack

The vectors are a sidecar file, not a table. That is a deliberate reversal of
the original design, and the reason is the device:

- A `vec0` virtual table cannot be read without the sqlite-vec **C extension
  compiled into the reader**, and iOS ships stock SQLite. A pack built that way
  does not open on the device it was built for.
- Vendoring ten thousand lines of C to fix that would buy nothing. sqlite-vec's
  `vec0` search is exhaustive — it was chosen over LanceDB's ANN index
  *because* it is exact — and so is the dot product the app does instead.

So the app memory-maps `gutenberg.vectors` and multiplies straight out of the
mapping with vDSP: no allocation per query, no C dependency, and the kernel
pages out what it is not using. The file is a 32-byte header (magic, dtype,
dim, count) followed by row-major vectors. `passages.vector_index` is a *dense*
row number into it, so a passage whose vector the source store lacks leaves no
hole. The header exists so a truncated download is rejected rather than read as
embeddings.

## The pack schema

Two title columns are deliberate. `title` is the **work's** title, which hit
cards show; `node_title` is the node's own — a section's chapter name, which
the Browse tab lists. Collapsing them loses the chapter list.

Empty chunks are dropped. Empty *sections* are not: they carry no prose, but
they are the chapter markers `get_chapters` lists and `get_chapter` slices
between.

`passages.id` is `<kg_name>:<node_id>`, not the source node id verbatim.
Diary node ids name the entry file within a book but not the book, and every
diary numbers its entries from `entry_0000` — so raw ids collide across the
four diaries merged into `diaries.pack`. The prefix keeps the id unique while
leaving it an opaque string, which is all either retrieval engine treats it
as.

The dense query is one join against a dense row index:

```sql
SELECT id, vector_index FROM passages
 WHERE vector_index IS NOT NULL AND genre = ?
```

…scored against the mapped sidecar, then fused with an FTS5/BM25 pass over the
same scope.

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

## The Swift side

`GutenbergKGKit` reads all of this:

| Type | Does |
|---|---|
| `CorpusPacks` | opens an installed corpus, checks the manifest against the embedder before trusting a single vector |
| `BGEEmbedder` | runs `BGEEmbedder.mlpackage` on the Neural Engine; CLS pooling and L2 normalisation are baked into the traced graph |
| `WordPieceTokenizer` | BERT WordPiece, ported from `tokenization_bert.py` |
| `VectorIndex` | memory-maps a sidecar, precomputes row norms once, scans with vDSP |
| `PassagePack` | FTS5/BM25, passage hydration, and the Browse queries over plain SQLite |
| `LocalRetrieval` | embed → dense → lexical → RRF, the same shape as `_semantic_search` |

The app picks it up automatically: copy the export into Application Support ▸
Corpus and `AppModel` opens it at launch, showing what it found in Settings ▸
Corpus. With no packs installed it falls back to the worker, so nothing breaks
in the meantime.

**Install the embedder alongside the packs.** `manifest.json` names the model
the corpus was built with and `embedder.json` names the one the app carries; if
they disagree, `CorpusPacks` refuses to open rather than search a
384-dimensional space with vectors from a different one. That failure would not
crash — it would return fluent, ranked, wrong passages — which is exactly why
it is checked up front.
