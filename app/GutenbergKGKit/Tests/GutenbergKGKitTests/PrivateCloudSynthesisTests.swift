// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The parts of PrivateCloudSynthesis that do not need a live session: mapping
// the framework's own enums onto the messages the chat shows. Everything else
// — the Profile-based session, actually streaming a response — needs a real
// Apple Intelligence session and is exercised by hand per app/RUNBOOK.md, the
// same boundary OnDeviceSynthesis has always drawn.
//
// swift-testing's `@Suite`/`@Test` macros reject `@available` on the
// declaration itself, so the guard is a runtime `#available` check inside
// each test body instead — `.enabled(if:)` keeps them from running at all
// below iOS/macOS 27, and the `#available` satisfies the compiler, which
// cannot see that the trait already guarantees it.

#if canImport(FoundationModels) && compiler(>=6.4)
    import Foundation
    import FoundationModels
    import Testing

    @testable import GutenbergKGKit

    /// Whether this toolchain's SDK actually carries iOS/macOS 27 — the tests
    /// below construct real framework types, so they need more than the file
    /// merely compiling against a 6.4+ compiler; they need to run on a system
    /// new enough for those types to work.
    private let isRunningOn27: Bool = {
        if #available(iOS 27.0, macOS 27.0, *) { return true }
        return false
    }()

    @Suite(.enabled(if: isRunningOn27))
    struct PrivateCloudSynthesisDescribeTests {

        @Test func deviceNotEligibleNamesTheDevice() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            #expect(
                PrivateCloudSynthesis.describe(.deviceNotEligible)
                    == "this device is not eligible for Private Cloud Compute")
        }

        @Test func systemNotReadyPointsAtSettings() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            #expect(
                PrivateCloudSynthesis.describe(.systemNotReady).contains("Apple Intelligence"))
        }
    }

    @Suite(.enabled(if: isRunningOn27))
    struct PrivateCloudSynthesisTranslateTests {

        @Test func quotaLimitReachedIsRecoverableElsewhere() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            let error = PrivateCloudComputeLanguageModel.Error.quotaLimitReached(
                .init(debugDescription: "daily limit reached"))
            let failure = PrivateCloudSynthesis.translate(error)

            guard case .unavailable = failure else {
                Issue.record("expected .unavailable, got \(failure)")
                return
            }
            #expect(failure.isRecoverableRemotely)
        }

        @Test func networkFailureIsABackendError() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            let error = PrivateCloudComputeLanguageModel.Error.networkFailure(
                .init(debugDescription: "offline"))
            let failure = PrivateCloudSynthesis.translate(error)

            guard case .backend = failure else {
                Issue.record("expected .backend, got \(failure)")
                return
            }
        }

        @Test func serviceUnavailableIsABackendError() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            let error = PrivateCloudComputeLanguageModel.Error.serviceUnavailable(
                .init(debugDescription: "PCC is down"))
            let failure = PrivateCloudSynthesis.translate(error)

            guard case .backend = failure else {
                Issue.record("expected .backend, got \(failure)")
                return
            }
        }
    }

    /// The iOS 27 unified error `streamResponse` actually throws in practice
    /// — found live, not from documentation: Private Cloud Compute's first
    /// real request threw one of these, unmatched by any of the typed catches
    /// above, and it fell through to `error.localizedDescription`, which for
    /// this type is often nil-backed and renders as an opaque
    /// "FoundationModels.LanguageModelError error -1". Every case carries a
    /// real `debugDescription`; `translateLanguageModelError` is what reads
    /// it instead, and `translateRemainingError` is what makes sure the
    /// generic catch-all tries this before giving up.
    @Suite(.enabled(if: isRunningOn27))
    struct LanguageModelErrorTranslationTests {

        @Test func contextSizeExceededIsContextOverflow() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            let error = LanguageModelError.contextSizeExceeded(
                .init(contextSize: 4_096, tokenCount: 5_000, debugDescription: "too long"))
            #expect(translateLanguageModelError(error) == .contextOverflow)
        }

        @Test func guardrailAndRefusalAreBothGuardrail() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            let guardrailError = LanguageModelError.guardrailViolation(
                .init(debugDescription: "declined"))
            let refusalError = LanguageModelError.refusal(
                .init(explanation: "no", debugDescription: "refused"))
            #expect(translateLanguageModelError(guardrailError) == .guardrail)
            #expect(translateLanguageModelError(refusalError) == .guardrail)
        }

        @Test func timeoutCarriesItsDebugDescriptionAsTheMessage() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            let error = LanguageModelError.timeout(.init(debugDescription: "the PCC round trip"))
            guard case .backend(let message) = translateLanguageModelError(error) else {
                Issue.record("expected .backend")
                return
            }
            #expect(message == "the PCC round trip")
        }

        @Test func rateLimitedIsRecoverableElsewhere() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            let error = LanguageModelError.rateLimited(
                .init(resetDate: nil, debugDescription: "slow down"))
            guard case .unavailable = translateLanguageModelError(error) else {
                Issue.record("expected .unavailable")
                return
            }
        }

        @Test func remainingErrorFallsBackToLanguageModelErrorFirst() {
            guard #available(iOS 27.0, macOS 27.0, *) else { return }
            let error: Error = LanguageModelError.timeout(.init(debugDescription: "network"))
            guard case .backend(let message) = translateRemainingError(error) else {
                Issue.record("expected .backend")
                return
            }
            #expect(message == "network")
        }
    }

    /// The failure PCC actually produced live: a raw `NSError` no typed catch
    /// matches, boilerplate on top, the truth two layers down. These pin the
    /// unwrapping so the "-1" mystery cannot silently come back.
    @Suite struct RootCauseUnwrappingTests {

        /// The exact three-level chain observed on 2026-09-02, verbatim.
        private var liveShape: NSError {
            let root = NSError(
                domain: "ModelManagerServices.ModelManagerError", code: 1046)
            let mid = NSError(
                domain: "FoundationModels.LanguageModelError", code: -1,
                userInfo: [NSUnderlyingErrorKey: root])
            return NSError(
                domain: "FoundationModels.LanguageModelSession.GenerationError", code: -1,
                userInfo: [NSUnderlyingErrorKey: mid])
        }

        @Test func walksToTheDeepestUnderlyingError() {
            guard #available(iOS 26.0, macOS 26.0, *) else { return }
            let root = rootCause(of: liveShape)
            #expect(root.domain == "ModelManagerServices.ModelManagerError")
            #expect(root.code == 1046)
        }

        @Test func modelManagerRefusalExplainsTheSigningRequirement() {
            guard #available(iOS 26.0, macOS 26.0, *) else { return }
            guard case .backend(let message) = translateRemainingError(liveShape) else {
                Issue.record("expected .backend")
                return
            }
            #expect(message.contains("com.apple.developer.private-cloud-compute"))
            #expect(!message.contains("error -1"))
        }

        @Test func unknownChainsNameTheirRootCause() {
            guard #available(iOS 26.0, macOS 26.0, *) else { return }
            let root = NSError(domain: "Some.Daemon.Error", code: 42)
            let top = NSError(
                domain: "FoundationModels.LanguageModelError", code: -1,
                userInfo: [NSUnderlyingErrorKey: root])
            guard case .backend(let message) = translateRemainingError(top) else {
                Issue.record("expected .backend")
                return
            }
            #expect(message.contains("Some.Daemon.Error 42"))
        }

        @Test func aChainlessErrorPassesThroughUnchanged() {
            guard #available(iOS 26.0, macOS 26.0, *) else { return }
            let flat = NSError(
                domain: "Flat", code: 7,
                userInfo: [NSLocalizedDescriptionKey: "just this"])
            guard case .backend(let message) = translateRemainingError(flat) else {
                Issue.record("expected .backend")
                return
            }
            #expect(message == "just this")
        }
    }
#endif
