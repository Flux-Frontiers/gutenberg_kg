// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0

import Foundation
import GutenbergKGKit
import Observation

/// One chat exchange: the user's question plus the worker's result (or error).
struct ChatTurn: Identifiable, Sendable {
    let id = UUID()
    let question: String
    let corpus: String
    var result: QueryResult?
    var errorMessage: String?
}

/// App-wide state: worker connection, sidebar settings, chat history, and
/// the live corpus metadata (stats/genres/models) fetched from the worker.
///
/// Mirrors the Streamlit sidebar contract in `serve/chat.py` — same defaults
/// (k=10, min score 0.5), same corpus scopes, same synthesis providers.
@MainActor
@Observable
final class AppModel {
    // Connection (env-compatible with the Python client)
    var workerURLString: String =
        ProcessInfo.processInfo.environment["KGRAG_ENDPOINT"] ?? "http://localhost:8000"
    var secret: String = ProcessInfo.processInfo.environment["HANDLER_SECRET"] ?? ""

    // Search settings (defaults mirror chat.py's sidebar)
    var corpus: String = "all"
    var resultCount: Double = 10
    var minScore: Double = 0.5
    var semanticFloor: Double = 0.0
    var synthesize: Bool = false
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

    /// Synthesis providers, label → backend key (chat.py's `_SYNTH_PROVIDERS`).
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
        guard let stats else { return "connecting…" }
        var parts = [
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

    /// Fetch stats + genres for the sidebar; clears/sets `connectionError`.
    func refreshSidebar() async {
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

    /// Run a corpus query and append the exchange to the chat.
    func send(_ question: String, corpusOverride: String? = nil) async {
        let text = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isQuerying else { return }
        let scope = corpusOverride ?? corpus
        var turn = ChatTurn(question: text, corpus: scope)
        turns.append(turn)
        isQuerying = true
        defer { isQuerying = false }
        do {
            turn.result = try await client.query(
                text,
                corpus: scope,
                k: Int(resultCount),
                minScore: minScore,
                semanticFloor: semanticFloor,
                synthesize: synthesize,
                model: model,
                backend: synthesize ? backend : "")
        } catch let error as WorkerError {
            turn.errorMessage = error.errorDescription
        } catch {
            turn.errorMessage = error.localizedDescription
        }
        if let index = turns.firstIndex(where: { $0.id == turn.id }) {
            turns[index] = turn
        }
    }
}
