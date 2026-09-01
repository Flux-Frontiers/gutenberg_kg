# The Knowledge Press — native app (macOS-first)

Swift workspace for the native app described in
[analysis/APP_ARCHITECTURE.md](../analysis/APP_ARCHITECTURE.md).

## Layout

```
app/
└── GutenbergKGKit/        Swift package — the headless app core
    ├── Sources/GutenbergKGKit/
    │   ├── WorkerClient.swift   async /runsync client (Swift port of
    │   │                        kg_utils.worker.client.WorkerClient)
    │   ├── Models.swift         Codable mirrors of the worker JSON schema
    │   └── WorkerError.swift
    └── Tests/                   Swift Testing suites (fixture JSON mirrors
                                 real worker responses — the schema contract)
```

The `KnowledgePress` SwiftUI app target (Phase 1 thin client) builds on this
package; retrieval/synthesis/imaging backends (Phases 2–4) land here as
additional modules.

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

## Live smoke test

Start the worker (`make up` or `make run` at repo root), then any client call
against `http://localhost:8000` — e.g. `WorkerClient(baseURL:).stats()` —
returns live corpus totals. The fixture JSON in
`Tests/GutenbergKGKitTests/ModelDecodingTests.swift` is the worker-schema
contract: update it in lockstep with `serve/handler.py`.
