// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The on-device context window is the tightest constraint in the app, so the
// packer is the piece worth testing hardest: it decides what evidence the
// model is allowed to see.

import Foundation
import Testing

@testable import GutenbergKGKit

private func hit(
    id: String,
    content: String?,
    summary: String? = nil,
    score: Double = 0.8,
    genre: String? = "philosophy",
    author: String? = "Immanuel Kant",
    title: String? = "Groundwork of the Metaphysics of Morals",
    kgKind: String = "KGKind.doc",
    name: String = "chunk"
) -> Hit {
    // Fixture JSON in the worker's shape, like ModelDecodingTests — the same
    // contract, so these tests break if the schema moves.
    func field(_ key: String, _ value: String?) -> String {
        guard let value else { return "\"\(key)\": null" }
        let escaped = value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: "\\n")
        return "\"\(key)\": \"\(escaped)\""
    }
    let json = """
        {"kg_name": "gutenberg-all", \(field("kg_kind", kgKind)), \(field("node_id", id)),
         \(field("name", name)), "kind": "chunk", "score": \(score),
         \(field("summary", summary)), "source_path": null, \(field("content", content)),
         "timestamp": null, \(field("genre", genre)), \(field("title", title)),
         \(field("author", author))}
        """
    return try! JSONDecoder().decode(Hit.self, from: Data(json.utf8))
}

private let lorem = String(repeating: "conformity to universal law ", count: 200)

@Suite struct ContextBudgeterTests {

    @Test func packsBestFirstAndStopsAtMaxPassages() {
        let hits = (1...12).map { hit(id: "n\($0)", content: lorem, score: 1.0 - Double($0) / 20) }
        let packed = ContextBudgeter(budget: .onDevice).pack(hits, question: "duty?")

        #expect(packed.passages.count <= ContextBudgeter.Budget.onDevice.maxPassages)
        #expect(packed.dropped == hits.count - packed.passages.count)
        // Order is retrieval order — the packer truncates, it never reranks.
        #expect(packed.passages.map(\.id) == (1...packed.passages.count).map { "n\($0)" })
    }

    @Test func staysInsideTheAllowance() {
        let hits = (1...12).map { hit(id: "n\($0)", content: lorem) }
        let budget = ContextBudgeter.Budget.onDevice
        let packed = ContextBudgeter(budget: budget).pack(hits, question: "duty?")

        #expect(packed.estimatedPromptTokens <= budget.contextWindow - budget.reservedForResponse)
    }

    @Test func skipsHitsWithNoText() {
        let hits = [
            hit(id: "empty", content: nil),
            hit(id: "blank", content: "   \n  "),
            hit(id: "real", content: lorem),
        ]
        let packed = ContextBudgeter().pack(hits, question: "duty?")

        #expect(packed.passages.map(\.id) == ["real"])
        // A hit with nothing to quote was never a candidate, so it is not
        // reported as dropped for want of budget.
        #expect(packed.dropped == 0)
    }

    @Test func fallsBackToSummaryWhenContentIsAbsent() {
        let packed = ContextBudgeter().pack(
            [hit(id: "s", content: nil, summary: lorem)], question: "duty?")

        #expect(packed.passages.count == 1)
        #expect(packed.passages[0].text.hasPrefix("conformity to universal law"))
    }

    @Test func keepsAShortPassageThatWasNeverTruncated() {
        // Below minCharactersPerPassage, but that is all the passage has —
        // dropping it would silently discard a real hit.
        let short = "But his wife looked back from behind him, and she became a pillar of salt."
        let packed = ContextBudgeter().pack([hit(id: "gen", content: short)], question: "salt?")

        #expect(packed.passages.count == 1)
        #expect(packed.passages[0].text == short)
    }

    @Test func trimsAtAWordBoundaryAndMarksTheCut() {
        let trimmed = ContextBudgeter.trim("the quick brown fox jumps", to: 12)

        #expect(trimmed == "the quick…")
        #expect(!trimmed.contains("brow"))
    }

    @Test func trimReturnsShortTextUnchanged() {
        #expect(ContextBudgeter.trim("  short  ", to: 100) == "short")
    }

    @Test func headerMatchesTheWorkerContextBlock() {
        let h = hit(id: "n", content: lorem)

        #expect(ContextBudgeter.header(for: h)
            == "philosophy · Immanuel Kant · Groundwork of the Metaphysics of Morals")
    }

    @Test func headerFallsBackToKgKindAndName() {
        // synthesize_rag: genre → kg_kind, title → name.
        let h = hit(
            id: "n", content: lorem, genre: nil, author: nil, title: nil,
            kgKind: "KGKind.diary", name: "September 2nd 1666")

        #expect(ContextBudgeter.header(for: h) == "KGKind.diary · September 2nd 1666")
    }

    @Test func workerBudgetMatchesSynthMaxK() {
        // SYNTH_MAX_K = 12 in serve/handler.py.
        #expect(ContextBudgeter.Budget.worker.maxPassages == 12)
    }

    @Test func privateCloudBudgetMatchesItsOwnContextWindow() {
        // PrivateCloudComputeLanguageModel().contextSize is 32,768 — not the
        // worker's number by coincidence, but its own, so this is asserted
        // independently rather than as "== .worker".
        #expect(ContextBudgeter.Budget.privateCloudCompute.contextWindow == 32_768)
        #expect(ContextBudgeter.Budget.privateCloudCompute.maxPassages == 12)
    }
}

@Suite struct SynthesisPromptTests {

    @Test func userPromptShapeMatchesSynthesizeRag() {
        let passages = [
            ContextBudgeter.Passage(id: "a", header: "sacred-texts · Genesis", text: "…salt."),
            ContextBudgeter.Passage(id: "b", header: "diary · Pepys", text: "…fire."),
        ]
        let prompt = SynthesisPrompt.ragUserPrompt(question: "what burned?", passages: passages)

        #expect(prompt == """
            Source passages:
            [sacred-texts · Genesis]
            …salt.

            [diary · Pepys]
            …fire.

            Question: what burned?
            """)
    }

    @Test func instructionsForbidPriorKnowledge() {
        // The one line that makes an answer citable rather than plausible.
        #expect(SynthesisPrompt.ragInstructions.contains("ONLY the provided source passages"))
        #expect(SynthesisPrompt.ragInstructions.contains("Do NOT use any prior knowledge"))
    }
}

@Suite struct SynthesisFailureTests {

    @Test func guardrailRefusalsCanBeRetriedRemotely() {
        #expect(SynthesisFailure.guardrail.isRecoverableRemotely)
        #expect(SynthesisFailure.contextOverflow.isRecoverableRemotely)
        // Nothing to answer from is not the backend's fault.
        #expect(!SynthesisFailure.noPassages.isRecoverableRemotely)
    }
}
