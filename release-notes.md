# Release Notes -- v1.22.0

> Released: 2026-09-16

### Added

- **Knowledge Press Forest** (`web/knowledge-press-forest/`): React + Vite +
  `@react-three/fiber` walkable grove, one tree per work. Grove atlas with
  minimap jump, carriage roads, optional ring tour, named signposts,
  space-colonization tree skeletons, day/night toggle persisted with season,
  dismissable book card on phone.
- **`scripts/export_web_catalog.py`**: generates `catalogPart*.ts` from DocKG
  chunk-node counts per book. Make target and
  `tests/test_export_web_catalog.py`.
- **In-app help** (`HelpContent.swift`, `HelpView.swift`): six topics, opened
  from a Settings row, a macOS Help menu item, or a per-section ⓘ. Content is
  data, not layout. `HelpContentTests` fails on unresolvable topic ids, empty
  bodies, unbalanced `**`, a Synthesis control with no paragraph, an
  unnamed engine, privacy-page drift, and guardrail-page drift.
- **Swift/Python synthesis prompt contract**: `gutenberg_kg.synthesis_prompts`
  re-exports `RAG_SYSTEM` and `IMAGE_REWRITE_SYSTEM` from `kg_utils` and adds
  `GUIDE_SYSTEM`. Both handlers select via `SYNTH_PROMPT=guide|worker`
  (default `guide`; unknown values fall back rather than raise).
  `tests/test_synthesis_parity.py` parses the Swift source, compares each
  literal to its Python constant, checks `Budget.worker.maxPassages` against
  `SYNTH_MAX_K`, and fails if a handler re-inlines a prompt. No toolchain,
  corpus or device required; 0.01s.
- **`SynthesisTuning`**: temperature, greedy, per-work cap override,
  instruction set, permissive guardrail — persisted in `UserDefaults`, exposed
  as a Settings section, recorded in every trace. Mac app gains
  `--ask QUESTION [--corpus|--engine|--temperature|--greedy|--cap|--instructions|--permissive]`
  via `make mac-dev`; `scripts/synth_replay.py` replays a trace through
  `/usr/bin/fm`. Measurements in `analysis/SYNTHESIS_TUNING_NOTES.md`.
- **iOS App Store submission support**: corpus bundled as a folder reference
  (743 MB packs, ~296 MB compressed download), opened in place —
  `CorpusPacks.installed()` still prefers Application Support.
  `PrivacyInfo.xcprivacy` (both platforms, declaration CA92.1),
  `ITSAppUsesNonExemptEncryption: false`, `ExportOptions.plist`, and
  `make ios-stage-corpus|ios-unstage-corpus|ios-archive|ios-upload`.
- **`TRADEMARK.md`**: claims names and artwork separately from the code.

### Changed

- **`app/` relicensed to `LicenseRef-Flux-Frontiers-Proprietary`.** Elastic-2.0
  restricts SaaS use but not redistribution, so it did not prevent republishing
  `app/` to the App Store under another name. 64 Swift files change SPDX header
  and name the license file. `app/fm-repro/` stays Elastic-2.0 (it is an Apple
  Foundation Models reproducer). Everything outside `app/` is unchanged;
  root `LICENSE` gains a scope note.
- **License and trademark owner is an individual**, not the `Flux-Frontiers`
  trade name, which cannot hold copyright or be a party to a grant.
  `app/LICENSE` runs to Eric G. Suchanek and to any later assignee.
- **PCC packing and sampling**: per-work cap 2 → 4 (the cap exists for the
  on-device model's repetition looping; the server model does not need it).
  Temperature 0 → 0.2. `SynthesisPrompt` gains `guideInstructions`;
  `ragInstructions` unchanged so engines remain comparable.
- **iOS deployment target 18.0 → 26.0.** `OnDeviceSynthesis` is
  `@available(iOS 26.0)` and `PrivateCloudSynthesis` 27, so iOS 18 builds had
  no answer engine. 26 is also the Apple-Hosted Background Assets floor.
- **Trademark filing planning moved to `kgrag_priv`**; `TRADEMARK.md` and
  `app/LICENSE` stay public.

### Fixed

- **`runpod/handler.py` prompt drift.** Its inlined RAG paraphrase had dropped
  "Do NOT use any prior knowledge" and "Never contradict or override what the
  passages say", and joined passage headers with `" | "` instead of `" · "`.
  In production since it was written; no test covered it.
- **PCC guardrail cut was silent.** The filter fires after text streams, and
  the failure label sat behind an `else` the partial answer never reached.
  `SynthesisFailure.guardrailCutShort` now renders under the text and the trace
  is still written. Catch widened to `LanguageModelError` (macOS 27 throws it
  for both backends; an iOS 26 `GenerationError` catch matched nothing).
- **CI build: `GenerationOptions(sampling:)`, not `(samplingMode:)`.**
  `OnDeviceSynthesis.swift` has no `#if compiler(>=6.4)` gate, so it must build
  against CI's older SDK. Same `SamplingMode` type — label only.
- **`AboutView` reported "Elastic License 2.0"** after the license split.
- **Help sheet Done button did not render**; it was attached outside
  `HelpView`'s own `NavigationStack`.
- **`npm install` failed**: `@react-three/fiber` 9.7 peer-requires react
  `<19.3` and the caret resolved 19.3.0. react/react-dom pinned `~19.2.0`.
  `GENRE_LABELS` keys corrected to real corpus dirs (`spanish`,
  `audel-electric`).
- **Stoic quest rendered as a grove card with no backing book.**

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
