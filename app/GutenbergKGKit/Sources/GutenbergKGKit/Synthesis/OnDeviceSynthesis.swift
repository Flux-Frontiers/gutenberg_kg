// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Apple Foundation Models backend — Phase 3 of analysis/APP_ARCHITECTURE.md.
//
// The answer is produced by the ~3B model built into the OS. Nothing leaves
// the device, no key is configured, and the whole path works in airplane mode.
// The cost is a ~4,096-token context window, which is why ContextBudgeter
// exists and why a fresh session is created per question.

import Foundation

#if canImport(FoundationModels)
    import FoundationModels

    /// Grounded synthesis on Apple's built-in language model.
    @available(iOS 26.0, macOS 26.0, *)
    public struct OnDeviceSynthesis: SynthesisBackend {

        public let label = "On-device"
        public let modelDescription = "Apple Foundation Models (on-device)"

        private let budgeter: ContextBudgeter
        private let temperature: Double

        /// :param budget: Context limits; defaults to the on-device window.
        /// :param temperature: Sampling temperature. 0.3 matches
        ///                     `TextSynthesizer.synthesize_rag`, which the
        ///                     worker uses for the same job.
        public init(budget: ContextBudgeter.Budget = .onDevice, temperature: Double = 0.3) {
            self.budgeter = ContextBudgeter(budget: budget)
            self.temperature = temperature
        }

        public var availability: SynthesisAvailability {
            switch SystemLanguageModel.default.availability {
            case .available:
                return .available
            case .unavailable(let reason):
                return .unavailable(reason: Self.describe(reason))
            @unknown default:
                return .unavailable(reason: "this device cannot run the built-in model")
            }
        }

        /// Load model weights ahead of the first question.
        ///
        /// Call this when the chat view appears: the first answer then starts
        /// streaming without the one-off load pause.
        public func prewarm() {
            guard availability.isAvailable else { return }
            LanguageModelSession { SynthesisPrompt.ragInstructions }.prewarm()
        }

        public func synthesize(
            question: String,
            passages: [Hit]
        ) -> AsyncThrowingStream<SynthesisEvent, Error> {
            AsyncThrowingStream { continuation in
                let task = Task {
                    do {
                        try await self.run(question: question, passages: passages, into: continuation)
                        continuation.finish()
                    } catch is CancellationError {
                        continuation.finish()
                    } catch let failure as SynthesisFailure {
                        continuation.finish(throwing: failure)
                    } catch let error as LanguageModelSession.GenerationError {
                        continuation.finish(throwing: translateGenerationError(error))
                    } catch {
                        continuation.finish(throwing: SynthesisFailure.backend(error.localizedDescription))
                    }
                }
                continuation.onTermination = { _ in task.cancel() }
            }
        }

        // MARK: - Implementation

        private func run(
            question: String,
            passages: [Hit],
            into continuation: AsyncThrowingStream<SynthesisEvent, Error>.Continuation
        ) async throws {
            guard case .available = availability else {
                throw SynthesisFailure.unavailable(
                    availability.reason ?? "the built-in model is not available")
            }

            let packed = budgeter.pack(passages, question: question)
            guard !packed.isEmpty else { throw SynthesisFailure.noPassages }

            // A session per question, deliberately. The framework charges the
            // whole transcript against the context window, so a long-lived
            // session would spend the 4K budget on history that the passages
            // need — and each turn is independently grounded anyway.
            let session = LanguageModelSession { SynthesisPrompt.ragInstructions }
            try await streamFoundationModelsAnswer(
                session: session, question: question, packed: packed, temperature: temperature,
                modelDescription: modelDescription, into: continuation)
        }

        static func describe(_ reason: SystemLanguageModel.Availability.UnavailableReason) -> String {
            switch reason {
            case .deviceNotEligible:
                return "this device does not support Apple Intelligence"
            case .appleIntelligenceNotEnabled:
                return "Apple Intelligence is turned off in Settings"
            case .modelNotReady:
                return "the model is still downloading"
            @unknown default:
                return "the built-in model is unavailable"
            }
        }
    }

    /// Stream a grounded answer from an already-configured session.
    ///
    /// Shared by every `SynthesisBackend` built on the Foundation Models
    /// framework. On-device and Private Cloud Compute differ only in which
    /// model backs the session — the packing already happened by the time this
    /// runs, and streaming, cancellation and metrics are identical either way,
    /// so that code lives here once rather than twice.
    ///
    /// :param session: A session already configured with the right model.
    /// :param question: The user's question, verbatim — used only for the
    ///     prompt text, not for packing (the caller already packed).
    /// :param packed: The passages the caller's budgeter fit to its window.
    /// :param temperature: Sampling temperature.
    /// :param modelDescription: Provenance string recorded on the turn.
    /// :param continuation: Where partial and final events are yielded.
    @available(iOS 26.0, macOS 26.0, *)
    func streamFoundationModelsAnswer(
        session: LanguageModelSession,
        question: String,
        packed: ContextBudgeter.Packed,
        temperature: Double,
        modelDescription: String,
        into continuation: AsyncThrowingStream<SynthesisEvent, Error>.Continuation
    ) async throws {
        let prompt = SynthesisPrompt.ragUserPrompt(question: question, passages: packed.passages)
        let options = GenerationOptions(temperature: temperature)

        let started = Date()
        var latest = ""

        for try await partial in session.streamResponse(to: prompt, options: options) {
            try Task.checkCancellation()
            // `content` is the whole answer so far, not a delta. (Early
            // iOS 26 betas yielded a bare String here; if this line fails to
            // compile against your SDK, drop `.content`.)
            latest = partial.content
            continuation.yield(.partial(latest))
        }

        let metrics = SynthesisMetrics(
            elapsedMs: Int(Date().timeIntervalSince(started) * 1000),
            passagesUsed: packed.passages.count,
            passagesDropped: packed.dropped,
            estimatedPromptTokens: packed.estimatedPromptTokens,
            model: modelDescription)
        continuation.yield(.completed(latest, metrics))
    }

    /// Map a `GenerationError` onto the two failures the chat handles
    /// specially. Shared by every Foundation-Models-backed synthesis backend.
    ///
    /// Guardrail refusals are expected against a corpus that contains the
    /// Inferno, the Old Testament and Frankenstein — the UI degrades to "read
    /// the passages yourself", which is the honest fallback and is the same
    /// shape as chat.py's `synthesis_error` state.
    @available(iOS 26.0, macOS 26.0, *)
    func translateGenerationError(_ error: LanguageModelSession.GenerationError) -> SynthesisFailure {
        switch error {
        case .guardrailViolation:
            return .guardrail
        case .exceededContextWindowSize:
            return .contextOverflow
        default:
            return .backend(error.localizedDescription)
        }
    }
#endif

/// Build the on-device backend when the OS and hardware allow it.
///
/// Returns nil on anything older than iOS 26 / macOS 26, or on an SDK without
/// the framework — the provider picker then offers only remote backends, the
/// same way chat.py falls back when no local model is reported.
public func makeOnDeviceSynthesis(
    budget: ContextBudgeter.Budget = .onDevice
) -> (any SynthesisBackend)? {
    #if canImport(FoundationModels)
        if #available(iOS 26.0, macOS 26.0, *) {
            return OnDeviceSynthesis(budget: budget)
        }
    #endif
    return nil
}
