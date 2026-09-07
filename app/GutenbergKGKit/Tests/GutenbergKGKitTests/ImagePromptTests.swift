// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0

import Foundation
import Testing

import GutenbergKGKit
@testable import KnowledgePressUI

@MainActor
@Suite struct ImagePromptTests {
    /// `Hit`'s compiler-synthesized memberwise init is internal to
    /// `GutenbergKGKit`, even though every stored property is `public` —
    /// that's always true of a cross-module struct unless the author writes
    /// a public initializer by hand. Decoding a fixture is the only way in
    /// from outside the module, same as every real `Hit` is ever built.
    private func hit(content: String? = nil, summary: String? = nil) -> Hit {
        let json: [String: Any?] = [
            "kg_name": "gutenberg", "kg_kind": "KGKind.GUTENBERG", "node_id": "n1", "name": "n1",
            "kind": "chunk", "score": 0.8, "summary": summary, "source_path": nil,
            "content": content, "timestamp": nil, "genre": "philosophy",
            "title": "The Republic", "author": "Plato",
        ]
        let data = try! JSONSerialization.data(withJSONObject: json.compactMapValues { $0 })
        return try! JSONDecoder().decode(Hit.self, from: data)
    }

    @Test func prefersTheAnswerOverPassages() {
        var turn = ChatTurn(question: "q", corpus: "all", engine: .worker)
        turn.answer = "The categorical imperative is a moral law."
        turn.retrieval = RetrievalResult(hits: [hit(content: "unused passage")], kgsQueried: 1, searchMs: 1)

        #expect(AppModel.imagePrompt(from: turn) == "The categorical imperative is a moral law.")
    }

    @Test func truncatesTheAnswerAt800Characters() {
        var turn = ChatTurn(question: "q", corpus: "all", engine: .worker)
        turn.answer = String(repeating: "a", count: 900)

        #expect(AppModel.imagePrompt(from: turn).count == 800)
    }

    @Test func fallsBackToTheTopThreePassagesWhenThereIsNoAnswer() {
        var turn = ChatTurn(question: "q", corpus: "all", engine: .off)
        turn.retrieval = RetrievalResult(
            hits: [
                hit(content: "first passage"),
                hit(content: "second passage"),
                hit(content: "third passage"),
                hit(content: "fourth passage, never reached"),
            ],
            kgsQueried: 1, searchMs: 1)

        #expect(
            AppModel.imagePrompt(from: turn)
                == "first passage second passage third passage")
    }

    @Test func fallsBackToSummaryWhenContentIsEmpty() {
        var turn = ChatTurn(question: "q", corpus: "all", engine: .off)
        turn.retrieval = RetrievalResult(
            hits: [hit(content: "", summary: "a summary instead")], kgsQueried: 1, searchMs: 1)

        #expect(AppModel.imagePrompt(from: turn) == "a summary instead")
    }

    @Test func isEmptyWithNeitherAnswerNorPassages() {
        let turn = ChatTurn(question: "q", corpus: "all", engine: .off)
        #expect(AppModel.imagePrompt(from: turn).isEmpty)
    }
}
