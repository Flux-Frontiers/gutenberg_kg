# The Knowledge Press — Native App Architecture (macOS-first)

**Status:** Draft for review · 2026-07-14 (rev. 2: macOS-first)
**Branch:** `feat/ios-app-architecture`

A native Swift port of the GutenbergKG chat experience (`gutenberg_kg/serve/chat.py`),
preserving the same query → retrieval → synthesis path and the same visual
vocabulary, with **Apple Foundation Models** for fully local inference and a
tiered strategy for image generation.

**Strategy: build for macOS first, iOS second.** Same SwiftUI codebase, same
FoundationModels API (macOS 26 ≡ iOS 26), but macOS removes every launch
blocker at once:

- **No corpus-distribution problem.** The 5.7 GB bundle is already on the dev
  machine's disk; the app opens the store directly. Pack hosting, Background
  Assets, and download UX all defer to the iOS phase.
- **The whole "remote" tier is localhost.** oMLX, Ollama, `image_server.py`,
  and `sdxl_server.py` already run on this Mac — every backend is reachable
  and debuggable without deploying anything.
- **No provisioning/TestFlight/App Review friction**; distribute to yourself
  with a Developer ID build.
- **M-series headroom.** More RAM and faster ANE/GPU than any iPhone; if the
  ~3 B Foundation Model proves too thin, an MLX-served larger model on the
  same machine is one provider entry away.
- **iOS becomes a target flip, not a port**: the deferred work is exactly the
  pack pipeline (§3) plus device-budget tuning — the app core doesn't change.

---

## 1. What we are porting

The current stack, as it runs today:

```
┌─────────────────────┐   RunPod-serverless JSON    ┌──────────────────────────────┐
│ Streamlit chat.py   │ ──────────────────────────► │ serve/handler.py (worker)     │
│  · sidebar config   │   {query, corpus, k,        │  · bge-small-en-v1.5 embed    │
│  · chat turns       │    min_score, floor,        │  · sqlite-vec cosine kNN(dense)│
│  · hit cards        │    synthesize, model,       │  · SQLite FTS5/BM25 (lexical) │
│  · Browse page      │    backend, op}             │  · RRF fusion                 │
│  · Render response  │                             │  · catalog enrichment         │
└─────────────────────┘                             │  · diary KGs merged by score  │
                                                    │  · synthesis → OpenAI-compat  │
                                                    │    endpoint (oMLX/Ollama/vLLM)│
                                                    │  · imagine → image server     │
                                                    └──────────────────────────────┘
                                                        image servers (either):
                                                        · image_server.py  (FLUX.2-Klein, mflux)
                                                        · sdxl_server.py   (SDXL-Lightning, diffusers)
                                                        both speak /v1/images/generations
```

Key data facts (measured from `bundles/gutenberg-all/`):

| Asset | Size | Notes |
|---|---:|---|
| Consolidated DocKG `graph.sqlite` | 2.9 GB | includes embed-text, topics, entities, keywords |
| Consolidated `vectors.sqlite` (sqlite-vec) | 1.1 GB | 688 K vectors, 384-dim fp32, bge-small-en-v1.5 — **now the served store** (was 2.5 GB LanceDB) |
| Diary KGs (4) | ~320 MB | each carries a `vectors.sqlite`; Pepys dominates |
| **Searched subset** | — | only `kind IN ('chunk','section')` = **364 K vectors** |

