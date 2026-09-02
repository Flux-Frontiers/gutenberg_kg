// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Retrieval against the RunPod-style worker — the Phase 1 path, unchanged in
// behavior, now behind the RetrievalEngine protocol.

import Foundation

/// Fetches passages from the GutenbergKG worker.
///
/// Synthesis is always requested as `false`: with a `SynthesisBackend` in the
/// app, asking the worker to also write an answer would pay for two.
public struct WorkerRetrieval: RetrievalEngine {
    public let label = "Worker"
    public let requiresNetwork = true

    private let client: WorkerClient

    public init(client: WorkerClient) {
        self.client = client
    }

    public func retrieve(_ request: RetrievalRequest) async throws -> RetrievalResult {
        let result = try await client.query(
            request.query,
            corpus: request.corpus,
            k: request.k,
            minScore: request.minScore,
            semanticFloor: request.semanticFloor,
            synthesize: false)
        return RetrievalResult(
            hits: result.hits,
            kgsQueried: result.kgsQueried,
            searchMs: result.searchMs)
    }
}
