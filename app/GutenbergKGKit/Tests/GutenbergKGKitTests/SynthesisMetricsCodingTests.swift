// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// `packedIds` was added to a struct that is persisted in every saved
// conversation. The one thing that must hold is that chats written before it
// existed still open.

import Foundation
import Testing

@testable import GutenbergKGKit

@Suite("SynthesisMetrics coding")
struct SynthesisMetricsCodingTests {

    @Test("a conversation saved before packedIds existed still decodes")
    func legacyMetricsDecode() throws {
        let legacy = """
            {"elapsedMs": 900, "passagesUsed": 5, "passagesDropped": 20,
             "estimatedPromptTokens": 3100, "model": "Apple Foundation Models (on-device)"}
            """
        let metrics = try JSONDecoder().decode(SynthesisMetrics.self, from: Data(legacy.utf8))
        #expect(metrics.passagesUsed == 5)
        #expect(metrics.packedIds.isEmpty)
    }

    @Test("packedIds round-trip in prompt order")
    func packedIdsRoundTrip() throws {
        let metrics = SynthesisMetrics(
            elapsedMs: 1, passagesUsed: 3, passagesDropped: 22, estimatedPromptTokens: 500,
            model: "m", packedIds: ["gutenberg:c:1", "gutenberg:c:9", "diary:p:2"])
        let data = try JSONEncoder().encode(metrics)
        let back = try JSONDecoder().decode(SynthesisMetrics.self, from: data)
        #expect(back == metrics)
        #expect(back.packedIds == ["gutenberg:c:1", "gutenberg:c:9", "diary:p:2"])
    }
}