The retrieval path (`_semantic_search`, [handler.py:454](../src/gutenberg_kg/serve/handler.py#L454))
never does graph-hop expansion — it is dense kNN + BM25 + RRF over chunks and
sections, with content hydrated from SQLite afterwards. This is the single most
important fact for the port: **the query path is a vector search + an FTS5
query + a rank fusion, all of which have first-class iOS equivalents.**

---

## 2. Target architecture

```
┌──────────────────────────── iOS app (SwiftUI) ────────────────────────────┐
│                                                                           │
│  ChatView ── BrowseView ── SettingsView            (UI layer, §4)         │
│      │                                                                    │
│  QueryOrchestrator (actor)                          (app core)            │
│      │                                                                    │
│  ┌───┴────────────────────────────────────────────┐                       │
│  │ RetrievalEngine        SynthesisBackend         │  ImageBackend        │
│  │ (protocol)             (protocol)               │  (protocol)          │
│  ├────────────────────────────────────────────────┤                       │
│  │ LocalRetrieval:        OnDeviceSynthesis:       │  PlaygroundImage:    │
│  │  · CoreML bge-small    · FoundationModels       │   · ImageCreator     │
│  │  · sqlite-vec (dense)    LanguageModelSession   │  RemoteImage:        │
│  │  · FTS5 (lexical)      RemoteSynthesis:         │   · /v1/images/      │
│  │  · RRF fusion (Swift)  · OpenAI-compat client   │     generations      │
│  │ RemoteRetrieval:         (oMLX/Ollama/vLLM/     │     (image_server or │
│  │  · WorkerClient          RunPod worker)         │      sdxl_server)    │
│  └────────────────────────────────────────────────┘                       │
│      │                                                                    │
│  CorpusStore (SQLite: content + FTS5 + vec0 tables + catalog)             │
│      ▲                                                                    │
└──────┼────────────────────────────────────────────────────────────────────┘
       │ one-time download (Background Assets / CDN)
┌──────┴───────────────┐
│ gutenkg export-ios    │  build-side: converts bundles/gutenberg-all/
│ (new CLI command)     │  into iOS corpus packs (§3)
└──────────────────────┘
```

Three operating modes, selected per-request by the same "Provider" concept the
sidebar has today:

| Mode | Retrieval | Synthesis | Image | Works offline |
|---|---|---|---|---|
| **Full local** | on-device | Foundation Models | Image Playground | ✅ airplane mode |
| **Hybrid** (default) | on-device | Foundation Models, worker for long answers | remote image server | partially |
| **Remote** | RunPod worker | worker's vLLM/oMLX | remote image server | ❌ (thin client, = today's Streamlit) |

Remote mode is also the Phase-1 ship vehicle (§8): the app is useful on day one
as a thin client against the existing worker, before any on-device machinery
lands.

---

## 3. Corpus on device

### 3.1 Why not LanceDB

LanceDB has no iOS/macOS Swift binding. The replacement is **SQLite +
`sqlite-vec`** (the `vec0` virtual table), which compiles cleanly for
iOS/macOS as a static SQLite extension and keeps the whole corpus in one
database technology — FTS5 is already SQLite, so dense + lexical + content
live in one file per pack.

**Benchmarked 2026-07-14** ([benchmarks/SQLITE_VEC_RESULTS.md](../benchmarks/SQLITE_VEC_RESULTS.md)):
over the real 361K-vector searched subset, vec0 brute force is *exact*
(recall@10 = 1.0 fp32 / 0.94 int8) where the production LanceDB IvfFlat
index averages **0.825 recall** at default settings, at comparable latency
(85–132 ms vs 77 ms) and 9–11× smaller size (636 MB fp32 / 218 MB int8 vs
2.5 GB). The store choice is therefore quality-neutral-or-better, not a
mobile compromise.

### 3.2 Pack format

A new `gutenkg export-ios` command transforms `bundles/gutenberg-all/` into
corpus packs:

```
core.pack        catalog.json + genres + document/section metadata      ~5 MB
gutenberg.pack   chunks+sections: content, FTS5 index, vec0 vectors     ~0.9–1.3 GB
diaries.pack     4 diary KGs, same schema + timestamp column            ~120 MB
```

Size budget for `gutenberg.pack` (the big one):

| Component | Raw | On device | How |
|---|---:|---:|---|
| Vectors (364 K × 384-dim) | 559 MB fp32 | **~140 MB** | int8 quantization (`vec0` native) |
| Chunk/section content | ~700 MB | ~350 MB | drop embed-text duplication; store clean passage only; SQLite page compression via zstd-seekable or plain gzip transfer |
| FTS5 index | — | ~250 MB | rebuilt at export time over clean content |
| Metadata (catalog, paths, kinds) | — | ~20 MB | |

Total on-device footprint ≈ **1.2–1.5 GB** — comparable to one large game.
Topics/entities/keywords (324 K nodes) are **not shipped**: the served query
path never touches them.

Per-genre sub-packs are a v2 option (the schema partitions cleanly on
`file_path` prefix, exactly like the worker's `genre_filter`), but v1 ships
one pack — partial corpora complicate the "semantic_floor across KGs" semantics
for no launch benefit.

### 3.3 Delivery

**macOS (Phase 1–3): none needed.** The app opens the SQLite store directly
from a user-chosen path (default: the repo's `bundles/` output, via a
security-scoped bookmark).

**The server-side sqlite-vec migration has landed (2026-07-14):** the worker now
serves the consolidated corpus and every diary from `vectors.sqlite`
(`dockg convert-index`; parity gate recall@10 = 1.0 over the 688 K-vector
bundle), so the bundle the app reads is **the same `vectors.sqlite` the worker
serves** — no separate LanceDB→Swift conversion step. An `export-swift`/pack
build is only needed for the int8-quantized, FTS-rebuilt, content-only *mobile*
pack (§3.2); on macOS the app can open the served store as-is.

**iOS (final phase):**

- **Background Assets framework** (essential/prefetched asset packs) so the
  download happens at install time with system UI, or
- plain resumable `URLSession` download from the existing CDN/host, stored in
  `Application Support` and marked `isExcludedFromBackup`.

Pack version is stamped in `core.pack`; the app checks it against a manifest
endpoint (can be a static JSON next to the packs) and offers re-download when
the corpus is re-ingested upstream.

---

## 4. UI — SwiftUI mapping

Same look, same information hierarchy, translated to native idiom. Every
element below maps 1:1 to a function in `chat.py`:

| Streamlit today | SwiftUI port |
|---|---|
| `main()` chat loop + `st.chat_input` | `ChatView`: `ScrollView` of turn views + bottom `TextField` bar; "📚 The Knowledge Press" title, corpus-count caption |
| user turn with `[corpus]` tag | trailing-aligned bubble with small corpus capsule when scope ≠ all |
| `_render_assistant_turn` | `AssistantTurnView`: synthesis as native Markdown (`AttributedString`), model caption, stats line ("N passages · M KGs · search X ms · synthesis Y ms") |
| `_render_hit_card` (HTML card, badges, score bar) | `HitCardView`: rounded card, `_kg_kind_badge`/`_node_kind_badge` → tinted capsules, `_score_bar` → `Gauge`/`ProgressView` tinted by magnitude, `DisclosureGroup` for the full passage |
| `st.expander("Source passages")` | collapsible `Section` under the synthesis, expanded when synthesis is off — same rule as today |
| `_render_sidebar` | `NavigationSplitView` sidebar on macOS/iPad (a sheet on iPhone later): corpus `Picker` (all/gutenberg/diary/18 genres), Results `Slider` (1–50), Min-score + Semantic-floor sliders, Synthesize `Toggle`, Provider `Picker` (**On-Device** / oMLX / Ollama / OpenAI), live model list, image resolution picker — on macOS this is a persistent sidebar, which is actually *closer* to the Streamlit layout than iPhone's sheet |
| suggested queries | tappable chips above the input field on first launch / empty chat |
| `_result_to_markdown` + download button | `ShareLink` exporting the identical Markdown document |
| 🎨 Render response | button on each assistant turn (and in settings) driving `ImageBackend`; result rendered inline in the turn, saveable to Photos |
| `pages/1_Browse.py` | `BrowseView` tab: genres → books → chapters → chapter reader, backed by the same four ops (`list_genres`/`list_books`/`get_chapters`/`get_chapter`) served locally from `core.pack` + content DB, or remotely via the worker |
| 🗑️ Clear chat | toolbar button |

App structure: `TabView` with **Chat**, **Browse**, **Settings**; conversation
history persisted with SwiftData so sessions survive relaunch (an upgrade over
Streamlit's session state, free on iOS).

---

## 5. Retrieval engine — porting `_semantic_search`

The Swift port is a direct translation; the algorithm does not change.

1. **Embed the query.** `bge-small-en-v1.5` (33 M params) converted once via
   `coremltools` to an `.mlpackage` (~65 MB fp16), running on the Neural
   Engine. Single query embedding is a few ms.
   **Critical constraint: the corpus vectors are bge-small vectors, so the
   query embedder must be the *same* model** — Apple's `NLContextualEmbedding`
   or any FM-framework embedding lives in a different space and would require
   re-embedding all 364 K chunks. Tokenizer: bge uses BERT WordPiece;
   `swift-transformers` provides a compatible tokenizer, and parity is
   verified by the golden-query harness (§7).
2. **Dense channel.** `vec0` kNN with cosine distance, `WHERE kind IN
   ('chunk','section') AND file_path NOT LIKE '%reference.md'` plus the genre
   prefix filter — same predicates, same `k*3` oversampling.
3. **Lexical channel.** FTS5/BM25 over the same scoped subset — the current
   `nodes_fts` schema ports unchanged; `search_lexical`'s prefix pushdown
   becomes a `WHERE` clause on the content table joined to FTS.
4. **RRF fusion.** ~20 lines of Swift, same `_RRF_K` constant, same
   hydrate-missing-cosine-rows step so every fused hit carries an honest
   cosine score.
5. **Hydration + enrichment.** Content and diary timestamps come from the same
   SQLite the vectors live in (no separate `_attach_content` round-trip);
   `_enrich_catalog` joins author/title/genre from the catalog table.
6. **Diaries.** Per-diary vec0 tables, pure cosine, merged by score with
   `semantic_floor` applied per-KG — mirroring `_semantic_search_diaries`.

`RemoteRetrieval` is the trivial sibling: the existing `WorkerClient` request
shape (`{"input": {query, corpus, k, min_score, semantic_floor, synthesize,
model, backend, op, secret}}`) reimplemented as a Swift `actor` on
`URLSession`, secret in the Keychain.

---

## 6. Synthesis — Apple Foundation Models

`OnDeviceSynthesis` wraps the FoundationModels framework (iOS 26+):

```swift
let session = LanguageModelSession(
    instructions: Instructions(synthesisSystemPrompt)  // ported from _synthesize's prompt
)
let stream = session.streamResponse(to: userPromptWithPassages)
```

Design points, in order of how much they shape the implementation:

- **Context window is ~4,096 tokens** — the hard constraint. The worker feeds
  up to `SYNTH_MAX_K=12` passages; on device we cap at **4–5 passages trimmed
  to ~400–500 chars each** (instructions + passages + question + response
  headroom ≈ 3.5 K tokens). The passage-packing step becomes a
  `ContextBudgeter` that greedily packs best-first hits until the token budget
  (via the framework's tokenizer estimate) is spent. Retrieval still returns
  the full k for the hit cards; only synthesis sees the trimmed set.
- **Streaming.** `streamResponse` drives progressive Markdown rendering in the
  assistant turn — a UX upgrade over the current blocking spinner.
- **Availability.** `SystemLanguageModel.default.availability` gates the
  "On-Device" provider entry: unavailable (old device, Apple Intelligence off,
  model not downloaded) → the picker falls back to the remote providers with
  an explanatory footnote, exactly like the "No models reported" caption today.
- **Guardrails.** The FM framework applies content guardrails; classic
  literature (Homer's violence, Dante's Inferno, Old Testament passages) may
  occasionally trip them. Catch `LanguageModelSession.GenerationError
  .guardrailViolation` and degrade to the existing "Answer generation off —
  see source passages below" state, with a one-tap "retry via worker" action.
  This mirrors the current `synthesis_error` path.
- **Latency/thermals.** ~3 B on-device model; answers of 200–400 tokens land
  in a few seconds on A17 Pro/M-class. No adapter training in v1 — the base
  model with a good instruction prompt matches the current generic-RAG use.

`RemoteSynthesis` keeps full parity with today: an OpenAI-compatible
chat-completions client pointed at oMLX / Ollama / vLLM / the RunPod worker,
model list fetched live from `/v1/models` (= `_fetch_models`, including the
`_is_synth_model` blocklist).

---

## 7. Image generation

No FLUX/SDXL runtime exists for iOS at acceptable cost, so this is tiered:

1. **Remote (primary, quality path).** Both `image_server.py` (FLUX.2-Klein)
   and the new `sdxl_server.py` (SDXL-Lightning) speak the identical
   OpenAI-style `POST /v1/images/generations` with `b64_json` responses — the
   app's `RemoteImage` backend is one request struct and works against either,
   unchanged. Prompt construction ports `_build_image_prompt` (synthesis or
   top-3 passages, ≤800 chars); the `vlm_rewrite` "prose → visual prompt" step
   moves **on-device**: a second FM-framework session with the rewrite
   instructions, which is exactly the kind of small transform the 3 B model is
   good at, and removes a server round-trip.
2. **Image Playground framework (offline fallback).** `ImageCreator` with
   `ImagePlaygroundConcept.extracted(from:)` fed the same distilled prompt.
   Honest caveats: stylized output only (illustration/animation/sketch — no
   photorealism), fixed square-ish sizes, and weaker prompt fidelity. It keeps
   "🎨 Render response" functional in airplane mode; the turn labels which
   backend produced the image (as the chat does today with
   `image_model`/`image_backend`).
3. **Core ML Stable Diffusion — explicitly deferred.** `apple/ml-stable-diffusion`
   can run SD/SDXL on device but costs 2–3 GB of weights and tens of seconds
   per image on iPhone. Not in v1; a possible iPad/Mac Catalyst option later.

Resolution picker maps to the server's explicit `WIDTHxHEIGHT` sizes (the
`--size` contract from PR #20) for remote, and is hidden for Playground.

---

## 8. Project layout & testing

```
app/
├── KnowledgePress/              multiplatform SwiftUI app target — macOS first,
│                                iOS added later as a destination, not a rewrite
├── GutenbergKGKit/              Swift package — everything testable headless:
│   ├── Retrieval/               LocalRetrieval, RemoteRetrieval, RRF, CorpusStore
│   ├── Synthesis/               OnDeviceSynthesis, RemoteSynthesis, ContextBudgeter
│   ├── Imaging/                 RemoteImage, PlaygroundImage, PromptDistiller
│   ├── WorkerClient/            RunPod-shape API client (query + 5 ops)
│   └── Embedding/               CoreML bge-small wrapper + WordPiece tokenizer
└── Tools/                       export validation scripts
src/gutenberg_kg/cli/cmd_export_swift.py  gutenkg export-swift (store/pack builder)
```

**Parity is the test strategy.** The Python handler is the reference
implementation, so:

- `gutenkg export-swift` emits, alongside the store, a **golden-query file**: N
  representative queries (per genre + the known-hard ones: "pillar of salt",
  "circles of Hell", Moses/Quran) with the worker's top-k node IDs and scores.
- `GutenbergKGKit` CI runs the same queries against the packs (macOS runner —
  Core ML and sqlite-vec both run on macOS) and asserts rank-overlap ≥ 0.9 and
  score deltas ≤ 0.02 — catching tokenizer drift and int8 quantization loss in
  one gate. If int8 recall disappoints, the fallback is fp16 vectors
  (+140 MB), a knob in the export command.
- Synthesis and image backends are protocol-mocked in UI tests.

---

## 9. Phased migration

All phases below target **macOS**; iOS is the last row, not a fork.

| Phase | Deliverable | Depends on |
|---|---|---|
| **0. Store spike + export tooling** | sqlite-vec benchmark (`benchmarks/bench_sqlite_vec.py`) → `gutenkg export-swift`: vec0 store conversion, FTS rebuild, golden-query file | bundle exists (`make build-corpus`) |
| **1. Thin client (macOS)** | Full SwiftUI app (Chat/Browse/Settings) in **Remote mode** against the local worker (`make run`) — same look, ships first, validates the UI with zero ML risk | worker runs locally (already true) |
| **2. Local retrieval** | Core ML embedder + CorpusStore + LocalRetrieval over the converted store on disk, parity gate green; Browse goes local | Phase 0 |
| **3. Local synthesis** ✅ | FoundationModels backend (macOS 26 / iOS 26), ContextBudgeter, guardrail fallbacks, streaming turns — **landed**, and ahead of Phase 2: it needs only hits, not where they came from | — |
| **4. Images** | RemoteImage against localhost image_server/sdxl_server, then Image Playground fallback; on-device vlm_rewrite | Phase 1 (remote) / 3 (rewrite) |
| **5. iOS target** ◐ | iPhone layout (settings sheet) and the app target have **landed** (`app/ios`), sharing every view with the Mac through `KnowledgePressUI`; pack splitting + hosting + Background Assets remain | Phases 2–4 |

Each phase is independently shippable; Phase 1 alone is already "our chat
interface as a native Mac app".

**Phase 3 landed before Phase 2**, which the dependency column had not
anticipated. Synthesis consumes `[Hit]` and never asks where the hits came
from, so the on-device answer engine works against worker retrieval exactly as
it will against local retrieval — and it is the half a reader can *feel*. The
app today is the Hybrid row of §2 with the arrow reversed: retrieval remote,
answer local. Phase 2 turns the last remote call off.

## 10. Risks & open questions

- **FM context window (4 K)** halves the passage budget vs the worker — answers
  may be thinner on multi-source questions. Mitigation: Hybrid default routes
  `k > 6`-passage syntheses to the worker when reachable.
- **Guardrail refusals on classical texts** — frequency unknown until tested
  against the real corpus; the fallback UX is designed in from the start.
- **Tokenizer parity** for bge-small in Swift — de-risked early by the Phase 0/2
  golden-query gate.
- **Pack hosting** *(iOS phase only)* — ~1.5 GB per user download; needs a
  home (existing CDN, Cloudflare R2, or GitHub Releases won't cut it at
  scale). Cost scales with installs. Not a blocker for anything before
  Phase 5.
- **Corpus updates** — on macOS, re-run `gutenkg export-swift` after
  re-ingest; on iOS, full re-download in v1 with delta packs as a later
  optimization.
- **Minimum OS is macOS 26 on Apple Silicon** for Full-local mode (and
  iOS 26 / Apple Intelligence hardware when the iOS target lands); older
  systems get Remote mode with the FM backend compiled conditionally.
