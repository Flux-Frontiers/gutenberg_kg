// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Retrieval → budget → synthesis, as one stream of events the chat renders.
//
// This is the whole query path in one place: it is what `serve/handler.py`
// does per request, minus the HTTP.

import Foundation

/// What the chat learns as an answer is assembled.
public enum QueryEvent: Sendable {
    /// Retrieval finished; the hit cards can be drawn before any answer text.
    case retrieved(RetrievalResult)
    /// The answer so far (cumulative — replace, do not append).
    case answer(String)
    /// The answer is complete.
    case finished(SynthesisMetrics)
    /// Retrieval succeeded but no answer was produced; the passages stand
    /// alone. Carries the message to show above them.
    case synthesisUnavailable(SynthesisFailure)
}

/// Runs one question end to end.
public struct QueryOrchestrator: Sendable {
    private let retrieval: any RetrievalEngine
    private let synthesis: (any SynthesisBackend)?

    /// :param retrieval: Where passages come from.
    /// :param synthesis: Answer engine, or nil to return passages only —
    ///                   which is exactly chat.py's "Synthesize" toggle off.
    public init(retrieval: any RetrievalEngine, synthesis: (any SynthesisBackend)? = nil) {
        self.retrieval = retrieval
        self.synthesis = synthesis
    }

    /// Stream retrieval then synthesis for one question.
    ///
    /// Retrieval errors are thrown; synthesis errors are *not* — a failed
    /// answer still leaves the passages worth reading, so they arrive as
    /// ``QueryEvent/synthesisUnavailable(_:)`` and the stream finishes
    /// normally.
    public func run(_ request: RetrievalRequest) -> AsyncThrowingStream<QueryEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let result = try await self.retrieval.retrieve(request)
                    continuation.yield(.retrieved(result))

                    guard let synthesis = self.synthesis else {
                        continuation.finish()
                        return
                    }
                    guard !result.hits.isEmpty else {
                        continuation.yield(.synthesisUnavailable(.noPassages))
                        continuation.finish()
                        return
                    }

                    do {
                        let stream = synthesis.synthesize(
                            question: request.query, passages: result.hits)
                        for try await event in stream {
                            switch event {
                            case .partial(let text):
                                continuation.yield(.answer(text))
                            case .completed(let text, let metrics):
                                continuation.yield(.answer(text))
                                continuation.yield(.finished(metrics))
                            }
                        }
                    } catch let failure as SynthesisFailure {
                        continuation.yield(.synthesisUnavailable(failure))
                    } catch {
                        continuation.yield(
                            .synthesisUnavailable(.backend(error.localizedDescription)))
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}
