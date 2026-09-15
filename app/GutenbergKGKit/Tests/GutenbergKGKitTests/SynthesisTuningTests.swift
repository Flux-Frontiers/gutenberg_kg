// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.

import Foundation
import Testing

@testable import GutenbergKGKit

@Suite struct SynthesisTuningTests {

    @Test func defaultsAreTheShippedValues() {
        let t = SynthesisTuning.default
        #expect(t.temperature == 0.2)
        #expect(!t.greedy)
        #expect(t.maxPassagesPerSource == nil)
        #expect(t.instructions == .guide)
        #expect(!t.permissiveGuardrails)
        #expect(t.instructionText == SynthesisPrompt.guideInstructions)
    }

    @Test func workerParitySelectsTheVerbatimServerPrompt() {
        let t = SynthesisTuning(instructions: .workerParity)
        #expect(t.instructionText == SynthesisPrompt.ragInstructions)
    }

    @Test func perSourceOverrideAppliesOnlyWhenSet() {
        let untouched = SynthesisTuning().apply(to: .privateCloudCompute)
        #expect(untouched == .privateCloudCompute)

        let widened = SynthesisTuning(maxPassagesPerSource: 6).apply(to: .onDevice)
        #expect(widened.maxPassagesPerSource == 6)
        #expect(widened.maxPassages == ContextBudgeter.Budget.onDevice.maxPassages)

        // Zero would pack nothing; clamp rather than answer from silence.
        #expect(SynthesisTuning(maxPassagesPerSource: 0).apply(to: .onDevice).maxPassagesPerSource == 1)
    }

    @Test func roundTripsThroughJSON() throws {
        let t = SynthesisTuning(
            temperature: 0.7, greedy: true, maxPassagesPerSource: 3,
            instructions: .workerParity, permissiveGuardrails: true)
        let data = try JSONEncoder().encode(t)
        let back = try JSONDecoder().decode(SynthesisTuning.self, from: data)
        #expect(back == t)
    }

    @Test func decodesAConfigSavedBeforeAFieldExisted() throws {
        // A stored tuning must survive the struct growing a field, or every
        // reader's settings reset the release after one is added.
        let old = Data(#"{"temperature":0.5,"greedy":false,"instructions":"guide","permissiveGuardrails":false}"#.utf8)
        let t = try JSONDecoder().decode(SynthesisTuning.self, from: old)
        #expect(t.temperature == 0.5)
        #expect(t.maxPassagesPerSource == nil)
    }
}
