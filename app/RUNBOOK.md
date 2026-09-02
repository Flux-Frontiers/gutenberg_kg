# Getting The Knowledge Press running on your hardware

A start-to-finish checklist for the on-device app: build the corpus, convert
the embedder, compile the Swift, and get it answering with the network off.

**Read this first.** This has now been run end to end on a Mac (Xcode-beta,
Swift 6.4, macOS 27), so the warning that used to stand here is retired: the
Swift compiles and the golden gate passes. Step 3 needed exactly one fix, and
it was not any of the six that [Troubleshooting](#7-troubleshooting) predicts
-- those all compiled as written. Section 7 stays because a different
toolchain may still hit them.

Two things did go wrong, and both are written up where they bite: step 2 does
not run in the project venv at all (see the note there), and the retrieval
port had two divergences from the worker that the golden gate was too weak to
catch. Both are fixed; the gate now checks rank order, not just membership.

Do the steps in order. Steps 1–5 get the Mac app working, which is the fastest
feedback loop; the iPhone (step 6) is the same code with a different shell.

---

## 0. Prerequisites

| | Needed for | Notes |
|---|---|---|
| macOS 26, Apple silicon | on-device answers | Apple Intelligence must be **on** in System Settings. Without it everything else still runs and the app says why the answer engine is off. |
| Xcode 26 | building | `swift test` needs the full Xcode, not Command Line Tools. |
| A built bundle | steps 1–2 | `bundles/gutenberg-all/` — the output of `make build-corpus`. |
| ~5 GB free | steps 1–2 | The export reads 5.7 GB and writes under 1 GB. |
| iPhone 15 Pro or newer, iOS 26 | step 6 | The Simulator cannot run Foundation Models. |

Check the toolchain before you start:

```sh
xcode-select -p          # want /Applications/Xcode.app/Contents/Developer
swift --version          # want 6.x
```

If `xcode-select -p` reports CommandLineTools, either switch once —

```sh
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
```

— or prefix the Swift commands below with
`DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer`.

---

## 1. Build the corpus packs

From the repo root:

```sh
poetry install
poetry run gutenkg export-swift --verify
```

This takes a few minutes and writes to `bundles/gutenberg-all/swift/`.

**Do a dry run first if you want to see the row counts before spending the
vector pass** — it finishes in seconds:

```sh
poetry run gutenkg export-swift --no-vectors --no-golden --out /tmp/packs-dry
```

### What you should see

```
core.pack  ← 241 books
gutenberg.pack
  gutenberg: ~364,000 passages
  building the FTS5 index over clean passage text…
  gutenberg: ~364,000 vectors written (int8)
diaries.pack
  ...
golden.json
  embedding 12 golden queries…
verifying int8 recall against exact fp32 ground truth
  1.00  pillar of salt
  ...

  core.pack             ~5 MB   241 rows
  gutenberg.pack      ~600 MB   364,000 rows, 364,000 vectors
  diaries.pack        ~100 MB   ...
  total               ~850 MB

  recall@10 0.9xx  ·  mean score delta 0.00xx
```

### Judgement calls

- **`recall@10` below 0.90** — the command warns. Rebuild with `--dtype float`:
  three times the vector size (~420 MB instead of ~140 MB), exact scores. The
  benchmark measured 0.94 for int8 on the real corpus, so below 0.90 means
  something is off, not just quantisation.
- **`passages_without_vectors` large** in `manifest.json` — the source vector
  store is missing rows for passages that exist in `graph.sqlite`. Those
  passages stay findable lexically and readable in Browse, but not by cosine.
  Worth investigating upstream if it is more than a handful.

---

## 2. Convert the query embedder

The packs hold `bge-small-en-v1.5` vectors. A query embedded by any other model
lands somewhere else in the space and returns fluent, ranked, **wrong**
passages — so the app has to carry this exact model.

**This does not work in the project venv, and cannot.** transformers 5.x
routes BERT through its unified `masking_utils`, which emits a non-scalar
`aten::Int` that coremltools 9.0 cannot fold to a constant:

```
TypeError: only 0-dimensional arrays can be converted to Python scalars
```

Downgrading is not an option either -- `doc-kg (>=0.22.0)` and `kg-rag 0.11.0`
require `transformers>=5.5.0`, which `pyproject.toml` documents. It is not
attention-dependent; `eager` and `sdpa` fail identically.

Use a throwaway venv pinned to the stack coremltools is tested against, which
is what "deliberately not project deps" was always pointing at:

```sh
python3.12 -m venv /tmp/mlenv
/tmp/mlenv/bin/pip install torch==2.7.1 transformers==4.46.3 "numpy<2" coremltools
```

`export_embedder.py` imports torch, transformers and coremltools lazily inside
the function and needs nothing else from the package, so drive it by loading
the file directly rather than importing `gutenberg_kg` -- that keeps the
transformers 5.x chain out of the process:

```python
import importlib.util, sys
from pathlib import Path

src = Path("src/gutenberg_kg/export_embedder.py")
spec = importlib.util.spec_from_file_location("export_embedder", src)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod        # @dataclass resolves through sys.modules
spec.loader.exec_module(mod)
mod.export_embedder(Path("bundles/gutenberg-all/swift"), progress=print)
```

Expect 66 MB at parity 0.9999.

Writes into the same directory as step 1:

```
BGEEmbedder.mlpackage    ~65 MB
vocab.txt                ~230 KB
embedder.json
```

The command embeds a probe sentence with both PyTorch and the converted model
and **refuses to write one whose cosine is below 0.999**. Expect `0.9999`.

If it fails the parity check, retry with `--compute-units CPU_AND_GPU`. If that
passes and `ALL` does not, the difference is a Neural Engine numerical
tolerance; ship the CPU/GPU build and tell me.

---

## 3. Build the Swift — expect fixes here

```sh
cd app/GutenbergKGKit
swift build
swift test
```

`swift test` runs 45-odd tests: the context budgeter, the WordPiece tokenizer,
RRF fusion, top-k selection, the worker schema fixtures, and the tokenizer
parity suite. The golden gate skips at this point — step 5 turns it on.

**When `swift build` fails, go to [Troubleshooting](#7-troubleshooting) before
changing anything.** The likely failures are known and small.

### What is already verified, and what is not

**All of it is verified now.** The whole package builds and 55 tests pass,
the golden gate among them. That includes everything importing CoreML,
Accelerate, SQLite3 or SwiftUI -- `BGEEmbedder`, `VectorIndex`, `CorpusStore`,
`CatalogPack`, `CorpusPacks`, `LocalRetrieval` and the UI target -- which was
the half this step existed to test.

The one compile failure was `CorpusStore.matchExpression`: chaining
`query.map` (a `[Character]`) into `split(separator: " ")` and then
`map(String.init)` gives the type checker an overload set it will not finish,
and it reports "failed to produce diagnostic for expression" rather than a
real error. Making the intermediate an explicit `String` fixes it.

`TokenizerParityTests` runs the shipped tokenizer over the real 30,522-token
`bge-small` vocabulary and asserts it reproduces Python's `BertTokenizer`
exactly on 36 inputs, the twelve golden queries among them.

If you want the same Linux check yourself (useful in CI, no Mac needed), the
subset builds with a stock `swift-6.0.3` toolchain against a `Package.swift`
containing only the files above.

---

## 4. Install the corpus for the Mac app

`swift run` is not sandboxed, so Application Support is the plain one:

```sh
mkdir -p ~/Library/Application\ Support/Corpus
cp -R bundles/gutenberg-all/swift/ ~/Library/Application\ Support/Corpus/
```

Check it landed:

```sh
ls ~/Library/Application\ Support/Corpus
# core.pack  diaries.pack  diaries.vectors  gutenberg.pack  gutenberg.vectors
# manifest.json  golden.json  embedder.json  vocab.txt  BGEEmbedder.mlpackage
```

All of it goes in one directory — the packs and the embedder together. The app
reads `manifest.json` and `embedder.json` and refuses to open if they name
different models.

---

## 5. Run the Mac app

```sh
cd app/GutenbergKGKit
swift run KnowledgePress
```

### What to check, in order

1. **Settings ▸ Corpus** says `Passages: on this device`, names the embedder,
   and shows the size. If it shows an error instead, that message names the
   problem — most likely a missing file from step 2 or 4.
2. **Settings ▸ Answers** shows `On-device` selected. If it says unavailable,
   Apple Intelligence is off or the Mac is not eligible; the rest still works.
3. The chat's opening screen says *"Passages and answers both come from this
   device. Works in airplane mode."* If it says "passages come from the worker"
   instead, the packs did not open — back to Settings ▸ Corpus for the reason.
4. **Ask "descriptions of the Great Fire of London".** You should get Pepys and
   Evelyn, and an answer that streams in.
5. **Turn off Wi-Fi and ask again.** Nothing should change. This is the whole
   point; if it works, the feature is done.

### Then run the golden gate

```sh
cd app/GutenbergKGKit
GUTENBERG_PACKS=../../bundles/gutenberg-all/swift swift test
```

This is the real check on the retrieval port. It replays the twelve golden
queries through the Swift path and compares against what the Python reference
recorded from the same packs — rank overlap ≥ 0.9, score delta ≤ 0.02 — and
reports **every** divergence at once rather than stopping at the first.

Reading a failure:

| What you see | What it means |
|---|---|
| All twelve queries diverge | Normally the tokenizer — but it is now pinned against Python's own output by `TokenizerParityTests`, so run those first: if they pass, the split is right and the fault is downstream, in the Core ML conversion or the embedding itself. Check the `export-embedder` parity cosine. |
| A few queries diverge on rank | Usually int8 quantisation at the tail of the ranking. Rebuild with `--dtype float` and re-run; if it goes away, that was it. |
| Ranks match, scores drift | Norm handling in `VectorIndex`. The reference divides by each row's real norm, not by 127. |
| One query diverges | Look at it directly — it is probably a genuine tie being broken differently, which is harmless. |

---

## 6. The iPhone app

```sh
brew install xcodegen
cd app/ios
xcodegen generate
open KnowledgePress.xcodeproj
```

In Xcode: select the **KnowledgePress** target ▸ Signing & Capabilities ▸ set
your team. Pick your iPhone as the destination. Run.

### Getting the corpus onto the phone

There is no in-app download yet, so use Xcode's container tooling — this is the
normal development path:

1. Run the app once on the device so its container exists.
2. **Xcode ▸ Window ▸ Devices and Simulators ▸** your iPhone.
3. Under *Installed Apps*, select **KnowledgePress**, click the gear ▸
   **Download Container…**, save the `.xcappdata` bundle.
4. In Finder, right-click it ▸ *Show Package Contents* ▸
   `AppData/Library/Application Support/`. Create a `Corpus` folder there and
   copy in everything from `bundles/gutenberg-all/swift/`.
5. Back in Xcode, gear ▸ **Replace Container…** and choose the edited bundle.
6. Relaunch the app. Settings ▸ Corpus should report it.

It is about 900 MB, so the replace takes a couple of minutes.

**On the Simulator**, the corpus works but answers do not — Foundation Models
are unavailable there, which the app says plainly. It is still the fastest way
to check retrieval and layout. The container path is:

```sh
xcrun simctl get_app_container booted com.fluxfrontiers.knowledgepress data
```

…then `Library/Application Support/Corpus` under that.

---

## 7. Troubleshooting

These are the failures I expect, in the order I think they are likely.

### `partial.content` — value of type has no member 'content'

`Synthesis/OnDeviceSynthesis.swift`, in the streaming loop. The Foundation
Models `ResponseStream` element changed shape during the iOS 26 betas: early
betas yielded a bare `String`, later ones a snapshot with `.content`.

**Fix:** drop `.content` so the line reads `latest = partial`. That one line is
the only place that knows.

### `LanguageModelSession { ... }` won't take a trailing closure

Same file. Some SDK revisions want `LanguageModelSession(instructions:)`
instead of the `@InstructionsBuilder` closure.

**Fix:** `LanguageModelSession(instructions: SynthesisPrompt.ragInstructions)`
in both places (`prewarm()` and `run(...)`).

### `.guardrailViolation` / `.exceededContextWindowSize` not found

The `GenerationError` cases moved or renamed.

**Fix:** in `OnDeviceSynthesis.translate(_:)`, keep the `default:` branch and
delete whichever case does not exist. Behaviour degrades to a generic message
instead of the tailored one — cosmetic, not structural.

### Swift 6 concurrency errors around `nonisolated(unsafe) let sink`

`Retrieval/VectorIndex.swift`, in `scoreAll`. If your toolchain rejects it, the
serial fallback is correct and slower:

```swift
for batch in 0..<batches { /* same body, no concurrentPerform */ }
```

### `vDSP_mmul` argument-order or type complaints

Same file. The call computes `(rows × dim) · (dim × 1)`. If the signature
fights you, the equivalent per-row loop is already written in `scoreSelected`
— call that for every row instead. Slower, obviously correct.

### `MLModel.compileModel(at:)` deprecation or async warnings

`Embedding/BGEEmbedder.swift`. Newer SDKs prefer
`MLModel.compileModel(at:) async throws`. Making the initializer async ripples
into `CorpusPacks.init`, which is already called off the main actor — so it is
a mechanical change, not a redesign.

### The app says "No corpus installed"

- Is `manifest.json` directly inside `~/Library/Application Support/Corpus/`,
  not in a nested `swift/` folder? (Note the trailing slash on the `cp -R`
  source in step 4 — without it you get `Corpus/swift/`.)
- Are `BGEEmbedder.mlpackage`, `vocab.txt` and `embedder.json` in the same
  folder?
- Settings ▸ Corpus shows the actual reason when a corpus is present but will
  not open. That message is the diagnosis.

### "The corpus was built with X but the app carries Y"

Steps 1 and 2 ran against different models, or you copied an old embedder.
Re-run step 2 and re-copy. The app refuses on purpose: searching with a
mismatched embedder returns confident nonsense rather than an error.

### iPhone cannot reach the worker

Only matters before the packs are installed. `localhost` is the *phone*, not
your Mac — use `http://<your-mac>.local:8000` in Settings.

---

## 8. If you get stuck

Send me:

- the full `swift build` output (the first error, not the last — later ones are
  usually cascades),
- the `manifest.json` and `embedder.json` from your corpus directory,
- and, if the golden gate is failing, its full output — the divergence list is
  what says which layer is wrong.

---

## What is not built yet

Honest inventory, so nothing here surprises you:

- **No in-app corpus download.** Installing means the container dance in step 6.
  Background Assets or a resumable `URLSession` fetch is the Phase 5 item.
- **No image generation.** `🎨 Render response` from the Streamlit chat has no
  Swift equivalent yet; it is Phase 4.
- **No SwiftData persistence.** Chat history is lost on relaunch.
- **Diaries cannot be browsed, only searched.** Browse lists the four diaries
  and then shows nothing under them. This is not new and not a packing fault:
  the catalog carries no `file_path` for a diary, `diaries.pack` holds 27,462
  chunks and zero `section` rows, and the worker cannot resolve one either
  (`handler._resolve_book_file_path` looks for a `document` node in the DocKG
  store, and diaries live in DiaryKG). Their text is fully readable through
  search, which is where diary passages surface today.

  Everything a fix needs is already in the pack, so it is Swift-only work with
  no re-export: `title` matches the catalog's `book`, `kg_name` identifies the
  diary, `timestamp` gives 874 / 1,426 / 88 / 2,754 dated entries, and
  `char_start` is populated on every chunk. A diary browses by dated entry
  rather than by chapter. Note that Pepys alone would render 2,754 entries, so
  the list wants grouping by year rather than one flat scroll.
The golden gate has now run, and it earned its keep: it was the thing that
made the "pillar of salt" divergence measurable rather than a matter of
opinion. Worth knowing what it did *not* catch on its own -- it compared the
set of returned passages and their scores, so a result carrying the right
passages in the wrong order passed, and it was doing so at exactly its 0.90
tolerance floor. It now also bounds how far a shared hit may drift from the
reference's fused position (`max_rank_drift`, default 2).
