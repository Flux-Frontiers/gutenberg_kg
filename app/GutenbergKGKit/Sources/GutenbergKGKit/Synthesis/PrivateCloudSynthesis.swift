// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Apple Foundation Models backend, routed to Private Cloud Compute (PCC)
// instead of the on-device model — the server tier WWDC26 added to the same
// framework `OnDeviceSynthesis` already uses.
//
// This is not "on-device" in the sense the rest of the app promises: it needs
// a network connection and is metered against the user's iCloud account, so
// it is offered as its own engine rather than folded silently into on-device.
// What it buys in return is a 32,768-token window — eight times the on-device
// model's — so ContextBudgeter.Budget.privateCloudCompute can carry as many
// passages as the worker's server-class synthesis does.

import Foundation

// `PrivateCloudComputeLanguageModel` is new in the iOS 27 / macOS 27 SDK, not
// merely gated by `@available` within an SDK that already had it — an Xcode
// 26 toolchain's FoundationModels module does not declare the type at all, so
// `#if canImport(FoundationModels)` alone is not enough to guard this file:
// that stays true on Xcode 26 too, and the build would fail outright rather
// than degrade. Swift 6.4 ships exclusively with Xcode 27's SDKs (confirmed
// against Apple's own Xcode 27 release notes), so gating on the compiler
// version is a correct, checkable proxy for "this SDK has the type" — unlike
// `#available`, which only affects what runs, `#if compiler(...)` affects
// what compiles. `app/RUNBOOK.md` section 0 still lists Xcode 26 as the
// baseline prerequisite; this keeps that baseline building, with Private
// Cloud Compute simply absent until the toolchain catches up.
#if canImport(FoundationModels) && compiler(>=6.4)
    import FoundationModels

    /// Grounded synthesis on Apple's server model, reached through the same
    /// `LanguageModelSession` the on-device backend uses.
    ///
    /// iOS 27 / macOS 27 only — a full major version above the on-device
    /// floor, because `PrivateCloudComputeLanguageModel` did not exist before
    /// it. Older systems simply never see this engine offered; see
    /// `makePrivateCloudSynthesis`.
    @available(iOS 27.0, macOS 27.0, *)
    public struct PrivateCloudSynthesis: SynthesisBackend {

        public let label = "Private Cloud"
        public let modelDescription = "Apple Foundation Models (Private Cloud Compute)"

        private let budgeter: ContextBudgeter
        private let temperature: Double
        private let model: PrivateCloudComputeLanguageModel

        /// :param budget: Context limits; defaults to PCC's 32K window.
        /// :param temperature: Sampling temperature — same default as
        ///                     on-device, for the same reason.
        public init(
            budget: ContextBudgeter.Budget = .privateCloudCompute, temperature: Double = 0.3
        ) {
            self.budgeter = ContextBudgeter(budget: budget)
            self.temperature = temperature
            self.model = PrivateCloudComputeLanguageModel()
        }

        public var availability: SynthesisAvailability {
            switch model.availability {
            case .available:
                return .available
            case .unavailable(let reason):
                return .unavailable(reason: Self.describe(reason))
            @unknown default:
                return .unavailable(reason: "Private Cloud Compute is unavailable")
            }
        }

        /// A one-line status for the day's usage, or nil when there is
        /// nothing worth telling the user — Apple's own guidance is to warn
        /// as the limit approaches and say plainly once it is reached, not to
        /// show a running count that means nothing to a reader.
        public var quotaCaption: String? {
            let usage = model.quotaUsage
            if usage.isLimitReached {
                if let resetDate = usage.resetDate {
                    let when = resetDate.formatted(date: .abbreviated, time: .shortened)
                    return "Today's Private Cloud Compute limit is reached. Resets \(when)."
                }
                return "Today's Private Cloud Compute limit is reached."
            }
            if case .belowLimit(let info) = usage.status, info.isApproachingLimit {
                return "Nearing today's Private Cloud Compute limit."
            }
            return nil
        }

        /// Present Apple's own upgrade sheet, when the framework offers one.
        ///
        /// :returns: True when a suggestion existed and was shown.
        @discardableResult
        public func presentLimitIncrease() -> Bool {
            guard let suggestion = model.quotaUsage.limitIncreaseSuggestion else { return false }
            suggestion.show()
            return true
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
                    } catch let error as PrivateCloudComputeLanguageModel.Error {
                        continuation.finish(throwing: Self.translate(error))
                    } catch {
                        continuation.finish(throwing: translateRemainingError(error))
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
                    availability.reason ?? "Private Cloud Compute is not available")
            }

            let packed = budgeter.pack(passages, question: question)
            guard !packed.isEmpty else { throw SynthesisFailure.noPassages }

            // Same one-session-per-question rule as on-device, and for the
            // same reason: the transcript is charged against the context
            // window, so a long-lived session would spend PCC's larger but
            // still finite 32K budget on history instead of passages.
            let profile = LanguageModelSession.Profile { Instructions(SynthesisPrompt.ragInstructions) }
                .model(model)
            let session = LanguageModelSession(profile: profile)
            try await streamFoundationModelsAnswer(
                session: session, question: question, packed: packed, temperature: temperature,
                modelDescription: modelDescription, into: continuation)
        }

        /// Map a PCC-specific failure onto the shared `SynthesisFailure` shape.
        ///
        /// A quota hit is not a bug and not the on-device unavailable case
        /// either, but the chat only distinguishes "try another engine" from
        /// "nothing will help" — `.unavailable` says the former, correctly.
        ///
        /// Reads each case's own `debugDescription`, not `errorDescription`:
        /// found live, the first version of this read `error.errorDescription
        /// ?? "..."`, and `errorDescription` (the `LocalizedError` half)
        /// returned nil here, silently falling to the generic fallback string
        /// and hiding the real reason. `debugDescription` is a plain
        /// non-optional `String` on every one of these structs — it is what
        /// actually carries the framework's own explanation.
        static func translate(_ error: PrivateCloudComputeLanguageModel.Error) -> SynthesisFailure {
            switch error {
            case .quotaLimitReached(let info):
                return .unavailable(info.debugDescription)
            case .networkFailure(let info):
                return .backend(info.debugDescription)
            case .serviceUnavailable(let info):
                return .backend(info.debugDescription)
            @unknown default:
                return .backend(error.errorDescription ?? "Private Cloud Compute request failed")
            }
        }

        static func describe(
            _ reason: PrivateCloudComputeLanguageModel.Availability.UnavailableReason
        ) -> String {
            switch reason {
            case .deviceNotEligible:
                return "this device is not eligible for Private Cloud Compute"
            case .systemNotReady:
                return "Private Cloud Compute is not ready — check Apple Intelligence in Settings"
            @unknown default:
                return "Private Cloud Compute is unavailable"
            }
        }
    }
#endif

/// Build the Private Cloud Compute backend when the OS allows it.
///
/// Returns nil on anything older than iOS 27 / macOS 27, or on an SDK without
/// the framework — the provider picker then simply does not offer this
/// engine, the same way it already omits on-device below iOS 26.
public func makePrivateCloudSynthesis(
    budget: ContextBudgeter.Budget = .privateCloudCompute
) -> (any SynthesisBackend)? {
    #if canImport(FoundationModels) && compiler(>=6.4)
        if #available(iOS 27.0, macOS 27.0, *) {
            return PrivateCloudSynthesis(budget: budget)
        }
    #endif
    return nil
}
