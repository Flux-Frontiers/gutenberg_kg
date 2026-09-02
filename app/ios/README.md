# The Knowledge Press — iPhone app

**First time? Follow [../RUNBOOK.md](../RUNBOOK.md)** — this file is the
target's reference, the runbook is the ordered checklist.

The iOS shell. One file (`Sources/KnowledgePressApp.swift`); everything it
draws comes from the `KnowledgePressUI` target in
[`../GutenbergKGKit`](../GutenbergKGKit), shared with the Mac app.

## What runs where

| | Where it runs | Needs the network |
|---|---|---|
| Answer | Apple Foundation Models, on the phone | no |
| Passages | the installed corpus packs | no |
| Browse | the same packs | no |

With the packs installed the app is offline end to end. Build them on the Mac:

```sh
gutenkg export-swift        # core.pack, gutenberg.pack + .vectors, diaries.pack + .vectors
gutenkg export-embedder     # BGEEmbedder.mlpackage, vocab.txt, embedder.json
```

…then copy that directory into the app's `Application Support/Corpus`. Settings
▸ Corpus reports what was found, and why if it would not open.

Without packs the app falls back to the worker for passages, so it is usable
before the ~800 MB download.

## Requirements

- **iOS 26 or later** on an Apple Intelligence device (iPhone 15 Pro or newer)
  for on-device answers. Older phones run everything else and show why the
  on-device engine is unavailable — they are not blocked from the app.
- Xcode 26 (iOS 26 SDK) to build.
- A worker reachable from the phone: `make up` at the repo root, then set the
  worker URL in Settings to `http://<your-mac>.local:8000`. `localhost` is the
  phone, not the Mac — the app cannot find your worker there.

## Build

With [XcodeGen](https://github.com/yonaskolb/XcodeGen):

```sh
brew install xcodegen
cd app/ios
xcodegen generate
open KnowledgePress.xcodeproj
```

Set your signing team on the KnowledgePress target, pick your device, run.

Without XcodeGen, the same target by hand:

1. **File ▸ New ▸ Project ▸ iOS ▸ App**, name `KnowledgePress`, interface
   SwiftUI, language Swift. Save it in `app/ios/`.
2. Delete the generated `ContentView.swift` and `<name>App.swift`; drag in
   `Sources/KnowledgePressApp.swift` instead.
3. **File ▸ Add Package Dependencies… ▸ Add Local…**, choose
   `app/GutenbergKGKit`, and add the **KnowledgePressUI** library product to
   the app target.
4. In the target's Info tab add `NSAppTransportSecurity` →
   `NSAllowsLocalNetworking` = YES, and an `NSLocalNetworkUsageDescription`
   string, so the phone may talk to the worker over plain HTTP on your LAN.
5. Set the deployment target to iOS 18 and your signing team.

## Simulator note

The Simulator does not run Apple Foundation Models. `SystemLanguageModel
.default.availability` reports `deviceNotEligible` there, the app says so in
Settings, and the answer engine falls back — which is the same path an
ineligible phone takes, so it is worth seeing once. Test real answers on
hardware.
