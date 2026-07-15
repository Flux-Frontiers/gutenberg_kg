// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0

import Foundation

/// Errors surfaced by ``WorkerClient``.
public enum WorkerError: Error, LocalizedError, Equatable {
    /// The worker returned an application-level `{"error": ...}` payload
    /// (unknown corpus, missing book, synthesis backend down, …).
    case application(String)
    /// The HTTP layer failed (non-2xx status).
    case httpStatus(Int)
    /// The response body was not the expected JSON envelope.
    case unexpectedPayload(String)

    public var errorDescription: String? {
        switch self {
        case .application(let message): return message
        case .httpStatus(let code): return "worker returned HTTP \(code)"
        case .unexpectedPayload(let detail): return "unexpected worker payload: \(detail)"
        }
    }
}
