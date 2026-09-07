// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0

import Foundation
import GutenbergKGKit
import Observation

/// Where a turn's answer comes from.
public enum AnswerEngine: String, CaseIterable, Sendable {
    /// Apple Foundation Models, on this device. Nothing leaves the phone.
    case onDevice
    /// Apple Foundation Models, on Private Cloud Compute. Leaves the device —
    /// needs a network connection and draws on the user's iCloud quota — in
    /// exchange for a context window eight times the on-device model's.
    case privateCloud
    /// The worker's oMLX/Ollama/vLLM backend.
    case worker
    /// Passages only — chat.py's "Synthesize" toggle, off.
    case off

    var label: String {
        switch self {
        case .onDevice: return "On-device"
        case .privateCloud: return "Private Cloud"
        case .worker: return "Worker"
        case .off: return "Passages only"
        }
    }

    var detail: String {
        switch self {
        case .onDevice: return "Apple Foundation Models · nothing leaves this device"
        case .privateCloud: return "Apple Foundation Models · Private Cloud Compute · needs internet"
        case .worker: return "oMLX / Ollama / vLLM on the worker"
        case .off: return "Retrieve passages without writing an answer"
        }
    }
}

/// One chat exchange: the question, the passages, and the answer as it arrives.
public struct ChatTurn: Identifiable, Sendable {
    public let id = UUID()
    let question: String
    let corpus: String
    let engine: AnswerEngine

    /// Passages, once retrieval returns.
    var retrieval: RetrievalResult?
    /// The answer so far — replaced wholesale on each streamed update.
    var answer: String = ""
    /// Set when the answer completed.
    var metrics: SynthesisMetrics?
    /// Set when retrieval succeeded but no answer could be written.
    var synthesisFailure: SynthesisFailure?
    /// Set when retrieval itself failed; nothing else in the turn is valid.
    var errorMessage: String?

    var isStreaming: Bool {
        retrieval != nil && metrics == nil && synthesisFailure == nil && errorMessage == nil
            && engine != .off
    }
}

/// App-wide state: connection, search settings, chat history, and the live
/// corpus metadata fetched from the worker.
///
/// Shares the same corpus scopes as the Streamlit sidebar in `serve/chat.py`,
/// with the on-device answer engine added as a first-class provider. The
/// search defaults below are this app's own (k=25, min score 0.5, semantic
/// floor 0.20) and are not kept in lockstep with chat.py's sliders, which
/// have since drifted to their own values (k=15, min score 0.6, semantic
/// floor 0.3) — the two were never wired together, so "mirrors" was already
/// false before either changed again.
@MainActor
@Observable
public final class AppModel {

    // Connection (env-compatible with the Python client)

    /// Where the worker lives.
    ///
    /// Persisted, and it has to be: an address the reader types in Settings
    /// that reverts on the next launch is worse than no field at all, because
    /// it looks like it worked. Written through a computed property rather
    /// than a `didSet`, whose interaction with the `@Observable` macro's
    /// synthesised accessors is not something to leave to chance.
    ///
    /// `KGRAG_ENDPOINT` still wins when set, so a launch from the shell can
    /// override a stored value without clearing it.
    public var workerURLString: String {
        get { storedWorkerURL }
        set {
            storedWorkerURL = newValue
            AppModel.defaults.set(newValue, forKey: AppModel.workerURLKey)
        }
    }

    private var storedWorkerURL: String = AppModel.initialWorkerURL()

    static let workerURLKey = "workerURL"
    static var defaults: UserDefaults = .standard

    /// The worker address to start from.
    ///
    /// The default differs by platform on purpose. `localhost` is right on a
    /// Mac, where the worker is the same machine. On iOS it names *the
    /// phone*, so the app spends every query dialling a port nothing is
    /// listening on and reports "Could not connect to the server" about a
    /// machine the reader never chose. Better to start empty and say what is
    /// wanted in the placeholder.
    static func initialWorkerURL() -> String {
        if let fromEnv = ProcessInfo.processInfo.environment["KGRAG_ENDPOINT"], !fromEnv.isEmpty {
            return fromEnv
        }
        if let stored = defaults.string(forKey: workerURLKey), !stored.isEmpty {
            return stored
        }
        #if os(macOS)
            return "http://localhost:8000"
        #else
            return ""
        #endif
    }

