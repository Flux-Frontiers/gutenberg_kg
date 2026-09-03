# Getting The Knowledge Press running on your hardware

A start-to-finish checklist for the on-device app: build the corpus, convert
the embedder, compile the Swift, and get it answering with the network off.

**Read this first.** This has now been run end to end on a Mac (Xcode-beta,
Swift 6.4, macOS 27), so the warning that used to stand here is retired: the
Swift compiles and the golden gate passes. Step 3 needed exactly one fix, and
it was not any of the six that [Troubleshooting](#8-troubleshooting) predicts
-- those all compiled as written. Section 7 stays because a different
toolchain may still hit them.

Two things did go wrong, and both are written up where they bite: step 2 does
not run in the project venv at all (see the note there), and the retrieval
port had two divergences from the worker that the golden gate was too weak to
catch. Both are fixed; the gate now checks rank order, not just membership.

Do the steps in order. Steps 1–5 get the Mac app working, which is the fastest
feedback loop; the iPhone (step 6) is the same code with a different shell.

---

## Status checklist

Where this actually stands, as of 2026-09-03 on branch `develop` (`26d9700`).
Check off what applies to your own run as you go — corpus/embedder are
per-machine artifacts, not something a commit can carry for you.

**Core app (steps 1–5)**

- [x] Corpus packs build (`gutenkg export-swift --verify`) — recall@10 0.958
      on the real corpus
- [x] Embedder converts (needs the isolated venv in step 2 — does **not**
      work in the project venv, and cannot)
- [x] Swift package builds clean on Xcode 27 / Swift 6.4 (one fix needed,
      `CorpusStore.matchExpression`, already applied)
- [x] Full test suite green — 78 tests, golden gate armed against the real
      corpus
- [x] Retrieval verified correct: phrase-first lexical search restored, RRF
      order preserved within a pack **and** across the `all`-scope merge —
      "pillar of salt" surfaces Genesis, not Ruskin
- [x] Diaries browsable by dated entry (874 / 1,426 / 88 / 2,754 across the
      four)
- [x] Corpus + embedder installed at `~/Library/Application Support/Corpus`
      on *your* machine (step 4 — per-machine, not carried by git). Verified
      present on this Mac 2026-09-03: all ten files.

**Private Cloud Compute (step 5, optional engine)**

- [x] Backend implemented against the real iOS 27 SDK (`Profile`-based
      session construction, not the API several web sources describe, which
      does not exist)
- [x] Compiles on Xcode 26 too — the feature compiles itself out below Swift
      6.4 rather than breaking the baseline build
- [x] Root cause of the "-1" failure fully diagnosed: `swift run` is
      categorically refused (`ModelManagerError` 1046) because PCC needs the
      `com.apple.developer.private-cloud-compute` entitlement in the code
      signature *and* the provisioning profile, which no unsigned binary can
      carry — not a bug in this app, not fixable in this app
- [x] Entitlement declared in `app/ios/project.yml`, ready for a signed build
- [x] Failure now explains itself in the chat turn instead of showing
      Apple's opaque boilerplate
- [x] Apple Developer account active (renewal submitted 2026-09-02; portal
      lagged the order confirmation by a few hours, as expected — resolved).
      A **Developer ID Application** certificate is now in the login keychain,
      team `552T2QP474`. Note what that is and is not: it signs a Mac app for
      distribution outside the App Store, it does not sign iOS device builds,
      and it carries no restricted entitlement, so it moves nothing below.
- [x] App ID registered in Certificates, Identifiers & Profiles —
      `com.fluxfrontiers.knowledgepress`, explicit, no capabilities enabled
      (Private Cloud Compute is not selectable until the account holds the
      entitlement; nothing else the app does needs one). Team ID
      `552T2QP474` — for reference when filing the PCC request or checking
      `codesign -d --entitlements :-` against a build.
- [ ] Enrolled in the App Store Small Business Program — **submitted
      2026-09-02, pending approval; this is the current blocker.** No
      published SLA from Apple.
- [ ] PCC entitlement requested via Apple's [direct
      form](https://developer.apple.com/contact/request/private-cloud-compute/)
      — blocked on SBP approval above
- [ ] Capability granted on the App ID in Certificates, Identifiers & Profiles
- [ ] Signed `app/ios` build run on real iOS 27 hardware — the actual, only
      way to get a PCC answer; `swift run` cannot, permanently

A dev-only shortcut exists for testing PCC access itself while the above is
pending: [TwoMillionKit](https://github.com/insidegui/TwoMillionKit) wraps
`/usr/bin/fm` (Apple's own signed CLI, ships with macOS 27) as a
`LanguageModel`, sidestepping the entitlement by delegating to a process that
already has it. Tried on this machine 2026-09-02 and blocked by an unrelated
problem: a dyld symbol mismatch between this machine's OS build (`26A5421a`,
Beta 5) and the SDK bundled in Xcode-beta (`26A5368f`, an earlier snapshot).
Updating Xcode-beta would likely fix it but is a multi-GB download that could
shift the SDK under everything else in this document — not attempted without
asking first. Not part of the shipped app either way; if used, keep it in a
throwaway scratch package, never in `app/GutenbergKGKit`.

**iPhone app (step 6)**

- [x] `xcodegen generate` run — needed one fix, a shared scheme in
      `project.yml`; without it `xcodebuild` builds the macOS executable
      target too and fails on `import AppKit`
- [x] Compiles for the Simulator **and** for arm64 device, unsigned
      (`CODE_SIGNING_ALLOWED=NO`) — 2026-09-03, Xcode 27.0 (27A5209h)
- [x] Apple ID added in Xcode ▸ Settings ▸ Accounts, team set on the target
- [x] Developer Mode enabled on the iPhone (Settings ▸ Privacy & Security),
      then reboot — the phone pairs and lists without it, and still refuses
      every build
- [x] **Signed build installed and running on real hardware** — 2026-09-03,
      iPhone 17 Pro (`iPhone18,1`), iOS 27
- [x] Corpus pushed to the device with `devicectl` — 691 MB, all sixteen
      entries verified in place including the `.mlpackage` weights
- [ ] Answers verified on the phone with the network off (the Simulator
      cannot run Foundation Models at all, on-device or PCC)

**Mac app, signed and notarized (step 7)**

- [x] `app/macos/project.yml` builds a real `KnowledgePress.app` — universal
      (arm64 + x86_64), reusing the same `KnowledgePressApp.swift` that
      `swift run` compiles, so the two cannot drift
- [x] Developer ID signed with hardened runtime, timestamped; `spctl` accepts
      it locally — 2026-09-03
- [x] `CODE_SIGN_INJECT_BASE_ENTITLEMENTS: NO` for Release, so the signature
      carries no `get-task-allow`; `make mac-verify` fails loudly if it
      returns
- [x] `make mac-dmg` packages it (1.4 MB — the app alone, no corpus), signed
      with the same Developer ID
- [x] `notarytool store-credentials` profile stored as `knowledgepress-notary`
      — 2026-09-03
- [x] **Notarized, stapled, and verified under quarantine** — both the `.app`
      and the `.dmg`, each accepted as `source=Notarized Developer ID`
      (2026-09-03). The image needed its own pass: with only the app stapled
      it was `rejected / source=no usable signature`.
- [ ] App icon — none exists; it ships with the generic one until then

**Known gaps** — tracked below in "What is not built yet": no in-app corpus
download, no image generation, no chat persistence.

---

## 0. Prerequisites

| | Needed for | Notes |
|---|---|---|
| macOS 26, Apple silicon | on-device answers | Apple Intelligence must be **on** in System Settings. Without it everything else still runs and the app says why the answer engine is off. |
| Xcode 26 | building | `swift test` needs the full Xcode, not Command Line Tools. |
| Xcode 27 (optional) | Private Cloud Compute answers | Only for the Private Cloud engine (step 5). Everything else builds and runs on Xcode 26 unchanged — `PrivateCloudSynthesis.swift` compiles itself out below Swift 6.4, which ships only with Xcode 27. |
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

`swift test` runs the suite (78 tests as of this writing): the context
budgeter, the WordPiece tokenizer, RRF fusion, top-k selection, the worker
schema fixtures, the Private Cloud Compute error-translation tests, and the
tokenizer parity suite. The golden gate and the diary-browse tests both skip
here — they need the real corpus, which step 5 supplies via
`GUTENBERG_PACKS`.

**When `swift build` fails, go to [Troubleshooting](#8-troubleshooting) before
changing anything.** The likely failures are known and small.

### What is already verified, and what is not

**All of it is verified now.** The whole package builds and the full suite
(78 tests as of this writing) passes, the golden gate and diary-browse tests
among them. That includes everything importing CoreML, Accelerate, SQLite3
or SwiftUI -- `BGEEmbedder`, `VectorIndex`, `CorpusStore`, `CatalogPack`,
`CorpusPacks`, `LocalRetrieval` and the UI target -- which was the half this
step existed to test.

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

### Trying Private Cloud Compute (needs Xcode 27, step 0)

Pick **Private Cloud** in Settings ▸ Answers. This is a genuinely different
promise from on-device — it needs a network connection and draws on your
iCloud account's daily quota — so it is its own engine rather than a silent
upgrade path, and "works in airplane mode" above does not apply to it.

**Verified live 2026-09-02: `swift run` can never use Private Cloud Compute.**
The request fails in ~15 ms — no network round trip happens at all — with a
raw `NSError` whose root cause, two `underlyingErrors` deep, is
`ModelManagerServices.ModelManagerError` code 1046: "PCC inference is not
available in this context." That is `modelmanagerd` refusing an unsigned
process. PCC requires the `com.apple.developer.private-cloud-compute`
entitlement in **both** the code signature and the provisioning profile;
a SwiftPM executable has neither, no matter what the account is entitled to.
Note the trap that cost an evening: `availability` reports `.available`
anyway — the check covers device eligibility, not whether *this process* may
ask.

The app now says all of this in the failed turn instead of the framework's
boilerplate ("FoundationModels.LanguageModelError error -1"). To actually
run PCC: the App ID needs the capability granted in the developer portal
(the eligibility programme from step 0), `app/ios/project.yml` already
declares the entitlement, and the signed app must run from Xcode on real
hardware. On-device answers need none of this, which is why they work from
`swift run`.

If it does run: the context window is 32,768 tokens against on-device's 4,096,
so up to 12 passages reach the model instead of 5 — the same shape as the
worker's server-class synthesis, coincidentally. Settings shows a usage
caption once you are nearing or have hit the day's quota, with a button to
Apple's own upgrade sheet.

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

Two prerequisites that are easy to miss, because neither produces an error
until you try to build and then the error names something else:

1. **Sign the Apple ID into Xcode** — Xcode ▸ Settings ▸ Accounts ▸ **+**.
   A Developer ID certificate sitting in the login keychain does *not* count;
   that one is for distributing a Mac app outside the App Store and cannot
   sign an iOS device build. What matters is the account being present, after
   which automatic signing mints the Apple Development certificate and the
   provisioning profile itself. Check with
   `defaults read com.apple.dt.Xcode IDEProvisioningTeams` — it prints
   nothing until an account is added.
2. **Enable Developer Mode on the iPhone** — Settings ▸ Privacy & Security ▸
   Developer Mode, on, then reboot the phone. It only appears in Settings
   after the phone has been plugged into a Mac running Xcode at least once.
   Without it the device is visible to `xcrun devicectl list devices` and
   still refuses every build, with `xcodebuild` reporting only "Timed out
   waiting for all destinations".

Then:

```sh
brew install xcodegen
cd app/ios
xcodegen generate
open KnowledgePress.xcodeproj
```

In Xcode: select the **KnowledgePress** target ▸ Signing & Capabilities ▸ set
your team. Pick your iPhone as the destination. Run.

`KnowledgePress.xcodeproj` and `Info.plist` are both generated and both
gitignored — `project.yml` is the source of truth. Edit that and re-run
`xcodegen generate`; anything changed in Xcode's target editor is lost on the
next generate.

**Private Cloud Compute is commented out of `project.yml` on purpose.** The
entitlement cannot be present until the capability is granted on the App ID,
and leaving it in blocks *every* device build rather than just PCC: automatic
signing cannot produce a profile carrying an entitlement the App ID does not
hold, so the build fails before it starts. The four lines are commented in
place; uncomment them once the portal shows the capability.

### Checking it compiles without a phone, an account, or a signature

Useful for CI and for isolating a code failure from a signing one:

```sh
cd app/ios
xcodebuild -scheme KnowledgePress -destination 'generic/platform=iOS' \
  CODE_SIGNING_ALLOWED=NO build
```

`project.yml` declares a shared scheme, and it has to. Without one,
`xcodebuild` invents a scheme containing every target in the workspace — the
package's `KnowledgePress` **macOS** executable among them, which imports
AppKit and cannot compile for iOS. The failure reads
`Unable to resolve module dependency: 'AppKit'` and points at the macOS
shell's source, which makes it look like the shared UI is broken when nothing
is wrong with it.

### Getting the corpus onto the phone

There is no in-app download yet. Push it straight into the app's data
container with `devicectl`, over the USB cable — no Finder, no `.xcappdata`
round trip. Run the app on the device once first so the container exists,
then, from the repo root:

```sh
make ios-deploy     # install the corpus, list what landed, relaunch the app
```

`make ios-devices`, `ios-generate`, `ios-check`, `ios-install-corpus`,
`ios-verify-corpus` and `ios-launch` are the individual steps; the phone is
auto-detected, and `IOS_DEVICE=<udid|name>` picks one when several are
attached. What those targets run, written out:

```sh
DEVICE=$(xcrun devicectl list devices --json-output /dev/stdout \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["devices"][0]["identifier"])')

cd bundles/gutenberg-all/swift
xcrun devicectl device copy to --device "$DEVICE" \
  --domain-type appDataContainer \
  --domain-identifier com.fluxfrontiers.knowledgepress \
  --destination "Library/Application Support/Corpus" \
  --source BGEEmbedder.mlpackage --source core.pack \
  --source diaries.pack --source diaries.vectors \
  --source embedder.json --source golden.json \
  --source gutenberg.pack --source gutenberg.vectors \
  --source manifest.json --source vocab.txt
```

It creates the intermediate directories itself and skips files that have not
changed, so re-running it after a re-export only moves what actually differs.
About 690 MB on the first run.

Check what landed without pulling it back:

```sh
xcrun devicectl device info files --device "$DEVICE" \
  --domain-type appDataContainer \
  --domain-identifier com.fluxfrontiers.knowledgepress \
  --subdirectory "Library/Application Support/Corpus"
```

Sixteen entries, because `BGEEmbedder.mlpackage` is a bundle and lists its
insides — the one to confirm is
`BGEEmbedder.mlpackage/Data/com.apple.CoreML/weights/weight.bin` at ~63 MB,
since a flattened copy of that directory is the failure that leaves the app
reporting a corpus it cannot open.

Then relaunch so it re-reads the directory:

```sh
xcrun devicectl device process launch --device "$DEVICE" \
  --terminate-existing com.fluxfrontiers.knowledgepress
```

The older path — Xcode ▸ Window ▸ Devices and Simulators ▸ gear ▸ **Download
Container…**, edit the `.xcappdata` in Finder, **Replace Container…** — still
works and is worth knowing if `devicectl` ever refuses, but it moves the whole
container both ways for the sake of adding one folder.

### Until the corpus is installed, the app calls a worker that is not there

Expected, and worth recognising so it is not mistaken for a bug. With no packs,
`AppModel.retrievalEngine` falls through to `WorkerRetrieval`, and the default
worker URL is `http://localhost:8000` — which on the phone means *the phone*.
The console fills with:

```
Connection 1: failed to connect 1:61, reason -1
... NSErrorFailingURLStringKey=http://localhost:8000/runsync
```

`61` is `ECONNREFUSED`. Installing the corpus is the fix: `retrievalEngine`
then takes the `LocalRetrieval` branch and opens no socket at all. Pointing
Settings at `http://<your-mac>.local:8000` also silences it, but that is the
pre-packs workaround, not the destination.

### The Private Cloud Compute errors in the Xcode console

Also expected, on every launch, whichever answer engine is selected:

```
ModelManager received unentitled request. Expected entitlement
  com.apple.developer.private-cloud-compute
establishment of session failed with Missing entitlement: ...
Failed to check usage limit status: ... com.apple.tokengeneration error 24
```

`AppModel` builds the PCC backend eagerly as a stored property, so
`PrivateCloudComputeLanguageModel()` is constructed at launch and its
usage-limit check runs immediately, entitlement or no entitlement. Cosmetic —
on-device answers are unaffected.

It is also the cleanest confirmation available that **signing was never the
blocker**: this is a signed build on real hardware and `modelmanagerd` still
refuses, because the capability is not on the App ID. Nothing about the
signing setup will change that.

**On the Simulator**, the corpus works but answers do not — Foundation Models
are unavailable there, which the app says plainly. It is still the fastest way
to check retrieval and layout. The container path is:

```sh
xcrun simctl get_app_container booted com.fluxfrontiers.knowledgepress data
```

…then `Library/Application Support/Corpus` under that.

---

## 7. Ship the Mac app

Everything above runs the Mac app through `swift run`, which is the fastest
loop and needs no certificate. This section produces the other thing: a
double-clickable `KnowledgePress.app`, signed with a Developer ID and
notarized, that opens on a machine which has never seen it before.

```sh
make mac-build         # Release .app, Developer ID signed, hardened runtime
make mac-verify        # prove it is distributable before a round trip
make mac-notarize      # submit the .app, wait, staple the ticket
make mac-dmg           # package it as a signed .dmg
make mac-notarize-dmg  # notarize and staple the image itself
make mac-release       # all five, in order
```

**Both layers are notarized, and both are necessary.** Stapling the app alone
produces a disk image Gatekeeper refuses:

```
KnowledgePress.dmg: rejected
source=no usable signature
```

A `.dmg` downloaded from the internet carries a quarantine flag, and
Gatekeeper assesses the *image* when it is mounted -- so an unsigned one stops
the reader before they ever reach the app. Notarizing the image alone is not
enough either: the app inside would then have no ticket of its own, and would
need a network check on first launch after being dragged out. For an app whose
whole premise is working offline, that is the wrong trade. Two round trips,
roughly a minute each.

To check it the way the recipient will see it, set the quarantine flag on a
copy rather than trusting the local verdict:

```sh
cp app/macos/build/KnowledgePress.dmg /tmp/
xattr -w com.apple.quarantine "0083;0;Safari;$(uuidgen)" /tmp/KnowledgePress.dmg
spctl -a -vvv -t open --context context:primary-signature /tmp/KnowledgePress.dmg
```

Want `accepted` and `source=Notarized Developer ID`. Verified 2026-09-03 on
both the image and the app inside it.

The signing identity is read out of the login keychain, so no name or team ID
is written into the repo. `app/macos/project.yml` is the source of truth;
`KnowledgePress.xcodeproj`, `Info.plist` and `build/` are all generated and
gitignored.

### It shares one source file with `swift run`, on purpose

The target compiles
`app/GutenbergKGKit/Sources/KnowledgePress/KnowledgePressApp.swift` directly
rather than keeping its own copy. Two shells, one macOS app. A duplicate would
let the bundle and `swift run` drift apart silently, and "the .app answers
differently from the executable" is the single worst bug this project could
ship.

### Notarization credentials, once

Nothing can be notarized until a keychain profile exists:

```sh
xcrun notarytool store-credentials knowledgepress-notary \
  --apple-id <your-apple-id> --team-id 552T2QP474 \
  --password <app-specific-password>
```

The password is an **app-specific password** from
[appleid.apple.com](https://appleid.apple.com), not the Apple ID password
itself. `make mac-notarize` checks for the profile and prints this if it is
missing, rather than failing inside `notarytool`.

### The one trap that costs a round trip

Xcode injects `com.apple.security.get-task-allow` — the entitlement that lets
a debugger attach — into every signature unless
`CODE_SIGN_INJECT_BASE_ENTITLEMENTS` is `NO`. Apple's notary service rejects
anything carrying it. The failure is nasty because everything *local* passes:
the app signs cleanly, `codesign --verify` is happy, and `spctl` accepts it.
Only the submission fails, minutes later, with a message that does not
obviously name the entitlement as the cause.

`app/macos/project.yml` sets it `NO` for Release, and `make mac-verify` fails
loudly if it ever reappears. That check is the reason the target exists.

### No sandbox, deliberately

The app reads `~/Library/Application Support/Corpus` — the same directory
`swift run` uses, so one corpus serves both. Adding
`com.apple.security.app-sandbox` later relocates it to

```
~/Library/Containers/com.fluxfrontiers.knowledgepress/
    Data/Library/Application Support/Corpus
```

which costs one re-copy and **no code change**, since
`CorpusPacks.defaultDirectory()` resolves through `FileManager`'s
`.applicationSupportDirectory` and follows the container automatically. That
is the same property that makes the iOS build work. Note macOS only
auto-migrates data for bundle-ID-keyed paths, and `Corpus` is not one, so the
migration would be a manual copy — trivial for reproducible data.

Choosing unsandboxed now does not foreclose the Mac App Store. Sandboxing is a
per-build entitlement, not a one-way door; an App Store build would flip it on
and sign with Apple Distribution instead.

### What is signed, and what that is worth

`make mac-verify` reports:

```
== architectures ==     x86_64 arm64
== signature ==         Developer ID Application: … (552T2QP474)
                        flags=0x10000(runtime)
== debug entitlement == absent
== gatekeeper ==        accepted, source=Developer ID
```

`spctl` accepting the app **before** notarization only means the signature is
well-formed and the certificate is trusted on *this* machine. A Mac that has
never seen the app still refuses it until the notarization ticket is stapled.
Do not read a local `accepted` as "ready to send someone."

---

## 8. Troubleshooting

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

**Settings ▸ Worker** (the settings sheet behind the toolbar button — on
macOS the same view is the sidebar). The field starts empty on iOS and the
placeholder shows the shape you want, because `localhost` is the *phone*, not
your Mac. Use the Mac's Bonjour name rather than its address:

```
http://<your-mac>.local:8000      preferred — survives a DHCP change
http://192.168.1.42:8000          works until the lease moves
```

`scutil --get LocalHostName` on the Mac prints the name; `ipconfig getifaddr
en0` prints the address. Check the worker answers on the LAN and not just
loopback before blaming the phone —

```sh
curl -s -o /dev/null -w '%{http_code}\n' http://<your-mac>.local:8000/
```

— then hit **Test** in Settings, which reports the book and genre counts on
success and the real error on failure, instead of leaving you to find out at
query time.

Two first-run traps:

- **iOS asks for Local Network permission** the first time. Denying it makes
  every address fail forever; the fix is Settings ▸ Knowledge Press ▸ Local
  Network.
- **The phone must be on the same Wi-Fi**, not cellular.

The address persists across launches. It did not always: `workerURLString`
was a plain stored property with no backing store, so anything typed reverted
to the default on the next launch — which looked like the field not working
rather than not saving.

---

## 9. If you get stuck

Send me:

- the full `swift build` output (the first error, not the last — later ones are
  usually cascades),
- the `manifest.json` and `embedder.json` from your corpus directory,
- and, if the golden gate is failing, its full output — the divergence list is
  what says which layer is wrong.

---

## What is not built yet

Honest inventory, so nothing here surprises you:

- **No in-app corpus download.** Installing means a `devicectl` push over the
  cable, step 6. Background Assets or a resumable `URLSession` fetch is the
  Phase 5 item.
- **No image generation.** `🎨 Render response` from the Streamlit chat has no
  Swift equivalent yet; it is Phase 4.
- **No SwiftData persistence.** Chat history is lost on relaunch.
- **Diaries browse by dated entry, fixed.** Browse used to list the four
  diaries and show nothing under them, because the catalog carries no
  `file_path` for a diary and `diaries.pack` has zero `section` rows — nothing
  for `LocalBrowser.locate` to resolve, and the worker cannot resolve one
  either (`handler._resolve_book_file_path` looks for a `document` node in the
  DocKG store; diaries live in DiaryKG). Fixed Swift-side, no re-export: a
  diary's `title` matches the catalog's `book` name, `kg_name` is the identity
  `CorpusStore.diaryIdentity(title:)` resolves it to, and each distinct
  `timestamp` is one browsable entry (874 / 1,426 / 88 / 2,754 of them across
  the four). Pepys's 2,754 render grouped by year rather than one flat scroll.
  Covered by `DiaryBrowseTests.swift`, opt-in behind `GUTENBERG_PACKS` like the
  golden gate.
- **The golden gate has now run**, and it earned its keep: it was the thing
  that made the "pillar of salt" divergence measurable rather than a matter of
  opinion. Worth knowing what it did *not* catch on its own -- it compared the
  set of returned passages and their scores, so a result carrying the right
  passages in the wrong order passed, and it was doing so at exactly its 0.90
  tolerance floor. It now also bounds how far a shared hit may drift from the
  reference's fused position (`max_rank_drift`, default 2).
