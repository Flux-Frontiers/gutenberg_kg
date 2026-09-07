# Foundation Models returns different completions for identical prompts

| Field | Value |
|---|---|
| **Author** | Eric G. Suchanek, PhD (Flux-Frontiers) |
| **Date** | 2026-09-07 |
| **Status** | Filed upstream; no action available in this repo |
| **Affects** | `GutenbergKGKit.OnDeviceSynthesis` on iPad hardware |
| **Evidence** | `fm_divergence_*.json` in this directory |

---

## Summary

An on-device `LanguageModelSession` returns materially different completions for a
byte-identical instruction set and prompt at temperature 0, depending only on which
device runs it. Both devices run build `24A5430a`. The iPad enters a repetition loop
and quotes a single source passage; the iPhone synthesizes correctly across all five.

This is not a defect in this project. It is recorded here because it cost a full
investigation to isolate, and because anyone comparing answers across devices will
otherwise reach for the same wrong explanations in the same order.

## Environment

| Field | iPad Pro 11-inch (M4) | iPhone 17 Pro | Status |
|---|---|---|---|
| Hardware | `iPad16,3` | `iPhone18,1` | differs |
| System | 27.0 (`24A5430a`) | 27.0 (`24A5430a`) | identical |
| Model path | on-device | on-device | identical |
| Temperature | 0 | 0 | identical |
| App binary | same `.app` product | same `.app` product | identical |

## What was held constant

Traces captured 21 seconds apart from the same question:

| Measurement | `iPad16,3` | `iPhone18,1` | Status |
|---|---|---|---|
| Question | `circles of Hell` | `circles of Hell` | identical |
| Instructions SHA-256 | `89dfc16116d9d769` | `89dfc16116d9d769` | identical |
| **Prompt SHA-256** | **`e24dd2bf123468fe`** | **`e24dd2bf123468fe`** | **identical** |
| Prompt length | 2107 chars | 2107 chars | identical |
| Source passages | 5 (20 dropped) | 5 (20 dropped) | identical |
| Estimated prompt tokens | 777 | 777 | identical |
| Completion length | 302 chars | 847 chars | **diverges** |
| Lines / unique lines | 6 / 3 | 5 / 5 | **diverges** |
| Elapsed | 4041 ms | 5021 ms | diverges |

The prompt digests match. Whatever produced the difference happened after the
framework received the request.

## The divergence

The iPad quotes source passage 3 verbatim, then emits it a second time:

```
Five centuries and more,
T for that lukewarmness was fain to pace
Round the fourth circle. (Dante Alighieri, *The Divine Comedy* (Cary's Translation))

Five centuries and more,
T for that lukewarmness was fain to pace
Round the fourth circle. (Dante Alighieri, *The Divine Comedy* (Cary's Translation))
```

The iPhone synthesizes across all five passages, as the instructions ask:

```
In *The Divine Comedy* (Cary's Translation), Dante describes the circles of Hell as follows:

- The circle remaining after the gulf in Malebolge, dark-stained rock, contains ten
  trenches sunk in its hollow bottom, between the gulf and the base of the high craggy banks.
- A circle of fire wheels around the point, more rapid than the motion that first girds
  the world, with successive circles enclosing each other until the seventh reach's
  circumference is so ample that its bow, within the span of Juno's messenger, lies
  scarcely held entire. Beyond the seventh, two more circles follow.
- The fourth circle is described as one around which the lukewarmness was fain to pace
  for five centuries and more.
- The lowest place, the lowest circle, is obscurest, farthest from heaven's all-circling
  orb, from which a spirit is drawn from Judas' circle.
```

A macOS 27.0 (`26A5425a`) host running the same code against the same corpus produces a
completion that is **byte-identical to the iPhone's**, and does so identically across
three consecutive runs:

| Platform | Prompt SHA-256 | Completion SHA-256 | Chars |
|---|---|---|---|
| macOS 27.0 `26A5425a` | `e24dd2bf123468fe` | `c4f936174e92e245` | 847 |
| `iPhone18,1` 27.0 `24A5430a` | `e24dd2bf123468fe` | `c4f936174e92e245` | 847 |
| `iPad16,3` 27.0 `24A5430a` | `e24dd2bf123468fe` | *(differs)* | 302 |

Three platforms, one prompt digest. Two produce the same completion to the byte; the
iPad is the sole outlier. Determinism at temperature 0 therefore holds across hardware
generations and across macOS and iOS, and fails only here.

## Ruled out

Each eliminated by direct measurement, not by inspection:

| Hypothesis | How it was eliminated |
|---|---|
| Sampling variance | Temperature pinned to 0. Three consecutive macOS runs byte-identical. |
| OS version skew | Both devices on `24A5430a`. An earlier real mismatch was corrected and retested. |
| Differing input data | All 12 corpus files identical by name and size; prompt digests match. |
| Application build skew | The same signed `.app` product installed to both from one build. |
| Genre scope | Both scoped to `world-literature`; `kgsQueried` counts packs, not genres. |
| Stale model assets | Apple Intelligence cycled off and on, device rebooted. No re-download; unchanged. |
| Low Power Mode | Confirmed off on the iPad. |
| Client-side accumulation | Streaming replaces rather than appends; duplication is in the raw completion. |
| Duplicate rendering | `AssistantTurnView` renders the answer once. |
| Context overflow | 777 estimated tokens against a 4,096-token window, on both devices. |
| Guardrail refusal | No `GenerationError` raised; a normal completion was returned. |

## Secondary observation

A second iPad run with the question capitalised differently, `Circles of hell`, prompt
digest `0bb062809e8d893d`, did not duplicate but still returned the same single quoted
passage and nothing else (150 characters, 1765 ms). The iPad's failure to synthesize is
therefore not specific to one prompt; the repetition loop is a further degradation on
top of it.

## How the evidence was captured

`SynthesisTrace` (`Sources/GutenbergKGKit/Synthesis/SynthesisTrace.swift`) writes one
JSON file per synthesis call into `Application Support/Diagnostics`, recording the
session instructions, the user prompt, and the raw completion verbatim, plus hardware
identifier, OS build, timings, and a line/unique-line count that makes a repetition loop
countable rather than a judgement call. It writes after `.completed` is yielded, so a
failure there costs a diagnostic and never an answer.

Files are pulled with:

```sh
xcrun devicectl device copy from --device <udid> \
  --domain-type appDataContainer --domain-identifier com.fluxfrontiers.knowledgepress \
  --source "Library/Application Support/Diagnostics" --destination <local>
```

## Standing note for future comparisons

Only 5 of 25 retrieved passages reach the model on every device, because the on-device
window is 4,096 tokens. That is the real constraint on answer quality across the board
and is worth addressing on its own terms. It is not the cause of this divergence: both
devices packed the same 5.
