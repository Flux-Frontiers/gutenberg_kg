# Synthesis tuning on Apple Foundation Models

Working notes, 2026-09-14, the day Private Cloud Compute first answered on
real hardware. The answers were weak. This records why, what Apple says
about the knobs, how to reproduce an answer without a device, and what the
`feat/synthesis-tuning` branch changes.

## How to see what the model saw

Every answer writes a trace: `Application Support/Diagnostics/synthesis-*.json`
in the app's data container, carrying the exact instructions, the exact
prompt (headers plus packed passage text), the answer, the temperature, and
the device. Pull them off a device with:

```sh
xcrun devicectl device copy from --device <id> \
  --domain-type appDataContainer --domain-identifier com.fluxfrontiers.knowledgepress \
  --source "Library/Application Support/Diagnostics" --destination ./traces
```

`make ios-devices` lists the ids. On the Mac the same directory is under
`~/Library/Application Support/Diagnostics`.

### On-device: reproducible from the terminal, byte for byte

`/usr/bin/fm` ships with macOS 27 and is the same on-device model the app
uses. `scripts/synth_replay.py TRACE --greedy` feeds a trace's instructions
and prompt through it. On this Mac, `--greedy` reproduced an iPhone 17 Pro
trace **byte for byte**, so prompt experiments need no device at all:

```sh
scripts/synth_replay.py traces/synthesis-....json --greedy
scripts/synth_replay.py traces/synthesis-....json --greedy --instructions my-instructions.txt
```

`fm` has no temperature flag; `--greedy` is temperature 0, and its default
sampling stands in for everything else.

### Private Cloud Compute: only through a signed build

`fm` has no PCC route, and PCC needs a provisioning profile that grants the
entitlement, which `swift run` and `swift test` can never carry. So the Mac
app grew a headless mode:

```sh
make mac-dev
app/macos/build/Build/Products/Debug/KnowledgePress.app/Contents/MacOS/KnowledgePress \
  --ask "circles of Hell" --corpus world-literature --engine privateCloud
```

Run the binary inside the bundle, not `open`, so stdout is the terminal.
The trace is written as usual.

## What was wrong

Three separate things, and temperature was the least of them.

**Packing starved the model.** The first PCC answer ("circles of Hell") got 4
of 25 passages -- 728 tokens of a 32,768-token window. `maxPassagesPerSource`
was 2, both Dante translations count as separate works, so four passages
went in and the other 21 hits were capped out. Capped-out hits also spend a
`maxPassages` slot (deliberately; see the budgeter), so nothing refilled.
The cap exists because the *on-device* model loops on repeated text; the
server model does not. PCC's preset is now 4 per work.

**Retrieval handed over junk, and the model cannot tell.** For "pillar of
salt" in the sacred-texts scope, the packed passages were: Solomon's temple
pillars (a lexical hit on "pillar"), the Genesis 19 chunk clipped at 500
characters, and two unrelated Quran chunks. Instructing the model to "skip
off-topic passages silently" made things worse -- it summarised every
passage it had been told to skip. Relevance cannot be delegated to a 3B
model; it has to be right before the prompt is built. This one is a
retrieval/ranking problem and is not fixed on this branch.

**The instructions were written for a 70B model.** `_RAG_SYSTEM` says "Be
concise and specific". The worker's model reads that as a style note; the
on-device model reads it as "one sentence". Given two perfect Genesis
chunks it still answered in 101 characters. The same passages under the
new guide instructions gave two paragraphs of narrative.

## Apple's guidance, the parts that apply

From the Foundation Models documentation, fetched 2026-09-14.

- **Instructions over prompts.** "The model obeys prompts at a lower priority
  than the instructions you provide." Put the role in the first sentence,
  say what to do, give style preferences, use uppercase to emphasise rules
  that matter. Never put user input in instructions (prompt injection).
- **Shape the output explicitly.** "If you specify 'using three sentences',
  it speeds up processing and generates a concise summary." The inverse
  holds too, which is what the guide instructions rely on: "two or three
  short paragraphs" is obeyed where "be concise" collapses.
- **What the on-device model is for**: summarise, extract, understand,
  refine, classify, compose. Not for math, code, or logical reasoning --
  and, from experience here, not for judging which passages are relevant.
- **Context window**: 4,096 tokens on-device, all of instructions + prompts
  + outputs in a session. One session per question is the right call.
- **`GenerationOptions`**: `temperature`, `samplingMode` (`.greedy`,
  `.random(top:seed:)`, `.random(probabilityThreshold:seed:)`), and
  `maximumResponseTokens` -- which Apple says to use "only when you need to
  protect against unexpectedly verbose responses", since a hard cap "can
  lead to the model producing malformed results".
