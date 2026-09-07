// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The retrieval seam. `LocalRetrieval` (Core ML bge-small + a mapped vector
// sidecar + FTS5 + RRF over the installed packs) and `WorkerRetrieval` both
// answer to it, so the chat never learns which one found a passage.

import Foundation

/// What to search and how much of it to return.
///
/// Field-for-field the worker's request contract, so the local engine and the
/// remote one cannot drift apart on semantics.
public struct RetrievalRequest: Sendable, Equatable {
    /// The user's question, verbatim.
    public var query: String
    /// `all`, `gutenberg`, `diary`, or a genre slug.
    public var corpus: String
    /// Passages to return for the hit cards. Synthesis may use fewer.
    public var k: Int
    /// Drop fused hits below this score.
    public var minScore: Double
    /// Per-KG dense-score floor, applied before fusion.
    public var semanticFloor: Double

    public init(
        query: String,
        corpus: String = "all",
        k: Int = 25,
        minScore: Double = 0.5,
        semanticFloor: Double = 0.20
    ) {
        self.query = query
        self.corpus = corpus
        self.k = k
        self.minScore = minScore
        self.semanticFloor = semanticFloor
    }
}

/// Passages plus how long finding them took.
public struct RetrievalResult: Sendable {
    public let hits: [Hit]
    public let kgsQueried: Int
    public let searchMs: Int?

    public init(hits: [Hit], kgsQueried: Int, searchMs: Int?) {
        self.hits = hits
        self.kgsQueried = kgsQueried
        self.searchMs = searchMs
    }
}

/// A source of passages for a question.
public protocol RetrievalEngine: Sendable {
    /// Short label for the UI, e.g. "On-device corpus".
    var label: String { get }
    /// True when this engine needs the network to answer.
    var requiresNetwork: Bool { get }

    func retrieve(_ request: RetrievalRequest) async throws -> RetrievalResult
}
