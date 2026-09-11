# Release Notes -- v1.21.0

> Released: 2026-09-11

### Added

- **The cross-pack merge is gated against the Python reference, on the real
  corpus.** `golden.json` recorded one pack at a time, so the golden gate could
  pass while the app and the worker folded books and diaries differently --
  which is how the round-robin below shipped unnoticed. `build_golden` now
  records the `corpus=all` ranking per query, produced by the worker's own
  `merge_by_rank` from the same per-pack lists it already records, plus
  `rescue_tolerance`. `GoldenParityTests` reproduces that ranking within the
  existing tolerance and asserts the app's constant equals the exporter's by
  name, before any ranking symptom could show a drift. Two new suites sit
  beside it: `CrossPackMergeTests` characterises the merge over synthetic
  lists using measured cosines, and `CrossPackProbeTests` prints the merged
  window for all twelve golden queries against `GUTENBERG_PACKS` -- every
  number in this release's retrieval entries came from it.

- **Source-passage cards say which ones reached the model.** The stats line
  read "3 of 25 in context" and nothing said which three. `SynthesisMetrics`
  gains `packedIds`, in prompt order, and each matching card gets an
  **in context** badge. Cards whose turn recorded nothing -- the worker path,
  where packing happens server-side, and chats saved before this -- stay
  unmarked rather than all reading as left out. The decoder is hand-written so
  a `conversation.json` written before the field existed still opens.

- **Reset search to defaults, in Settings.** Results, Min score and Semantic
  floor could be moved but not put back short of remembering 25, 0.5 and 0.20.
  The numbers now live in `AppModel.SearchDefaults` so the reset restores them
  rather than restating them; the button disables itself when nothing has
  changed. Scope is deliberately untouched: it is persisted because it is a
  lens, not a preference, and a button about sliders must not undo the
  reader's narrowing.

- **`make ios-build` and `make ios-deploy-all`.** A signed device build, and
  an install-and-relaunch across every reachable physical device in one pass.
  The Team ID is resolved from the machine -- a provisioning profile's
  `TeamIdentifier`, falling back to the Developer ID certificate -- rather
  than carried in `project.yml`, which xcodegen wipes anyway. Not from the
  Apple Development certificate: its parenthesised value is the certificate's
  own id, and a build signed against it fails in a way that names neither.

### Changed

- **`corpus=all` ranks across packs on cosine, except where BM25 did the
  finding.** Books and diaries were folded by fused rank alone. Node ids never
  repeat across the two corpora, so every hit scored from exactly one list,
  rank 0 tied rank 0, and the tie broke first-seen -- a strict round-robin.
  Measured on all twelve golden queries, every one gave four diaries exactly
  5 of the top 10, displacing 74 book passages that scored higher; on
  "categorical imperative" the model got Kant interleaved with Pepys on the
  blessing of bells.

  Sorting the union by cosine is the obvious fix and regresses the bug the
  rank merge exists for: a lexically-rescued hit has low cosine by
  construction, and a score sort drops the pillar-of-salt verse entirely. The
  merge now carries which hits BM25 found outside the dense top k; those keep
  their fused rank and everything else competes on cosine, which is directly
  comparable across packs. Then a second half: FTS5 stems "Imperator" and
  "imperative" to one token, and "moral", "duty" and "categorical" all occur
  in diaries, so BM25 rescues plenty that is no literal match. Measured
  against the field's best dense score, every legitimate rescue sits within
  0.141 of it and every rescue that displaced a better passage sits at 0.155
  or beyond; `rescueTolerance` / `RESCUE_TOLERANCE` is 0.15, and a rescue past
  it keeps its hit but loses its pin. Swift and Python change together.

  A rescue's fused rank is a floor, not a slot: it takes the better of that
  and the rank its cosine earns. Pinned to the slot alone, a rescue whose
  fused rank fell past `k` after interleaving sat outside the window while
  weaker unpinned hits filled it -- caught on the worker, where the DocKG's
  FTS rescues different hits than the pack's, holding two *Groundwork*
  passages at 0.766 below two Boswell entries at 0.688.

  Result, top 10 across the twelve queries: diary passages 60 -> 27, cosine
  inversions 197 -> 54, and composition now tracks the question -- none for
  the whiteness of the whale, five for the Great Fire where Pepys and Evelyn
  outscore the books. The verse holds rank 3, exactly where it was. Design
  and every measurement: `analysis/CROSS_PACK_FUSION_PLAN.md`.

