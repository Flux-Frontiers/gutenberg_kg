# Release Notes — v1.18.0

> Released: 2026-09-06

The corpus now searches and answers on the device. This release adds the
export path that shrinks a 5.7 GB bundle to ~640 MB of SQLite packs, the
Core ML query encoder that keeps the app in the same embedding space, and
three answer engines — on-device, Private Cloud Compute, and the worker.
It also fixes a set of retrieval bugs that returned fluent, ranked, wrong
passages, and closes two resume gates that let half-built stores pass as
complete.

### Added

**On-device search and synthesis**

- **`LocalRetrieval` — the corpus searches itself on the device.**
  `BGEEmbedder` runs the converted `bge-small` on the Neural Engine,
  `VectorIndex` scans memory-mapped vectors with vDSP, `PassagePack` runs
  BM25 over FTS5, and the two channels fuse with the same RRF constant the
  worker uses. With packs installed the app answers and browses with the
  network off.
- **Vectors live in a `<pack>.vectors` sidecar, not a `vec0` table.** iOS
  ships stock SQLite, so a `vec0` table cannot be read without compiling in
  sqlite-vec. The sidecar is a 32-byte header plus row-major rows, memory-
  mapped and multiplied in place, indexed by a dense `passages.vector_index`.
  The header exists so a truncated download is rejected rather than read as
  embeddings.
- **`OnDeviceSynthesis` — grounded answers from Apple Foundation Models.**
  Streams from the ~3B model in iOS 26 / macOS 26. No key, no endpoint,
  nothing leaves the device. `SynthesisPrompt.ragInstructions` is
  `kg_utils.synthesis._text._RAG_SYSTEM` word for word, pinned by a test,
  because drift there silently changes what every answer may say.
- **`ContextBudgeter` — an explicit trade against a ~4,096-token window.**
  Packs best-first, trims at word boundaries, stops when the budget is spent,
  rather than letting the framework truncate silently. Retrieval still returns
  the full `k` for hit cards; the turn's stats line reports "5 of 10 in
  context" when they differ.
- **`PrivateCloudSynthesis` — Private Cloud Compute as a second engine.**
  A peer of `OnDeviceSynthesis`, not a rewrite: both build a
  `LanguageModelSession` and share everything downstream. Offered separately
  (Settings ▸ Answers ▸ **Private Cloud**) because it needs a network
  connection and draws on the user's iCloud quota. In exchange its
  32,768-token window carries 12 passages instead of 5. Gated on
  `compiler(>=6.4)` so the Xcode 26 baseline keeps building; the engine is
  absent until the toolchain catches up.

**Export pipeline**

- **`gutenkg export-swift` — the corpus, small enough for a phone.** Turns
  `bundles/gutenberg-all/` into three SQLite packs plus a manifest and a
  parity file: ~5.7 GB in, ~640 MB out. The reduction is knowing what the
  query path reads — 324K topic/entity/keyword nodes, all 5.1M edges, and the
  embed-text duplicate of every passage stay behind. Vectors re-encode fp32 →
  int8, L2-normalised first so ×127 scaling lands in range instead of
  clipping. Every read is driven by `PRAGMA table_info`, so a column missing
  from one store becomes `NULL` rather than a crash 300,000 rows in.
- **`gutenkg export-embedder` — the query encoder, converted once.** Traces
  `bge-small-en-v1.5` with CLS pooling and L2 normalisation folded into the
  graph, converts to fp16 Core ML, writes the tokenizer vocabulary beside it,
  and checks the result against PyTorch — refusing to ship a model that
  disagrees. `manifest.json` and `embedder.json` name the model at both ends
  and `CorpusPacks` refuses to open when they differ, because that failure has
  no symptom other than bad answers.
- **`gutenberg_kg.serve.fusion`.** Importing `handler` runs its startup, so
  nothing in that module can be unit-tested without loading a model. The
  rank-merge arithmetic is pure, so it lives here and the handler calls in.

**App**

