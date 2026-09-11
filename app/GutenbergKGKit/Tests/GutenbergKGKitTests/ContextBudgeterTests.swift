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

    @Test func thePerSourceCapDoesNotBackfillFromBelowTheWindow() {
        // Rank order as the fixed cross-pack merge produces it for
        // "categorical imperative": one book dominates the top of the list,
        // and the hits that would refill its capped slots are the diary noise
        // the merge just ranked below it.
        var hits: [Hit] = []
        for i in 1...8 { hits.append(hit(id: "kant\(i)", content: lorem, score: 0.78, title: "Groundwork")) }
        hits.append(hit(id: "nietzsche", content: lorem, score: 0.71, title: "Twilight"))
        hits.append(hit(id: "evelyn", content: lorem, score: 0.65, title: "Evelyn"))
        // Below the window. Under a backfilling cap these would be packed.
        hits.append(hit(id: "pepys1", content: lorem, score: 0.65, title: "Pepys"))
        hits.append(hit(id: "boswell1", content: lorem, score: 0.63, title: "Boswell"))
        hits.append(hit(id: "pepys2", content: lorem, score: 0.62, title: "Pepys"))

        let budget = ContextBudgeter.Budget(maxPassages: 10, maxPassagesPerSource: 2)
        let packed = ContextBudgeter(budget: budget).pack(hits, question: "duty?")

        // Two Kant, then the six capped-out Kant spent slots 3-8, then
        // Nietzsche and Evelyn took 9 and 10. Nothing from rank 11 on.
        #expect(packed.passages.map(\.id) == ["kant1", "kant2", "nietzsche", "evelyn"])
        #expect(packed.dropped == hits.count - packed.passages.count)
    }

    @Test func thePerSourceCapCountsADiaryAsOneWork() {
        // A diary is one file per entry, so keyed by path every Pepys day was
        // its own source and the cap never bound. Keyed by title it does.
        let json = { (id: String, path: String) -> Hit in
            try! JSONDecoder().decode(
                Hit.self,
                from: Data(
                    """
                    {"kg_name": "pepys", "kg_kind": "KGKind.DIARY", "node_id": "\(id)",
                     "name": "chunk", "kind": "chunk", "score": 0.77, "summary": null,
                     "source_path": "\(path)", "content": "\(lorem)", "timestamp": null,
                     "genre": "diaries", "title": "The Diary of Samuel Pepys",
                     "author": "Samuel Pepys"}
                    """.utf8))
        }
        let hits = [
            json("p1", "entry_0828_chunk_0.md"),
            json("p2", "entry_2756_chunk_0.md"),
            json("p3", "entry_2371_chunk_5.md"),
        ]
        let budget = ContextBudgeter.Budget(maxPassages: 10, maxPassagesPerSource: 2)
        let packed = ContextBudgeter(budget: budget).pack(hits, question: "fire?")
        #expect(packed.passages.map(\.id) == ["p1", "p2"])
    }

    @Test func thePerSourceCapKeepsTranslationsApart() {
        // Titles carry the translator, so this is not the case above.
        let hits = [
            hit(id: "l1", content: lorem, title: "The Divine Comedy (Longfellow)"),
            hit(id: "l2", content: lorem, title: "The Divine Comedy (Longfellow)"),
            hit(id: "c1", content: lorem, title: "The Divine Comedy (Cary)"),
            hit(id: "c2", content: lorem, title: "The Divine Comedy (Cary)"),
        ]
        let budget = ContextBudgeter.Budget(maxPassages: 10, maxPassagesPerSource: 2)
        let packed = ContextBudgeter(budget: budget).pack(hits, question: "hell?")
        #expect(packed.passages.count == 4)
    }

    @Test func thePerSourceCapStillLimitsWithinTheWindow() {
        // The cap's original job, unchanged: no source floods the prompt.
        let hits = (1...6).map { hit(id: "cary\($0)", content: lorem, title: "Inferno (Cary)") }
        let budget = ContextBudgeter.Budget(maxPassages: 10, maxPassagesPerSource: 2)
        let packed = ContextBudgeter(budget: budget).pack(hits, question: "hell?")
        #expect(packed.passages.count == 2)
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