- **On-device synthesis stops looping on repeated sources.** Apple's
  on-device model was repeating text verbatim under greedy decoding when
  several packed passages came from the same translation. Temperature moves
  from 0 to 0.2, and `ContextBudgeter` gains `maxPassagesPerSource` (default
  2) so one book cannot dominate the packed context; with that in place
  `Budget.onDevice` goes back to 10 passages, which the budget always had
  room for -- five 500-character passages spent under a quarter of it.

  The cap then needed two corrections of its own. It backfilled: a capped-out
  hit freed its slot and the walk continued, so "categorical imperative"
  retrieved 19 *Groundwork* passages, kept 2, and refilled with the five diary
  entries the merge had just demoted. A capped-out hit now spends its slot;
  the cap thins the top `maxPassages` by rank and reaches no further. And it
  never bound on a diary: keyed by `sourcePath`, and a diary is one file per
  entry, so every Pepys day was its own source. Keyed by title now, which
  still separates the two Divine Comedy translations.

- **The app opens on an empty chat.** Launching reopened the newest saved
  conversation, so a relaunch always landed on the previous session's question
  in front of a reader who came back to ask a different one. That restore was
  a stopgap from before the sidebar existed, and said so; the sidebar reaches
  saved chats now, so a launch reads the list and stops there.

- **KG pins bumped, and the release bumps them before verifying.**
  kgmodule-utils 0.19.1 -> 0.21.0, doc-kg 0.25.0 -> 0.26.0, diary-kg
  0.98.0 -> 0.99.0. `check_pins.py` in the release's verify step only
  confirmed the four pin files agreed with each other; it never moved anything
  to match PyPI, so a release shipped whatever pins were sitting in the repo
  and the next run reported them behind again. The release skill now runs
  `--bump` first.

### Fixed

- **`export-swift --force` deleted the Core ML embedder.** The forced
  re-export cleared every child of its output directory, which is also where
  `export-embedder` writes by default, so `make export-swift` silently
  destroyed `BGEEmbedder.mlpackage`, `vocab.txt` and `embedder.json` -- 66 MB
  that only a separate, pinned toolchain can rebuild -- and left packs whose
  own `manifest.json` declares them unusable without it. The wipe now deletes
  only what the export owns. The instructions that cost the time are fixed
  too: the docstring, the CLI help and the `ImportError` all said
  `poetry run pip install torch transformers coremltools`, which is the one
  thing that cannot work under transformers 5.x; they give the throwaway-venv
  recipe RUNBOOK step 2 had all along.

- **The `ios-*` targets aimed at whichever device was listed first.**
  `devicectl list devices` reports everything ever paired, so the auto-detect
  took a sleeping iPad over the phone on the desk and failed with a
  usage-assertion error that named no device. Resolution now filters on
  `tunnelState`: only `unavailable` is disqualifying, since `disconnected` is
  the resting state of a reachable device between commands. `ios-deploy-all`
  had the same defect in a different form -- it grepped the printed table for
  "available", which a device with a live tunnel does not print -- and so
  found no devices when three were ready.

- **The golden gate misread int8 near-ties as rank drift.** Three diary hits
  for "circles of Hell" at 0.6578 / 0.6577 / 0.6576 -- a tie that numpy's
  argsort and Accelerate's dot product resolve in opposite orders. A plain
  swap is drift 2, inside tolerance, but RRF interleaves a lexical rescue at
  every odd rank, so the outer two swapping read as drift 4. The comment on
  `max_rank_drift` already said a tie swapped is not a ranking fault; the
  check now measures drift to the nearest position held by a tied hit.

- **RUNBOOK: what a stranger has to change, and no team ID in a public repo.**
  Section 6's prerequisites were written from the seat of someone whose App ID
  is already registered; anyone else followed them and failed at provisioning,
  because `com.fluxfrontiers.knowledgepress` is an explicit App ID and unique
  across Apple. A new section says to change `PRODUCT_BUNDLE_IDENTIFIER` first
  and points at `ios-check` / `mac-check` as the no-account thing to try after
  a clone. The team ID, which both Makefile macros resolve at build time
  precisely so it is not written down, was written down in four places; each
  now says `<your-team-id>` and names the command that prints your own.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
