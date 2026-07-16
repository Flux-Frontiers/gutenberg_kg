// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Swift port of kg_utils.worker.client.WorkerClient: a small client for the
// GutenbergKG RunPod-style worker (POST {base}/runsync with {"input": {...}},
// response unwrapped from {"output": {...}}).

import Foundation

/// Async client for the GutenbergKG worker's `/runsync` endpoint.
///
/// Mirrors the Python `WorkerClient` request/response contract exactly, so a
/// worker started with `make run` (or the RunPod deployment) serves both the
/// Streamlit chat and this client interchangeably.
public actor WorkerClient {
    private let baseURL: URL
    private let secret: String
    private let session: URLSession
    private let decoder = JSONDecoder()

    /// :param baseURL: Worker base URL, e.g. `http://localhost:8000`.
    /// :param secret: Shared secret (sent as `input.secret` when non-empty).
    /// :param session: Injectable session for testing.
    public init(baseURL: URL, secret: String = "", session: URLSession = .shared) {
        self.baseURL = baseURL
        self.secret = secret
        self.session = session
    }

    // MARK: - Public API

    /// Semantic-search the corpus, optionally with a synthesized answer.
    public func query(
        _ query: String,
        corpus: String = "all",
        k: Int = 8,
        minScore: Double = 0.0,
        semanticFloor: Double = 0.0,
        synthesize: Bool = false,
        model: String = "",
        backend: String = ""
    ) async throws -> QueryResult {
        var input: [String: Any] = [
            "query": query,
            "corpus": corpus,
            "k": k,
            "min_score": minScore,
            "semantic_floor": semanticFloor,
            "synthesize": synthesize,
        ]
        if !model.isEmpty { input["model"] = model }
        if !backend.isEmpty { input["backend"] = backend }
        return try await post(input)
    }

    /// Live corpus totals for the sidebar header.
    public func stats() async throws -> CorpusStats {
        try await post(["op": "stats"])
    }

    /// Every genre with its book count.
    public func listGenres() async throws -> [GenreCount] {
        let list: GenreList = try await post(["op": "list_genres"])
        return list.genres
    }

    /// Every book in a genre.
    public func listBooks(genre: String) async throws -> [Book] {
        let list: BookList = try await post(["op": "list_books", "genre": genre])
        return list.books
    }

    /// A book's chapter listing.
    public func chapters(genre: String, book: String) async throws -> [Chapter] {
        let list: ChapterList = try await post([
            "op": "get_chapters", "genre": genre, "book": book,
        ])
        return list.chapters
    }

    /// One chapter's reconstructed text.
    public func chapter(genre: String, book: String, sectionId: String) async throws -> ChapterContent {
        try await post([
            "op": "get_chapter", "genre": genre, "book": book, "section_id": sectionId,
        ])
    }

    /// Available synthesis models for a backend.
    public func listModels(backend: String = "") async throws -> ModelList {
        var input: [String: Any] = ["op": "models"]
        if !backend.isEmpty { input["backend"] = backend }
        return try await post(input)
    }

    /// Rewrite corpus prose into an image-generation prompt.
    /// Falls back to the original text if the worker reports a rewrite error,
    /// matching the Python client's behavior.
    public func rewrite(_ text: String, backend: String = "", model: String = "") async throws -> String {
        var input: [String: Any] = ["op": "rewrite", "text": text]
        if !backend.isEmpty { input["backend"] = backend }
        if !model.isEmpty { input["model"] = model }
        let result: RewriteResult = try await post(input)
        return result.prompt ?? text
    }

    /// Generate an illustration from a prompt via the worker's image backend.
    public func imagine(
        prompt: String,
        imageBackend: String = "",
        size: String? = nil,
        steps: Int? = nil
    ) async throws -> GeneratedImage {
        var input: [String: Any] = ["op": "imagine", "prompt": prompt]
        if !imageBackend.isEmpty { input["image_backend"] = imageBackend }
        if let size { input["size"] = size }
        if let steps { input["steps"] = steps }
        return try await post(input)
    }

    // MARK: - Transport

    private func post<T: Decodable>(_ input: [String: Any]) async throws -> T {
        var enriched = input
        if !secret.isEmpty { enriched["secret"] = secret }

        var request = URLRequest(url: baseURL.appendingPathComponent("runsync"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["input": enriched])

        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw WorkerError.httpStatus(http.statusCode)
        }
        return try Self.decodePayload(data, decoder: decoder)
    }

    /// Unwrap the worker envelope and decode the output payload.
    ///
    /// Accepts either `{"output": {...}}` (RunPod envelope) or a bare payload
    /// dict; surfaces `{"error": ...}` at either level as
    /// ``WorkerError/application(_:)`` — the same rules as the Python
    /// `decode_worker_response`.
    static func decodePayload<T: Decodable>(_ data: Data, decoder: JSONDecoder) throws -> T {
        let top = try JSONSerialization.jsonObject(with: data)
        guard let topDict = top as? [String: Any] else {
            throw WorkerError.unexpectedPayload("top-level JSON is not an object")
        }
        if let message = topDict["error"] as? String {
            throw WorkerError.application(message)
        }
        let output = topDict["output"] ?? topDict
        guard let outDict = output as? [String: Any] else {
            throw WorkerError.unexpectedPayload("output is not an object")
        }
        if let message = outDict["error"] as? String {
            throw WorkerError.application(message)
        }
        let outData = try JSONSerialization.data(withJSONObject: outDict)
        return try decoder.decode(T.self, from: outData)
    }
}
