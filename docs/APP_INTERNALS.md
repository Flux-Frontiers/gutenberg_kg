# Inside the app

How the iOS and macOS app is put together, written for someone who knows
systems and Python but has never built for Apple platforms.

The short version: one Swift package holds all the logic, two thin shells put a
window around it, and every part of a query — embedding, search, and the
written answer — runs on the device.

> An illustrated version of this page, with the diagrams drawn out, is
> published at
> <https://claude.ai/code/artifact/bb8a8545-1ec7-4aa8-ae89-3b68b1536348>.
> This file is the canonical copy.

**Related:** [`app/RUNBOOK.md`](https://github.com/Flux-Frontiers/gutenberg_kg/blob/main/app/RUNBOOK.md)
is the ordered checklist for building and installing;
`analysis/APP_ARCHITECTURE.md` is the design record with its phase table;
[On-device corpus packs](ON_DEVICE.md) covers the data format.

---

## 1. What an iOS app actually is

A Python program is a directory of source that an interpreter walks into. An
iOS app is none of those things, and four differences account for most of the
friction.

**It is a signed bundle, not a script.** The build produces
`KnowledgePress.app` — a directory the OS treats as one opaque object,
containing a compiled binary, an `Info.plist` manifest, and resources. It
carries a cryptographic signature tied to an Apple developer identity, and
unsigned code does not run on an iPhone at all. That is why the runbook has you
set a signing team before anything will launch: it is not configuration, it is
the difference between an app and a pile of bytes.

**It has no filesystem in the Unix sense.** Each app gets a sandbox — its own
private directory tree, invisible to every other app. There is no
`/usr/local/share` to drop a corpus into and no shell to drop it from. When the
code asks for `.applicationSupportDirectory` it gets a path inside that
sandbox, and that is the only place it can write. It is also why installing
900 MB of packs on a phone means Xcode's container tooling rather than `scp`.

**The UI runs on one thread, and blocking it is fatal.** Every pixel is drawn
from the main thread. Hold it for a few hundred milliseconds and the interface
stutters; hold it for seconds and the OS kills the process. So work that takes
time — opening a 600 MB SQLite pack, compiling a Core ML model, scanning
364,000 vectors — must happen elsewhere and hand its result back.

**Capabilities are declared, not discovered.** An app cannot reach a device on
the local network unless its `Info.plist` says so and the user agrees. That is
the `NSLocalNetworkUsageDescription` string in `app/ios/project.yml`; without
it the phone silently fails to find the worker on your Mac.

---

## 2. Two shells, three libraries

Swift's package manager plays the role `pyproject.toml` plays for you, and a
*target* is roughly a Python package: a directory compiled as one unit with
declared dependencies. `app/GutenbergKGKit/Package.swift` declares four.

```
  KnowledgePress (macOS)          KnowledgePress (iOS)
  swift run · MacRootView         Xcode · PhoneRootView
            │                               │
            └───────────────┬───────────────┘
                            ▼
                    KnowledgePressUI            every view; only the root
                    AppModel · ChatView         differs per platform
                    BrowseView · SettingsView
                            │
                            ▼
                     GutenbergKGKit             all logic, no SwiftUI —
                     retrieval · embedding      the target the tests import
                     synthesis · worker client
                            │
                            ▼
        corpus packs · Core ML encoder · OS language model
```

Dependencies point downward only. An iOS app target **cannot import a macOS
executable**, which is the whole reason `KnowledgePressUI` was split out of the
Mac app: two shells needed the same views, and only a library can be shared.

Each shell is about thirty lines — create the state object, put a root view on
screen, kick off two startup tasks. Everything else the phone does is code the
Mac runs too, so a bug fixed on the Mac (where the build-and-run loop is
seconds) is fixed on the phone.

The fourth target, `GutenbergKGKitTests`, imports only the logic library. Same
instinct that keeps retrieval code out of `chat.py`: anything testable
headlessly should not need a window to exist.

---

## 3. SwiftUI, if you wrote chat.py

You already know the hard part, because Streamlit taught it to you. In
`serve/chat.py` you never mutate a widget — you write a script that reads state
and describes the whole page, and Streamlit re-runs it from the top when state
changes. SwiftUI works the same way, with one refinement:

| | Streamlit | SwiftUI |
|---|---|---|
| State lives in | `st.session_state` | an `@Observable` class (`AppModel`) |
| On change | re-run the whole script | re-evaluate only views that **read that property** |
| Result | whole page redrawn | just the chat list redrawn |

That granularity is what makes token-by-token streaming affordable. An answer
streams dozens of times a second; re-running the whole page at that rate would
be unusable, re-drawing one bubble is not.

Three pieces of syntax carry it:

- `@Observable` on `AppModel` makes the class report which properties each view
  read. Think `st.session_state` that also keeps a dependency graph.
- A `View` is a struct with a `body` property — a *value* describing what
  should be on screen, not an object you mutate. Closer to a render function
  returning a tree than to a Qt widget.
- `@Environment(AppModel.self)` pulls the shared model out of the view tree
  without threading it through every intermediate view.

So `ChatView` reads `model.turns` and describes a list of bubbles. When
retrieval appends a hit or the model emits another sentence, the code mutates
`model.turns` and the list redraws itself. Nothing in the view layer knows
where the text came from.

---

## 4. Concurrency, next to asyncio

| Swift | Means | Nearest Python |
|---|---|---|
| `async` / `await` | Suspend without blocking the thread | `async` / `await` |
| `Task { … }` | Start concurrent work and keep going | `asyncio.create_task` |
| `actor` | A type whose state only one task touches at a time, compiler-enforced. `WorkerClient` is one. | A class you remembered to lock |
| `@MainActor` | Runs on the UI thread. `AppModel` is marked so. | No equivalent |
| `AsyncStream` | A sequence you `for await` over as values arrive | async generator |
| `Sendable` | Safe to hand to another task; the compiler refuses if not | Nothing |

The addition is that these are checked at compile time rather than discovered
at runtime. Touching `@MainActor` state from a background task is a build
error, not an intermittent crash.

`AppModel.loadCorpusPacks()` shows it working: opening the corpus compiles a
Core ML model, which takes seconds, so the work happens in a detached task and
only the assignment of the result happens back on the main actor. That is why
launching does not freeze while the embedder loads.

---

## 5. One question, end to end

```
  ChatView ──► AppModel.send ──► QueryOrchestrator
  "the Great Fire"  appends a turn        │  1 · retrieval
                                          ▼
  ┌─────────────────────── LocalRetrieval ───────────────────────┐
  │  BGEEmbedder ──────► VectorIndex ────────┐                   │
  │  384 floats          364K rows           ├──► RRF fusion     │
  │  Neural Engine       mmap + vDSP         │    k = 60         │
  │       └────────────► PassagePack FTS5 ───┘        │          │
  │                      BM25, clean text             ▼          │
  │                             hydrate passages from SQLite     │
  └──────────────────────────────┬───────────────────────────────┘
                    10 hits ◄────┘
                        ▼
              ContextBudgeter ──2──► OnDeviceSynthesis
              packs 5 into              Apple Foundation
              4,096 tokens              Models · ~3B
                                              │
     ChatView ◄────────────────────────────────┘
     3 · cumulative snapshots, many per second

  Nothing in this diagram crosses the network.
```

The two retrieval channels run over the same scoped subset and are fused by
reciprocal rank fusion at the same constant the worker uses (`RRF_K = 60`), so
a passage the embedder buries can still be surfaced by an exact term match.

### What each step costs

Roughly, on an A17 Pro. The numbers set what the interface can promise: search
feels instant, the answer visibly writes itself.

| Step | Order of magnitude | Why |
|---|---|---|
| `BGEEmbedder` | ~5 ms | 33 M parameters, 64 tokens, Neural Engine |
| `VectorIndex` | ~100–300 ms | 364 K × 384 int8 dot products; the cost is reading 140 MB, not the arithmetic |
| FTS5 BM25 | ~10 ms | An inverted index doing what it is for |
| `OnDeviceSynthesis` | 2–4 s | A ~3 B model writing 200–400 tokens; streamed, so the wait is visible progress |

---

## 6. The three seams

A Swift `protocol` is your `typing.Protocol`. Three of them carry the
architecture, and each exists because something real needed to be swapped.

| Protocol | Implementations | What it buys |
|---|---|---|
| `RetrievalEngine` | `LocalRetrieval` (device), `WorkerRetrieval` (network) | The app works before the packs are installed and gets faster and private after — one property in `AppModel` decides which |
| `SynthesisBackend` | `OnDeviceSynthesis` (device) | A phone that cannot run Apple Intelligence still reads passages, and says why the answer engine is off |
| `CorpusBrowser` | `LocalBrowser` (device), `WorkerClient` (network) | Browse reads books the same way either way. `WorkerClient` already had the right signatures, so conforming it took one empty extension |

The seams are also what let the app degrade honestly instead of failing. No
corpus installed is not an error state — retrieval falls back to the worker and
Settings says so. Apple Intelligence switched off is not an error state — the
passages still arrive, with a line explaining why there is no answer.

---

## 7. What runs on the silicon

Three different Apple technologies, doing three different jobs.

**Core ML — the query encoder.** The runtime for a model you supply, roughly
what ONNX Runtime or TorchScript is elsewhere. `gutenkg export-embedder` traces
`bge-small-en-v1.5` and converts it to an `.mlpackage` (~65 MB fp16) that the
OS schedules onto the Neural Engine. It has to be *that* model: the packs hold
bge-small vectors, and a query embedded by anything else lands in a different
384-dimensional space and returns fluent, ranked, wrong passages. Hence
`CorpusPacks` comparing `manifest.json` against `embedder.json` and refusing to
open when they disagree — the failure has no other symptom.

**Foundation Models — the answer.** Since iOS 26, Apple ships a roughly
3-billion-parameter language model as part of the OS and any app may call it.
No bundled weights, no per-token cost, nothing leaving the device. The price is
a context window of about 4,096 tokens for instructions, passages, question and
answer together — against the twelve passages the worker feeds a server-class
model. That is what `ContextBudgeter` is for.

**Accelerate — the vector scan.** No neural network, just SIMD. `VectorIndex`
memory-maps the `.vectors` sidecar and multiplies straight out of the mapping
with vDSP, so a query allocates nothing and the kernel pages in only what it
touches.

> **Why the vectors are a file, not a table.** The original design put them in
> a `vec0` virtual table, which is how the worker stores them. That cannot work
> on a phone: reading a `vec0` table needs the sqlite-vec C extension compiled
> into the reader, and iOS ships stock SQLite — the pack would not open on the
> device it was built for. Vendoring the extension would buy nothing either,
> since `vec0`'s search is exhaustive and so is the dot product done instead.

---

## 8. Where the corpus lives

Everything the device needs sits in one folder inside the app's sandbox, at
`Application Support/Corpus` — on the Mac, `~/Library/Application Support/Corpus`.

```
Corpus/
  manifest.json          names the embedder; checked before anything opens
  core.pack              genres, books, Browse entry points — ~5 MB
  gutenberg.pack         364K passages + FTS5 index — ~600 MB
  gutenberg.vectors      their embeddings, memory-mapped — ~140 MB
  diaries.pack           the four diaries, with timestamps
  diaries.vectors
  golden.json            the parity gate's expected answers
  BGEEmbedder.mlpackage  the query encoder — ~65 MB
  vocab.txt              WordPiece vocabulary, from the same tokenizer
  embedder.json          model id, dim, special-token ids
```

The `.pack` files are ordinary SQLite databases with an unusual extension. You
can open any of them with the `sqlite3` CLI — the schema is `passages`,
`passages_fts` and `pack_meta`. That is deliberate: a format you can inspect
with tools you already have is a format you can debug.

---

## 9. From source to phone

Apple platforms have two overlapping toolchains, which is a common source of
confusion.

| Tool | Builds | Use it for |
|---|---|---|
| `swift build` / `swift test` | Libraries and command-line executables | The fastest loop. Compiles every target and runs the tests; the Mac app runs this way too |
| Xcode | App bundles, signed and installable | Anything that lands on a phone. Signing, provisioning and device deployment live only here |
| XcodeGen | The `.xcodeproj` itself | Generating the project from `app/ios/project.yml`, so a short YAML file is in version control instead of a large generated XML one |

Hence the order in the runbook: find compile errors with `swift build`, where
the loop is seconds and the output is readable, and bring Xcode in only for the
parts that genuinely need it.

---

## 10. Swift ↔ Python glossary

Reading aids, not exact equivalences.

| Swift | Roughly |
|---|---|
| `struct` | A frozen dataclass, copied on assignment. Most types here are structs |
| `final class` | A normal Python object — reference semantics, shared |
| `protocol` | `typing.Protocol` / an ABC |
| `extension X: P {}` | Retroactively declaring that an existing type satisfies a protocol |
| `enum` with values | A tagged union — closer to a sealed class hierarchy than to `enum.Enum` |
| `guard let x else { … }` | An early return when a value is nil |
| `try? f()` | Call, and get nil instead of an exception |
| `deinit` | `__del__`, but deterministic |
| `some View` / `any P` | A concrete-but-unnamed type / a boxed protocol value |
| `Package.swift` | `pyproject.toml` |
| target | A package, in the import sense |
| `@testable import` | Import with internal names visible — no `_private` convention needed |

---

## 11. Where to look in the code

| File | What it does |
|---|---|
| `Embedding/WordPieceTokenizer.swift` | BERT WordPiece, ported from `tokenization_bert.py`. The most dangerous file here: a word split differently is a query sent somewhere else, and nothing throws |
| `Embedding/BGEEmbedder.swift` | Loads the Core ML encoder and vocabulary, refuses a model that does not match the packs, turns a string into 384 floats |
| `Retrieval/VectorIndex.swift` | Maps the `.vectors` sidecar, precomputes row norms once, scans with vDSP, keeps the best k without sorting everything |
| `Retrieval/CorpusStore.swift` | `PassagePack`: BM25 over FTS5, passage hydration, the Browse queries |
| `Retrieval/CatalogPack.swift` | Reads `core.pack` — genres, books, header counts |
| `Retrieval/CorpusPacks.swift` | Opens an installed corpus and validates it; the embedder check lives here |
| `Retrieval/LocalRetrieval.swift` | Embed → dense → lexical → RRF. The Swift half of `_semantic_search` |
| `Retrieval/SQLiteConnection.swift` | Owns the database handle so the pack types can fail on a bad file before they finish initialising |
| `Synthesis/ContextBudgeter.swift` | Fits passages into 4,096 tokens. Pure logic, heavily tested |
| `Synthesis/SynthesisPrompt.swift` | The RAG instructions, copied word for word from `kg_utils`. Drift here silently changes what every answer may say |
| `Synthesis/OnDeviceSynthesis.swift` | Apple Foundation Models: streaming, availability, guardrail fallback |
| `QueryOrchestrator.swift` | Retrieval then synthesis, as one stream of events the chat renders |
| `KnowledgePressUI/AppModel.swift` | All app state, and the decision about which engine answers |
| `KnowledgePressUI/RootViews.swift` | The only place the two platforms differ: sidebar on the Mac, sheet on the phone |

If you read three, read `LocalRetrieval.swift` for the shape of the query,
`ContextBudgeter.swift` for the one constraint that shapes the whole answer,
and `WordPieceTokenizer.swift` for the thing most likely to be subtly wrong.
