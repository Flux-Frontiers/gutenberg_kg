# The Knowledge Press — native app

Swift workspace for the native app described in
[analysis/APP_ARCHITECTURE.md](../analysis/APP_ARCHITECTURE.md).

## Layout

```
app/
├── GutenbergKGKit/                 Swift package — the app core
│   ├── Sources/GutenbergKGKit/     headless, testable
│   │   ├── WorkerClient.swift        async /runsync client (Swift port of
│   │   │                             kg_utils.worker.client.WorkerClient)
│   │   ├── Models.swift              Codable mirrors of the worker JSON schema
│   │   ├── QueryOrchestrator.swift   retrieval → budget → synthesis, streamed
│   │   ├── Retrieval/                RetrievalEngine protocol, WorkerRetrieval
│   │   └── Synthesis/                SynthesisBackend protocol, ContextBudgeter,
│   │                                 SynthesisPrompt, OnDeviceSynthesis
│   ├── Sources/KnowledgePressUI/   shared SwiftUI — chat, browse, settings,
│   │                               and one root view per platform
│   ├── Sources/KnowledgePress/     macOS shell (`swift run KnowledgePress`)
│   └── Tests/                      Swift Testing suites
└── ios/                            iPhone shell + XcodeGen spec — see its README
```

## Where the work happens

| | Runs | Offline |
|---|---|---|
| Answer | Apple Foundation Models, on the device | yes |
| Passages | the GutenbergKG worker | no — Phase 2 |

On-device inference is in (Phase 3 of the architecture doc). On-device
retrieval is close: `gutenkg export-swift` now builds the corpus packs
([docs/ON_DEVICE.md](../docs/ON_DEVICE.md)), and what is left is Swift-side —
a Core ML `bge-small` query embedder and a `CorpusStore` that reads the packs.
`AppModel.retrievalEngine` is the one line that changes when it lands.

The on-device engine needs macOS 26 / iOS 26 on Apple Intelligence hardware.
Everywhere else the app still runs — the provider picker says why the engine
is unavailable and falls back to the worker, the same way `chat.py` falls back
when no local model is reported.

## Build & test

```sh
cd app/GutenbergKGKit
swift build
swift test
```

`swift test` needs the full Xcode toolchain for the Testing framework
(CommandLineTools alone can build the library but not run the tests). If
`xcode-select -p` reports CommandLineTools, either switch once with
`sudo xcode-select -s /Applications/Xcode-beta.app/Contents/Developer` or
prefix commands with `DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer`.

The iPhone app builds from `app/ios` — see [ios/README.md](ios/README.md).

## Live smoke test

Start the worker (`make up` or `make run` at repo root), then any client call
against `http://localhost:8000` — e.g. `WorkerClient(baseURL:).stats()` —
returns live corpus totals. The fixture JSON in
`Tests/GutenbergKGKitTests/ModelDecodingTests.swift` is the worker-schema
contract: update it in lockstep with `serve/handler.py`.

`ContextBudgeterTests` is the other contract worth keeping honest: it pins the
prompt shape against `kg_utils/synthesis/_text.py`, so a change there should
break a test here.
