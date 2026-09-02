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
│   │   ├── Embedding/                WordPieceTokenizer, BGEEmbedder (Core ML)
│   │   ├── Retrieval/                RetrievalEngine + WorkerRetrieval,
│   │   │                             CorpusPacks/PassagePack/CatalogPack,
│   │   │                             VectorIndex (mmap + vDSP), LocalRetrieval
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
| Passages | the installed corpus packs | yes |
| Browse | the same packs | yes |

With packs installed the app answers with the network off. Build them with
`gutenkg export-swift` and `gutenkg export-embedder`, then copy the output into
Application Support ▸ Corpus — see [docs/ON_DEVICE.md](../docs/ON_DEVICE.md).
With no packs the app falls back to the worker, so nothing breaks before the
first download.

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