- **Guardrails**: both prompt and output are checked; a failure throws
  `guardrailViolation`. `SystemLanguageModel(guardrails:
  .permissiveContentTransformations)` skips that check for string output,
  meant for apps that "work with certain inputs ... that might contain
  sensitive content". The on-device model "still has a layer of safety".
  Not available on the PCC model.

## Results, on-device replay (greedy)

| Trace | Original instructions | Guide instructions |
|---|---|---|
| pillar of salt, as packed | 142 chars, one sentence | 783 chars, narrative + says the Quran passages do not cover it |
| pillar of salt, two Genesis chunks | 101 chars | 584 chars, the flight from Sodom, the angels, the looking back |
| circles of Hell (PCC's prompt) | 501 chars of stitched fragments | 928 chars, two paragraphs |
| Great Fire, 10 passages | 1,580 chars of bullets | 1,065 chars, two paragraphs, nothing invented |
| categorical imperative | 1,355 chars | 1,577 chars, Kant, Nietzsche, Westermarck in turn |

## Cross-device, for the Apple report

PCC at temperature 0 gave **identical** answers on the iPhone 17 Pro and the
iPad mini (A17 Pro) for an identical prompt. The divergence `app/fm-repro/`
documents is on-device only, and it is still there: 45 same-prompt pairs
for "pillar of salt" at T=0, zero identical answers, and the iPad's
answers open with fabricated tool calls (`tool_call: {"tool_name":
"extract_references", ...}`), which is the reproducer's exact symptom.

## Private Cloud Compute's guardrail, measured

Apple's framework runs a safety classifier over the prompt and over the
generated text. Either tripping throws `guardrailViolation`. On-device that
check can be skipped for plain-text output (`permissiveContentTransformations`).
The PCC model's API has no guardrail parameter at all.

With the per-work cap at 4, `--ask` through PCC on this Mac:

| Question (scope) | Runs | Completed | Stopped mid-stream |
|---|---|---|---|
| circles of Hell (world-literature) | 3 | 2 | 1, at "Popes and Cardinals ... avarice" |
| descriptions of the Great Fire (diaries) | 4, incl. greedy and worker-parity | 0 | 4, every time at "Papist" |
| pillar of salt (sacred-texts) | 1 | 1 | -- |

The Great Fire failure is content-determined, not sampling: cap 2 (five
passages) completes, cap 3 fails, so one Pepys passage admitted by the wider
cap carries the trigger. The cut-short trace names it: "a printed account of
the examinations taken, touching the burning of the City of London, shewing
the plot of the Papists therein". The 1666 diary of a civil servant, refused
by the filter as sectarian, and refused at a different point each run --
268 characters in once, 870 another -- as soon as the model reaches that
passage.

The on-device model, given the identical eight passages, completed the
answer with default guardrails and again with permissive ones. The server
filter is the stricter of the two, and it is the one with no setting.

One trap for anyone catching this: on macOS 27 the session throws the
unified `LanguageModelError` (`.guardrailViolation` or `.refusal`), not
iOS 26's `LanguageModelSession.GenerationError`. A catch written against
the latter matches nothing on PCC. `isGuardrailStop` covers both.

Two consequences on the branch:

- The output check fires *after* text has streamed, so the answer exists in
  part. The app used to show the truncated text with no notice -- the
  failure label sat behind an `else` the partial answer never reached.
  `SynthesisFailure.guardrailCutShort` now names the state, the turn view
  shows it under the text, and the trace is written anyway, since which
  text tripped the filter is what a trace is for.
- No setting fixes this for PCC. The realistic mitigations are upstream:
  a narrower cap on the diaries scope, or a retry with the offending passage
  dropped, neither of which is built.

## What the branch changes

- `SynthesisTuning`: temperature (default 0.2), greedy, per-work cap
  override, instruction set, permissive guardrails. Persisted; applied to
  the next answer; recorded in each trace.
- Settings gains a "🧪 Synthesis" section for all of it.
- `SynthesisPrompt.guideInstructions` beside the untouched `ragInstructions`,
  so on-device and worker answers can still be compared under identical
  instructions ("Worker parity").
- `Budget.privateCloudCompute.maxPassagesPerSource` 2 -> 4.
- PCC temperature was 0; it now shares the tuning default.
- `SynthesisFailure.guardrailCutShort`, shown under a partial answer.
- `KnowledgePress --ask`, `make mac-dev`, `scripts/synth_replay.py`.

## Not done

- Retrieval ranking a lexical "pillar" hit above Genesis 19 within a
  scope; and a 500-character passage clip that cuts stories mid-sentence
  on-device. Both upstream of synthesis.
- `maximumResponseTokens`, `random(top:)` and `random(probabilityThreshold:)`
  are not exposed. Apple's own caution on the first, and no evidence yet
  that the second two matter more than temperature.
- A retry-without-the-offending-passage path for guardrail stops.
