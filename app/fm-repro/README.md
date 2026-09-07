# FM Repro

A minimal reproducer for a Foundation Models defect: an on-device
`LanguageModelSession` returns materially different completions for a
byte-identical prompt at temperature 0, depending on which device runs it.

One Swift file, no dependencies, no network, no data files. Nothing in this
project can be the cause of what it demonstrates.

## What it shows

| Platform | System | Result |
|---|---|---|
| `iPhone18,1` | 27.0 (24A5430a) | 847 characters, correct synthesis |
| macOS (M5 Max) | 27.0 (26A5425a) | 847 characters, **byte-identical to the iPhone** |
| `iPad16,3` | 27.0 (24A5430a) | 302 characters: one source passage quoted, then repeated verbatim |

The iPad both fails to follow the system instructions, which ask for an answer
drawn from all the supplied passages, and emits its output twice.

## Running it

```sh
brew install xcodegen
cd app/fm-repro && xcodegen generate
open FMRepro.xcodeproj
```

Select a device and run, then tap **Run 3 times**. The app reports the
hardware identifier, the OS version with build number, and the SHA-256 of both
the instructions and the prompt, so two devices can be compared without
trusting that they were given the same input.

Signing needs a development team selected in Xcode once, because the bundle
identifier is new. To check that it compiles without signing at all:

```sh
xcodebuild -project FMRepro.xcodeproj -scheme FMRepro \
  -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
```

## The prompt

`Sources/FMReproApp.swift` carries the instructions and prompt verbatim, taken
from a captured trace rather than retyped. Their digests must read:

| String | Length | SHA-256 (first 16) |
|---|---|---|
| Instructions | 387 | `89dfc16116d9d769` |
| Prompt | 2107 | `e24dd2bf123468fe` |

The app prints both at launch. If they differ from the table, the file has been
edited and the comparison is no longer against the reported input.

The passages in the prompt are from two public-domain English translations of
Dante's *Divine Comedy* (Cary and Longfellow), retrieved by the parent project
for the question "circles of Hell". They are included only because they are the
exact input that produced the divergence.

## Background

Full investigation, including what was ruled out and by which measurement:
`analysis/FOUNDATION_MODELS_DIVERGENCE_20260907.md` in the parent repository,
with the four raw traces alongside it.
