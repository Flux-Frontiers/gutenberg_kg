# Foundation Models returns different completions for identical prompts

| Field | Value |
|---|---|
| **Author** | Eric G. Suchanek, PhD (Flux-Frontiers) |
| **Date** | 2026-09-07, addenda 2026-09-08 |
| **Status** | Filed upstream. Investigation complete: OS build eliminated by experiment; the remaining variable is the chip. No action available in this repo. |
| **Affects** | `GutenbergKGKit.OnDeviceSynthesis` on `iPad16,3` and `iPad16,1` |
| **Finding** | One prompt digest, three distinct completions, across three iOS devices on **one identical build** |
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

**Addendum, 2026-09-08:** a fourth device, `iPad16,1`, produces a *third* distinct
completion from the same prompt digest. `iPad16,1` was then updated from build
`24A5390f` to `24A5430a` -- the build the other two iOS devices run -- and its
completions did not change by a single byte, which eliminates the OS build as the
variable. See the addenda at the end. The original report as filed is preserved
unchanged above them.

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

---

## Addendum, 2026-09-08: a third behavior on `iPad16,1`

The day after filing, the same question was run on an iPad mini (A17 Pro, `iPad16,1`).
It produced a completion unlike either of the two already recorded: the answer's
*substance* is correct, but it is wrapped in a confabulated tool-call exchange. This
app registers no tools with the framework. The model invented one, "called" it,
declared it unnecessary, and then answered.

### Held constant, again

| Measurement | `iPad16,1` | Reference (`iPhone18,1`, macOS) | Status |
|---|---|---|---|
| Question | `circles of Hell` | `circles of Hell` | identical |
| Instructions SHA-256 | `89dfc16116d9d769` | `89dfc16116d9d769` | identical |
| **Prompt SHA-256** | **`e24dd2bf123468fe`** | **`e24dd2bf123468fe`** | **identical** |
| Source passage IDs | same 5, same order | same 5, same order | identical |
| Passages used / dropped | 5 / 20 | 5 / 20 | identical |
| Temperature | 0 | 0 | identical |
| Completion SHA-256 | `37c9dd60745b6efe` | `c4f936174e92e245` | **diverges** |
| Completion length | 653 chars, 15 lines / 15 unique | 847 chars, 5 / 5 | **diverges** |

### The completion, verbatim

````
[Project Gutenberg literary guide]

Tool call: get_circle_references

```json
{
  "work": "The Divine Comedy (Cary's Translation)",
  "author": "Dante Alighieri",
  "topic": "circles of Hell"
}
```

[No tool call needed]

**Answer:**