    /// Placeholder for the Settings field — a real example, not a format
    /// description, since the mistake it exists to prevent is typing
    /// `localhost`.
    public static var workerURLPlaceholder: String {
        #if os(macOS)
            return "http://localhost:8000"
        #else
            return "http://your-mac.local:8000"
        #endif
    }

    var secret: String = ProcessInfo.processInfo.environment["HANDLER_SECRET"] ?? ""

    // Search settings (defaults mirror chat.py's sidebar)
    var corpus: String = "all"
    var resultCount: Double = 25
    var minScore: Double = 0.5
    var semanticFloor: Double = 0.20

    /// Which engine writes the answer. Defaults to on-device when the
    /// hardware allows, which is the point of the app.
    var engine: AnswerEngine = .off
    var backend: String = "omlx"
    var model: String = ""

    // Live worker metadata
    var stats: CorpusStats?
    var genres: [GenreCount] = []
    var models: [String] = []

    // Chat state
    var turns: [ChatTurn] = []
    var isQuerying = false
    var connectionError: String?
    private var activeQuery: Task<Void, Never>?

    /// The on-device backend, or nil on hardware/OS that cannot run it.
    let onDevice: (any SynthesisBackend)? = makeOnDeviceSynthesis()

    /// The Private Cloud Compute backend, or nil below iOS 27 / macOS 27.
    let privateCloud: (any SynthesisBackend)? = makePrivateCloudSynthesis()

    /// The installed corpus, once it has been opened. Nil means the app has
    /// not found packs — the ordinary state before a download, not a fault.
    private(set) var packs: CorpusPacks?
    /// Why an installed corpus would not open, when one is present but broken.
    private(set) var packsError: String?
    private(set) var isLoadingPacks = false

    /// True when a question can be answered with the network off: passages
    /// from the packs, answer from the built-in model.
    var isFullyLocal: Bool { packs != nil && engine == .onDevice }

    /// Kept so the observer registered below could be removed if `AppModel`
    /// were ever torn down mid-run — it never is, in practice, since one
    /// instance lives for the whole app launch, but `NotificationCenter`
    /// gives no way to express "this token is fine to leak" explicitly.
    private var askObserver: NSObjectProtocol?

    public init() {
        if onDeviceAvailability.isAvailable { engine = .onDevice }

        // See AskIntent.swift: Siri/Shortcuts have no other way to reach this
        // instance, so `AskKnowledgePressIntent.perform()` posts here instead.
        askObserver = NotificationCenter.default.addObserver(
            forName: .askKnowledgePress, object: nil, queue: .main
        ) { [weak self] notification in
            guard let question = notification.userInfo?["question"] as? String else { return }
            Task { @MainActor in self?.send(question) }
        }
    }

    /// Whether the built-in model can answer right now, and why not if it
    /// cannot — shown verbatim under the provider picker.
    var onDeviceAvailability: SynthesisAvailability {
        onDevice?.availability
            ?? .unavailable(reason: "this build targets a system older than iOS 26 / macOS 26")
    }

    /// Whether Private Cloud Compute can answer right now, and why not if it
    /// cannot — shown verbatim under the provider picker.
    var privateCloudAvailability: SynthesisAvailability {
        privateCloud?.availability
            ?? .unavailable(reason: "this build targets a system older than iOS 27 / macOS 27")
    }

