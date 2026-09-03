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
#endif
