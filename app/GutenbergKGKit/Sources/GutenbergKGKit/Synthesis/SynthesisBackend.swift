// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The synthesis seam. `OnDeviceSynthesis` (Apple Foundation Models) and any
// remote OpenAI-compatible backend both answer to this protocol, so the chat
// UI never learns which one produced a turn.
//
// Reference implementation: kg_utils.synthesis._text.TextSynthesizer
// .synthesize_rag — see SynthesisPrompt for the ported prompt contract.

import Foundation

/// One progressive update from a synthesis run.
///
/// `partial` carries the **cumulative** answer text, not a delta: the
/// Foundation Models framework streams snapshots of the whole response so far,
/// and re-deriving deltas here would only invite off-by-one bugs in the view.
public enum SynthesisEvent: Sendable {
    /// The answer as generated so far. Replace the rendered text with this.
    case partial(String)
    /// The final answer plus what it cost.
    case completed(String, SynthesisMetrics)
}

/// What a completed synthesis cost, for the turn's stats caption.
public struct SynthesisMetrics: Sendable, Equatable {
    /// Wall-clock milliseconds from first token request to completion.
    public let elapsedMs: Int
    /// Passages that actually reached the model after budgeting.
    public let passagesUsed: Int
    /// Passages retrieval returned that the context budget could not fit.
    public let passagesDropped: Int
    /// Estimated prompt size in tokens (see `ContextBudgeter.estimateTokens`).
    public let estimatedPromptTokens: Int
    /// Human-readable provenance, e.g. "Apple Foundation Models (on-device)".
    public let model: String

    public init(
        elapsedMs: Int,
        passagesUsed: Int,
        passagesDropped: Int,
        estimatedPromptTokens: Int,
        model: String
    ) {
        self.elapsedMs = elapsedMs
        self.passagesUsed = passagesUsed
        self.passagesDropped = passagesDropped
        self.estimatedPromptTokens = estimatedPromptTokens
        self.model = model
    }
}

/// Why a synthesis run produced no answer.
///
/// Every case maps to a message the chat can show without blaming the user;
/// `isRecoverableRemotely` marks the ones where "retry via the worker" is a
/// sensible next action, mirroring chat.py's `synthesis_error` path.
public enum SynthesisFailure: Error, Sendable, Equatable {
    /// The backend cannot run at all (Apple Intelligence off, model absent…).
    case unavailable(String)
    /// Retrieval returned nothing with usable content.
    case noPassages
    /// The model's safety guardrails refused the passages or the question.
    case guardrail
    /// The packed prompt still exceeded the model's context window.
    case contextOverflow
    /// Anything else the framework reported.
    case backend(String)

    /// True when routing the same request to a remote provider could succeed.
    public var isRecoverableRemotely: Bool {
        switch self {
        case .unavailable, .guardrail, .contextOverflow, .backend: return true
        case .noPassages: return false
        }
    }

    /// Message shown in the assistant turn, in the voice chat.py already uses.
    public var displayMessage: String {
        switch self {
        case .unavailable(let reason):
            return "On-device answers are unavailable — \(reason). The passages below are still yours to read."
        case .noPassages:
            return "No passage carried enough text to answer from. Try different wording or a lower minimum score."
        case .guardrail:
            return "The on-device model declined to answer from these passages. This happens with some classical texts; the passages below are unfiltered."
        case .contextOverflow:
            return "The passages did not fit the on-device context window. Lower the passage count and ask again."
        case .backend(let message):
            return "Answer generation failed — \(message)."
        }
    }
}

/// A source of grounded answers over retrieved passages.
public protocol SynthesisBackend: Sendable {
    /// Short label for the provider picker, e.g. "On-device".
    var label: String { get }
    /// Provenance string recorded on each turn.
    var modelDescription: String { get }
    /// Whether this backend can serve a request right now.
    var availability: SynthesisAvailability { get }

    /// Stream a grounded answer to `question` from `passages`.
    ///
    /// The stream finishes with a single ``SynthesisEvent/completed(_:_:)``
    /// event, or throws ``SynthesisFailure``.
    ///
    /// :param question: The user's question, verbatim.
    /// :param passages: Retrieval hits, best-first. The backend is responsible
    ///                  for fitting them to its own context window.
    func synthesize(
        question: String,
        passages: [Hit]
    ) -> AsyncThrowingStream<SynthesisEvent, Error>
}

/// Whether a backend can run, and why not when it cannot.
public enum SynthesisAvailability: Sendable, Equatable {
    case available
    case unavailable(reason: String)

    public var isAvailable: Bool {
        if case .available = self { return true }
        return false
    }

    /// The reason string, or nil when available.
    public var reason: String? {
        if case .unavailable(let reason) = self { return reason }
        return nil
    }
}