    /// The day's usage caption for Private Cloud Compute, or nil when there
    /// is nothing worth telling the user.
    ///
    /// The `compiler(>=6.4)` half of the guard matches `PrivateCloudSynthesis`
    /// itself — see that file's header — so this still compiles against an
    /// Xcode 26 toolchain that lacks the type entirely; it just always
    /// returns nil there, same as `privateCloud` being nil in the first place.
    var privateCloudQuotaCaption: String? {
        #if canImport(FoundationModels) && compiler(>=6.4)
            if #available(iOS 27.0, macOS 27.0, *), let backend = privateCloud as? PrivateCloudSynthesis {
                return backend.quotaCaption
            }
        #endif
        return nil
    }

    /// Present Apple's own "raise my limit" sheet, when one is offered.
    func presentPrivateCloudLimitIncrease() {
        #if canImport(FoundationModels) && compiler(>=6.4)
            if #available(iOS 27.0, macOS 27.0, *), let backend = privateCloud as? PrivateCloudSynthesis {
                backend.presentLimitIncrease()
            }
        #endif
    }

    /// Remote synthesis providers, label → backend key (chat.py's
    /// `_SYNTH_PROVIDERS`).
    static let providers: [(label: String, key: String)] = [
        ("oMLX (local MLX)", "omlx"),
        ("Ollama (local)", "ollama"),
        ("OpenAI (cloud)", "openai"),
    ]

    /// Genre-tagged starter queries shown when the chat is empty.
    static let suggestedQueries: [(corpus: String, query: String)] = [
        ("sacred-texts", "pillar of salt"),
        ("world-literature", "circles of Hell"),
        ("diary", "descriptions of the Great Fire of London"),
        ("philosophy", "the categorical imperative and moral duty"),
        ("horror", "a monster assembled from dead body parts"),
    ]

    var corpusOptions: [String] {
        ["all", "gutenberg", "diary"] + genres.map(\.genre)
    }

    /// Sidebar header line, built from live stats (no hardcoded counts).
    var statsCaption: String {
        guard let stats else { return "\(AppVersion.display) · connecting…" }
        var parts = [
            AppVersion.display,
            "\(stats.books) books", "\(stats.genres) genres", "\(stats.diaries) diaries",
            "\(stats.nodes.formatted()) nodes",
        ]
        if let model = stats.embedModel {
            parts.append(model.components(separatedBy: "/").last ?? model)
        }
        return parts.joined(separator: " · ")
    }

    private var client: WorkerClient {
        let url = URL(string: workerURLString) ?? URL(string: "http://localhost:8000")!
        return WorkerClient(baseURL: url, secret: secret)
    }

    /// Whether a worker address has been entered at all.
    ///
    /// "Not configured" and "configured but unreachable" are different
    /// problems with different fixes, and collapsing them into one connection
    /// error is what made an unset iPhone report that it could not reach a
    /// server the reader never named.
    public var hasWorkerURL: Bool {
        !workerURLString.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Result of the last Settings ▸ Worker ▸ Test.
    public enum WorkerProbe: Equatable, Sendable {
        case idle
        case probing
        case reachable(String)
        case unreachable(String)
    }

    public private(set) var workerProbe: WorkerProbe = .idle

    /// Ask the worker for its stats and report what came back.
    ///
    /// Exists so the reader finds out whether an address works *when they
    /// type it*, rather than at the first query — the point in the flow where
    /// a failure is least diagnosable and most annoying.
    public func probeWorker() async {
        guard hasWorkerURL else {
            workerProbe = .unreachable("No address set.")
            return
        }
        workerProbe = .probing
        do {
            let found = try await client.stats()
            stats = found
            genres = (try? await client.listGenres()) ?? []
            connectionError = nil
            workerProbe = .reachable("\(found.books) books · \(found.genres) genres")
        } catch {
            workerProbe = .unreachable(error.localizedDescription)
        }
    }

    /// Retrieval engine for the next query — the packs when they are
    /// installed, the worker when they are not.
    private var retrievalEngine: any RetrievalEngine {
        if let packs { return LocalRetrieval(packs: packs) }
        return WorkerRetrieval(client: client)
    }

    /// Where the Browse tab reads books from, by the same rule.
    var browser: any CorpusBrowser {
        if let packs { return LocalBrowser(packs: packs) }
        return client
    }

    private var synthesisBackend: (any SynthesisBackend)? {
        switch engine {
        case .onDevice: return onDevice
        case .privateCloud: return privateCloud
        case .worker, .off: return nil
        }
    }

    /// Open the installed corpus, if there is one.
    ///
    /// Off the main actor: opening compiles the Core ML embedder, which takes
    /// seconds the first time and must not hold up the first frame.
    public func loadCorpusPacks() async {
        isLoadingPacks = true
        defer { isLoadingPacks = false }
        let opened = await Task.detached(priority: .userInitiated) { () -> (CorpusPacks?, String?) in
            var failure: String?
            let packs = CorpusPacks.installed { failure = $0 }
            return (packs, failure)
        }.value
        packs = opened.0
        packsError = opened.1
    }

    /// Fetch stats + genres for the sidebar; clears/sets `connectionError`.
    ///
    /// Prefers the installed corpus, so the header is populated in airplane
    /// mode and the worker is only consulted when there are no packs.
    public func refreshSidebar() async {
        if let packs, let catalog = packs.catalog {
            stats = catalog.stats(embedModel: packs.manifest.embedder.model)
            genres = catalog.genres()
            connectionError = nil
            return
        }
        guard hasWorkerURL else {
            connectionError = "No worker address set — Settings ▸ Worker."
            return
        }
        do {
            stats = try await client.stats()
            genres = try await client.listGenres()
            connectionError = nil
        } catch {
            connectionError = "Cannot reach worker at \(workerURLString) — is it running? (`make up`)"
        }
    }

    /// Fetch the synthesis model list for the selected backend.
    func refreshModels() async {
        let list = try? await client.listModels(backend: backend)
        models = list?.models ?? []
        if model.isEmpty || !models.contains(model) {
            model = list?.defaultModel ?? models.first ?? ""
        }
    }

    /// Load the built-in model's weights so the first answer starts promptly.
    public func prewarmOnDevice() {
        #if canImport(FoundationModels)
            if #available(iOS 26.0, macOS 26.0, *),
                let backend = onDevice as? OnDeviceSynthesis
            {
                backend.prewarm()
            }
        #endif
    }

    /// Run a query and stream the exchange into the chat.
    func send(_ question: String, corpusOverride: String? = nil) {
        let text = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isQuerying else { return }

        let scope = corpusOverride ?? corpus
        let turn = ChatTurn(question: text, corpus: scope, engine: engine)
        turns.append(turn)
        isQuerying = true

        // The worker still writes the answer in `.worker` mode, so that path
        // keeps its single round-trip; on-device and passages-only both go
        // through the orchestrator.
        activeQuery = Task { [self, engine] in
            defer { self.isQuerying = false }
            if engine == .worker {
                await self.sendViaWorker(turn.id, question: text, corpus: scope)
            } else {
                await self.stream(turn.id, question: text, corpus: scope)
            }
        }
    }

    /// Stop an answer mid-stream. The passages already shown stay.
    func cancel() {
        activeQuery?.cancel()
        activeQuery = nil
        isQuerying = false
    }

    // MARK: - Query paths

    private func stream(_ id: ChatTurn.ID, question: String, corpus: String) async {
        let orchestrator = QueryOrchestrator(
            retrieval: retrievalEngine, synthesis: synthesisBackend)
        let request = RetrievalRequest(
            query: question,
            corpus: corpus,
            k: Int(resultCount),
            minScore: minScore,
            semanticFloor: semanticFloor)

        do {
            for try await event in orchestrator.run(request) {
                guard let index = turns.firstIndex(where: { $0.id == id }) else { return }
                switch event {
                case .retrieved(let result):
                    turns[index].retrieval = result
                case .answer(let text):
                    turns[index].answer = text
                case .finished(let metrics):
                    turns[index].metrics = metrics
                case .synthesisUnavailable(let failure):
                    turns[index].synthesisFailure = failure
                }
            }
        } catch {
            guard let index = turns.firstIndex(where: { $0.id == id }) else { return }
            turns[index].errorMessage = (error as? WorkerError)?.errorDescription
                ?? error.localizedDescription
        }
    }

    /// The Phase 1 path: one worker call that retrieves and synthesizes.
    private func sendViaWorker(_ id: ChatTurn.ID, question: String, corpus: String) async {
        do {
            let result = try await client.query(
                question,
                corpus: corpus,
                k: Int(resultCount),
                minScore: minScore,
                semanticFloor: semanticFloor,
                synthesize: true,
                model: model,
                backend: backend)
            guard let index = turns.firstIndex(where: { $0.id == id }) else { return }
            turns[index].retrieval = RetrievalResult(
                hits: result.hits, kgsQueried: result.kgsQueried, searchMs: result.searchMs)
            turns[index].answer = result.synthesis ?? ""
            if let synthesis = result.synthesis, !synthesis.isEmpty {
                turns[index].metrics = SynthesisMetrics(
                    elapsedMs: result.synthesisMs ?? 0,
                    passagesUsed: result.hits.count,
                    passagesDropped: 0,
                    estimatedPromptTokens: 0,
                    model: result.model ?? backend)
            } else {
                turns[index].synthesisFailure = .backend(
                    result.synthesisError ?? "the worker returned no answer")
            }
        } catch {
            guard let index = turns.firstIndex(where: { $0.id == id }) else { return }
            turns[index].errorMessage = (error as? WorkerError)?.errorDescription
                ?? error.localizedDescription
        }
    }
}