- **An iPhone target sharing every view with the Mac app.** The SwiftUI layer
  moved into a `KnowledgePressUI` library both shells import. `MacRootView`
  keeps the settings sidebar; `PhoneRootView` puts the same controls behind a
  sheet. `BrowseView` became a `NavigationStack` drill — one code path instead
  of two.
- **`RetrievalEngine` and `QueryOrchestrator`.** Retrieval, budgeting and
  synthesis are one streamed pipeline (`QueryEvent`), with the worker behind a
  protocol.
- **Diaries browse by dated entry.** The catalog carries no `file_path` for a
  diary and `diaries.pack` has no `section` rows, so Browse listed the four
  diaries and showed nothing under them. `CorpusStore.diaryIdentity(title:)`
  maps a catalog title to its `kg_name` and each distinct `timestamp` becomes
  one entry — 874, 1,426, 88 and 2,754 across the four. Pepys's 2,754 render
  grouped by year rather than as one flat scroll.

**Tests and corpus**

- **`TokenizerParityTests` — the Swift tokenizer pinned to Python's output.**
  Runs against the real 30,522-token `bge-small-en-v1.5` vocabulary and
  asserts it reproduces `BertTokenizer` exactly across 36 inputs: the twelve
  golden queries plus contractions, accents, punctuation runs, em dashes,
  digits, an over-long word, control characters, CJK, and a string long enough
  to truncate. Runs without a corpus, device or network, so a divergence here
  localises to the tokenizer rather than the Core ML conversion.
  `scripts/make_tokenizer_fixture.py` regenerates the fixture.