Dante Alighieri, *The Divine Comedy (Cary's Translation)* describes the following circles of Hell:

- **Fourth circle** – Five centuries and more, the lukewarmness was fain to pace round this circle.
- **Fourth circle** – Water moves in the round chalice, even as the blow compels it inwardly or from without.
- **Judas’ circle** – Described as the lowest place, obscurest, and farthest from heaven’s all-circling orb.
````

`get_circle_references` does not exist. Neither does the bracketed framing. The three
bullets that follow are a reasonable synthesis of the packed passages.

### It is reproducible, not a one-off

A second question on the same device, `pillar of salt` (prompt digest
`fa5f559d45e90fb2`), did the same thing with a *different* invented tool name:

```
tool_call: {"tool_name": "extract_references", "filters": {"text": "pillar of salt", "source_type": "sacred-texts"}} Marshaling the provided source passages, here is the result:

- [sacred-texts · The Bible] - "And his wife looked back from behind him, and she became a pillar of salt." (Lot entering into Zoar)
```

The tool name changes with the question, which is what a model generating plausible
scaffolding from the question's shape looks like. The quoted verse is the correct one.

The same question on `iPad16,3` has the same prompt digest, `fa5f559d45e90fb2` --
proven from its trace, not assumed -- and returned only a three-line stub with no
verse at all, 74 characters:

```
The Bible (Lot) mentions a pillar of salt:
Author: Unknown
Work: [lot]
```

(The model's trailing double-spaces, a Markdown line break, are elided here; the
digest is over the exact bytes.) It returned that stub three times across two
sessions, byte-identical each time, completion digest `6975f008aa6f596f`. So this is
a second question, with a second proven-identical prompt, on which the two iPads
diverge -- and on which each iPad is perfectly consistent with itself.

So the two iPads fail in *opposite* directions from one prompt: `iPad16,3` degrades
the substance and keeps the form; `iPad16,1` keeps the substance and invents form
around it.

### Four platforms, one prompt digest, three completions

| Platform | Chip | Build | Completion SHA-256 | Chars | Shape |
|---|---|---|---|---|---|
| macOS 27.0 | M5 Max | `26A5425a` | `c4f936174e92e245` | 847 | correct synthesis |
| `iPhone18,1` | A19 Pro | `24A5430a` | `c4f936174e92e245` | 847 | byte-identical to macOS |
| `iPad16,3` | M4 | `24A5430a` | `3eb5d65be9aecfac` | 302 | one passage quoted twice |
| `iPad16,1` | A17 Pro | `24A5390f`, then `24A5430a` | `37c9dd60745b6efe` | 653 | confabulated tool call, correct answer |

The original report described the divergence as binary: one platform wrong, two
right. It is not binary. Three of four hardware classes disagree with each other,
and only the two that agree are the two that happen to sit on either side of the
iPads in the product line.

### One confound, stated rather than buried -- since resolved

`iPad16,1` was on build `24A5390f`; the other two iOS devices were on `24A5430a`.
Build alone could not explain the original divergence, since `iPhone18,1` and
`iPad16,3` share a build and disagree. But it could have been part of why `iPad16,1`
did a *third* thing rather than `iPad16,3`'s thing.

The experiment was run the same day. See the second addendum below: the build was
eliminated.

### Retrieval breadth was changed deliberately, and changed nothing

Screenshots showed the two iPads retrieving different passage counts for the same
query, which looked like a confound: if retrieval differs by device, so might the
prompt. It is not a confound. The Results slider was moved by hand on `iPad16,3`,
between runs, to test whether retrieving more or fewer passages would shift the
answer.

It did not, on either question:

| Question | Run | Retrieved | Reached model | Completion SHA-256 |
|---|---|---:|---:|---|
| `pillar of salt` | `21:09:00Z` | 25 | 5 | `6975f008aa6f596f` |
| `pillar of salt` | `21:09:46Z` | 14 | 5 | `6975f008aa6f596f` |
| `circles of Hell` | 2026-09-07 | 25 | 5 | `3eb5d65be9aecfac` |
| `circles of Hell` | `21:10:16Z` | 14 | 5 | `3eb5d65be9aecfac` |

Byte-identical completions across a near-halving of the retrieved set, on both
questions, on the device that fails. The reason is the context budget: only 5
passages reach the model either way, and the same 5 rank highest whether 14 or 25
are retrieved, so the prompt is unchanged -- digest `e24dd2bf123468fe` for both
`circles of Hell` rows, the same digest every other device produced.

Two things follow. The differing counts in the screenshots were a slider, not
hardware, and never reached the model. And **retrieval breadth is not a lever on
this failure**: "the app packed too much context" is eliminated as a cause, by
experiment rather than by argument.

### The wrong completion is stable, and it is prompt-specific

`iPad16,3` re-ran `circles of Hell` on 2026-09-08 at `21:10:16Z`: prompt digest
`e24dd2bf123468fe`, completion digest `3eb5d65be9aecfac` -- byte-identical to its run
the day before. The device is deterministic; it is deterministically wrong. That rules
out flakiness and means the failure will reproduce for whoever picks up the report.

It is not a blanket failure of the device, either. In the same session `iPad16,3`
answered three other questions sensibly: `descriptions of the Great Fire of London`
(720 characters, a correct list from Pepys), `What great battles were described?` (a
correct numbered list from Plutarch and Thucydides), and `Describe the Trojan war`
(824 characters of coherent prose). Those prompts have no cross-device reference yet,
so they prove nothing about divergence. They do show the model on this device is
capable, and that whatever triggers the loop and the stub is specific to certain
prompts. `circles of Hell` and `pillar of salt` are two known triggers.

### Evidence

- `fm_divergence_ipad16_1_20260908T210720.json` -- `circles of Hell` on `iPad16,1`, the run quoted above
- `fm_divergence_ipad16_1_20260908T210607.json` -- `pillar of salt` on `iPad16,1`
- `fm_divergence_ipad16_3_20260908T211016.json` -- `circles of Hell` on `iPad16,3`, byte-identical to its 2026-09-07 completion
- `fm_divergence_ipad16_3_20260908T210900.json` and `..._20260908T210946.json` -- `pillar of salt` on `iPad16,3`, 25 and then 14 passages retrieved, same prompt digest, same completion

All pulled from the devices the same way as the originals. The `answer` field in each
is the raw completion; the tool-call text is in the file, not in the rendering.

---

## Addendum 2, 2026-09-08: the OS build is eliminated

`iPad16,1` was updated from build `24A5390f` to `24A5430a` -- the build `iPhone18,1`
and `iPad16,3` already ran -- and both questions were re-asked. **Nothing changed.**

| Question | Build | Prompt SHA-256 | Completion SHA-256 |
|---|---|---|---|
| `circles of Hell` | `24A5390f` | `e24dd2bf123468fe` | `37c9dd60745b6efe` |
| `circles of Hell` | `24A5430a` | `e24dd2bf123468fe` | **`37c9dd60745b6efe`** |
| `pillar of salt` | `24A5390f` | `fa5f559d45e90fb2` | `9c6bf98353bf1fea` |
| `pillar of salt` | `24A5430a` | `fa5f559d45e90fb2` | **`9c6bf98353bf1fea`** |

Byte-identical completions across an OS update, on both questions. The confabulated
tool call survived intact, including the invented tool names `get_circle_references`
and `extract_references`. A second `pillar of salt` run on the new build returned the
same digest a third time.

### What this leaves

All three iOS devices now run build `24A5430a`. They still produce three different
completions from one prompt:

| Device | Chip | Build | Completion SHA-256 | Behavior |
|---|---|---|---|---|
| `iPhone18,1` | A19 Pro | `24A5430a` | `c4f936174e92e245` | correct synthesis |
| `iPad16,3` | M4 | `24A5430a` | `3eb5d65be9aecfac` | one passage quoted twice |
| `iPad16,1` | A17 Pro | `24A5430a` | `37c9dd60745b6efe` | confabulated tool call |

Identical build, identical prompt digest, identical instructions, temperature 0,
identical five source passages. Three completions. macOS on `26A5425a` agrees with
`iPhone18,1` to the byte, so the correct behavior spans two operating systems.

The OS build is eliminated as the variable. What remains that differs is the silicon
and whatever model assets or execution path the framework selects for it.

### Every device is self-consistent

Each device reproduces its own completion exactly, which is what makes this
actionable rather than anecdotal:

| Device | Question | Runs | Distinct completions |
|---|---|---:|---:|
| macOS | `circles of Hell` | 3 | 1 |
| `iPad16,3` | `circles of Hell` | 2, across two days | 1 |
| `iPad16,3` | `pillar of salt` | 3 | 1 |
| `iPad16,1` | `circles of Hell` | 2, across an OS update | 1 |
| `iPad16,1` | `pillar of salt` | 3, across an OS update | 1 |

Determinism at temperature 0 holds *within* every device tested. It fails *between*
them.

### Evidence

- `fm_divergence_ipad16_1_20260908T214329.json` -- `circles of Hell` on `24A5430a`
- `fm_divergence_ipad16_1_20260908T214316.json` -- `pillar of salt` on `24A5430a`
- `fm_divergence_ipad16_1_20260908T214356.json` -- `pillar of salt` again, same digest