- **A Christmas Carol (PG #46)** added to `english-literature` — the edition
  that exercises the `STAVE` heading rule.
- **`make spacy-model`** downloads `en_core_web_sm` when it cannot be loaded.
  It is not installable as an ordinary Poetry dependency, and
  `chunk-diaries` now depends on it. This also un-skips the suite's one
  guarded test (877 passed/1 skipped → 886 passed).

**Snapshots**

- **`snapshot save` gained `--subject` and `--key`.** `capture()` already took
  named `key`/`subject` parameters, but the CLI had no way to reach either, so
  every snapshot's subject could only ever be the `corpus:gutenberg` default.
  `--subject` names what was measured, separate from `version`, which names
  the measuring tool; `--key` snapshots the package against a release tag
  instead of a timestamp. Both stay optional and keep today's behaviour when
  omitted. Four new tests go through the CLI and read what actually landed on
  disk — the default subject reaches the snapshot file and the manifest
  entry, explicit `--subject`/`--key` reach their own fields rather than
  `metrics`, an omitted key is a timestamp rather than a git tree hash, and a
  timestamp key round-trips through `snapshot show` despite its colons.

### Changed

- Assistant turns render progressively instead of behind a blocking spinner.
  The Foundation Models stream yields snapshots of the whole answer rather
  than deltas, so `SynthesisEvent.partial` carries cumulative text and the
  view replaces rather than appends.
- A query in flight can be stopped. Passages already retrieved stay on screen.
- **Embeddings stream to JSONL during ingest.** `build_dockg()` passed the
  cache as `embeddings.json`, and the suffix selects the code path: the
  `.json` branch builds its own `CorpusEmbedder` from the shared embedder's
  name, so a second copy of the model loaded once per book — the double-load
  that causes SIGBUS on MPS. The `.jsonl` branch calls the shared embedder
  directly. On a 9,544-node book, peak RSS drops from +978 MB to +205 MB with
  identical vector counts.
- **Per-book `SIMILAR_TO` discovery** is now explicit in
  `docs/ingestion-pipeline.md`.

### Fixed

**Retrieval**

- **Exact phrases were lost in the export path.** `GraphStore.search_lexical`
  searches the phrase first and only then falls back to an OR of the terms.
  `export_swift` kept the OR and dropped the phrase, and the Swift port
  mirrored it — so "pillar of salt" ran as `"pillar" OR "of" OR "salt"`, and
  "of" matches nearly all 364K passages, diluting BM25 until the verse was
  unreachable. Both sides now do phrase, then OR: the Genesis chunk returns to
  rank 1 from 604th.
- **`LocalRetrieval` re-sorted every result by cosine.** Within one corpus the
  order is already RRF's, and cosine is not what RRF ranked by — a literal
  match floated up by fusion carries a *lower* cosine than the semantic hits
  under it, so re-sorting buried exactly what fusion surfaced.
- **The `all` scope threw away the matches the lexical channel had rescued.**
  A BM25 match owes its rank to the lexical channel *because* the dense
  channel buried it, so its cosine is low by construction: the Lot's-wife
  verse fused to the top of the books at 0.59 where every diary chunk scores
  ~0.70. Sorting the merged list by score dropped it out of the top k
  entirely, and the better the lexical channel worked the more reliably the
  merge undid it. Both corpora now fold together by fused *rank* at the same
  RRF constant, in `LocalRetrieval` and in `handler.query`. `runpod/handler.py`
  is deliberately untouched: it has no lexical channel, so sorting its union
  is coherent.
- **The golden gate could not catch any of the above.** It compared the set of
  returned passages and their scores, so the right passages in the wrong order
  passed — at exactly its own 0.90 tolerance floor. It now also bounds how far
  a shared hit may drift from its reference position (`max_rank_drift`,
  default 2). Deliberately not an exact-order check: the dense channels differ
  in their last bits, so near-ties come back either way round.

**Export**

- **`export-swift` silently dropped 4,601 of 27,462 diary passages.** Diary
  node ids name the entry file but not the book, and every diary numbers from
  `entry_0000` — so merging four diaries into one `passages` table keyed by
  raw id discarded every later diary's colliding rows via `INSERT OR IGNORE`.
  Pepys alone lost 2,927. The pack id is now `<kg_name>:<node_id>`, the insert
  is a plain `INSERT` that fails loudly on any residual collision, and a
  vector can only land on a row from its own KG.
- **`export-swift --verify` compared hybrid search against dense ground
  truth**, reporting recall@10 of 0.567 against its 0.9 threshold when actual
  dense-only int8 recall was 0.958. Every lexical rescue counted as a recall
  miss — including the golden queries chosen because only BM25 finds them.
  Verify now runs `search_pack(..., lexical=False)`, matching its docstring.
- **`export-swift`'s per-KG vector log printed the running total**, so the
  last diary appeared to write 22,861 vectors for 2,784 passages.

**Ingest**

- **Half-built DocKG stores were skipped as complete.** `build_dockg()` writes
  `graph.sqlite` before the vector store, so a run that dies in between leaves
  a valid graph with no vectors. The resume gate checked only
  `is_sqlite_valid(graph.sqlite)`, which passes on that shape — the next run
  printed "already built, skipping" and registered the book with no semantic
  search, surfacing at query time as missing results rather than at ingest
  time as an error. `dockg_defect()` replaces the graph-only probe and checks
  that a vector store exists and holds rows, reading `vec_nodes_rowids` rather
  than the `vec0` virtual table. Verified against all 249 corpus stores with
  no false positives.
- **The same gate was weaker still for diaries.** `build_diary_index()`
  treated a diary as built if `graph.sqlite` merely existed — not readable,
  not complete — so an interrupted run reported "already built" with
  `nodes=0 edges=0`. `.diarykg` has the same on-disk shape as `.dockg`, so
  `dockg_defect()` applies unchanged; a defective store now wipes and
  rebuilds.
- **A failed diary stage reported SUCCESS.** `ingest_diaries()` returns a
  `None` summary when the stage fails outright, and both `print_summary()` and
  `save_summary()` derived status solely from the per-genre failed count — so
  a failed diary stage contributed zero and the run printed "SUCCESS — all
  books ingested" with the genre missing from the report. On 2026-09-05 that
  listed 20 genres instead of 21 and left four `.diarykg` stores at their
  2026-09-01 build. The exit code was correct throughout; nothing a reader saw
  said so. Both functions now take `diary_rc` and refuse to print SUCCESS when
  it is non-zero.
- **Connection and cache leaks on the ingest failure path.** `kg.close()` and
  the `embeddings.json` unlink now run in a `finally`; both were unreachable
  on the exception path.
- **`ImportError`, `AttributeError`, `TypeError` and `NameError` now
  propagate** instead of being caught per book. These mean a bad import or
  signature drift against `doc_kg`, which fails identically for every book, so
  the old handler turned one bug into 249 identical "build failed" lines with
  no traceback. Genuine per-book failures are still caught, and now print a
  traceback unless quiet.

**Conversion and build**

- **`_is_prose_line` rejected lines of exactly 60 characters.** The detector is
  documented as a 60-character bar (`len >= 60`) but checked `len <= 60`, so a
  filled wrap line never counted. A Christmas Carol wraps at 60; Stave I had
  four such lines and none longer, so the cluster split that peels the body's
  `STAVE I` off the contents list never fired and the whole first stave was
  attributed to the preface. Changed to `len < 60`. All 243 cached books
  unchanged; Carol now emits `## STAVE I` through `## STAVE V`.
- **The Swift package would not compile on a Mac.**
  `CorpusStore.matchExpression` chained `query.map` into
  `split(separator:)` and `map(String.init)`; Swift 6.4 will not finish that
  overload set and reports "failed to produce diagnostic for expression". An
  explicit `String` intermediate types each step unambiguously.
- **The Swift tokenizer mis-segmented CJK.** `WordPieceTokenizer` omitted
  BERT's `_tokenize_chinese_chars` pass, so a run of ideographs was one "word"
  and WordPiece prefixed all but the first with `##` — `中` + `##文` where
  Python produces `中` + `文`. Not a crash: a plausible tokenization that sends
  the query elsewhere in the embedding space. The source comment claiming CJK
  "degrades to unknown tokens" was also wrong.
- **Two test messages that would not have compiled.** swift-testing's
  `Comment` is `ExpressibleByStringInterpolation`, not built from a
  concatenation, so the `#expect` failure messages in `TokenizerParityTests`
  and `GoldenParityTests` were type errors.

**Pins**

- **`docker/Dockerfile` and `runpod/requirements.txt` had drifted from
  `pyproject.toml`/`poetry.lock`.** `kgmodule-utils`, `doc-kg` and `diary-kg`
  had moved to `0.19.0`/`0.24.1`/`0.98.0` in the lock, but the Dockerfile ARGs
  and the RunPod requirements still named `0.18.1`/`0.23.0`/`0.97.0` — nine
  mismatches in total, each drifting in one of three ways `check_pins.py`
  distinguishes: an ARG behind pyproject's floor (so `pip install .` silently
  upgrades it past what any build actually ran), the lock ahead of the ARG
  (an index built by one version and read by an older one, which fails
  silently as empty results rather than an error), and the RunPod floor below
  pyproject's (letting the serverless worker install a version the package
  itself rejects). Since `build` depends on `check-pins`, this blocked every
  Docker and Apple container build outright. `kg-rag` was unaffected — it had
  not moved. All four now sit at PyPI latest.
- **`check_pins.py --bump` half-applied when PyPI was partly unreachable.**
  `bump()` aborted only when *every* lookup had failed, so a single
  unreachable package was dropped from the set while the rest moved,
  `poetry lock` ran, and the command reported success on a bump that had left
  one pin behind — the drift the whole-set bump exists to prevent, and which
  its docstring already claimed could not happen. It now refuses outright and
  writes nothing.
- **`_version_key` compared tuples of unequal length**, so `(0, 19)` sorted
  below `(0, 19, 0)` and a `>=0.19` floor read as below a 0.19.0 ARG.
  Components are zero-padded to a common width; padding never truncates, so
  `0.19.0.1` still sorts above `0.19.0`. Latent until now — no pin was
  two-component.
- **`bump_files` rewrote docker-compose.yml's version build args**,
  contradicting the check beside it: any `*_VERSION` there is drift whether
  it agrees or not, because the pins belong only in the Dockerfile.
  Maintaining the copy kept alive what that check rejects. The compose
  rewrite is gone; the compose check is unchanged.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
