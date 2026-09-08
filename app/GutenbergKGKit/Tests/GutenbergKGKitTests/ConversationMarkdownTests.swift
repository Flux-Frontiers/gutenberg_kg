// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// What leaves the app when a chat is exported.
//
// The passages are the reason these tests exist. An answer shared without its
// evidence is an unattributed paragraph about a book, which is the one thing
// this project is built not to produce -- so the export must carry the work,
// the author, and the score, and must be honest about how many passages the
// model actually saw.

import Foundation
import GutenbergKGKit
import Testing

@testable import KnowledgePressUI

@Suite("Conversation export")
struct ConversationMarkdownTests {

    private func hit(
        title: String = "The Divine Comedy",
        author: String = "Dante Alighieri",
        genre: String = "world-literature",
        score: Double = 0.812,
        content: String = "Midway upon the journey of our life I found myself within a forest dark."
    ) -> Hit {
        let json = """
            {"node_id":"gutenberg:chunk_\(UUID().uuidString)","name":"Inferno","kind":"chunk",
             "score":\(score),"kg_name":"world-literature","kg_kind":"DocKG",
             "title":"\(title)","author":"\(author)","genre":"\(genre)",
             "summary":null,"source_path":"x.md","timestamp":null,
             "content":"\(content)"}
            """
        return try! JSONDecoder().decode(Hit.self, from: Data(json.utf8))
    }

    private func answeredTurn(hits: [Hit]? = nil, used: Int = 5) -> ChatTurn {
        var turn = ChatTurn(
            question: "circles of Hell", corpus: "world-literature", engine: .onDevice)
        let passages = hits ?? [hit()]
        turn.retrieval = RetrievalResult(hits: passages, kgsQueried: 3, searchMs: 42)
        turn.answer = "Dante's Hell is arranged in nine concentric circles."
        turn.metrics = SynthesisMetrics(
            elapsedMs: 1200, passagesUsed: used, passagesDropped: max(0, passages.count - used),
            estimatedPromptTokens: 3100, model: "Apple Foundation Models (on-device)")
        return turn
    }

    private func render(_ turns: [ChatTurn], title: String = "circles of Hell") -> String {
        ConversationMarkdown.render(Conversation(title: title, turns: turns))
    }

    @Test("the document carries the question, the answer, and the title")
    func carriesTheExchange() {
        let out = render([answeredTurn()])
        #expect(out.contains("# circles of Hell"))
        #expect(out.contains("## circles of Hell"))
        #expect(out.contains("Dante's Hell is arranged in nine concentric circles."))
    }

    @Test("every quoted passage carries its work, author, genre, and score")
    func passagesKeepTheirAttribution() {
        let out = render([answeredTurn()])
        #expect(out.contains("The Divine Comedy"))
        #expect(out.contains("Dante Alighieri"))
        #expect(out.contains("world-literature"))
        #expect(out.contains("0.812"))
        #expect(out.contains("Midway upon the journey"))
    }

    @Test("the export records which engine answered and what it was asked against")
    func provenanceIsRecorded() {
        let out = render([answeredTurn()])
        #expect(out.contains("scope: `world-literature`"))
        #expect(out.contains("On-device"))
        #expect(out.contains("Apple Foundation Models (on-device)"))
    }

    @Test("it says how many passages actually reached the model, not just how many were found")
    func retrievedVersusUsedIsHonest() {
        // 25 retrieved, 5 in context: quoting "25 passages" would overstate
        // what the answer rests on.
        let many = (0..<25).map { _ in hit() }
        let out = render([answeredTurn(hits: many, used: 5)])
        #expect(out.contains("25 retrieved"))
        #expect(out.contains("5 reached the model"))
    }

    @Test("a long list is quoted in part, and says so")
    func longListsAreTrimmedVisibly() {
        let many = (0..<25).map { _ in hit() }
        let out = render([answeredTurn(hits: many, used: 5)])
        #expect(out.contains("quoted"))
        // Only the quoted few, not all 25.
        #expect(out.components(separatedBy: "  > ").count - 1 == ConversationMarkdown.quotedPassages)
    }

    @Test("a stopped answer exports as stopped rather than as a blank section")
    func cancelledTurnSaysSo() {
        var turn = ChatTurn(question: "circles of Hell", corpus: "all", engine: .onDevice)
        turn.retrieval = RetrievalResult(hits: [hit()], kgsQueried: 1, searchMs: 5)
        turn.synthesisFailure = .cancelled

        let out = render([turn])
        #expect(out.contains("Stopped."))
        // The evidence survives even though the answer does not.
        #expect(out.contains("The Divine Comedy"))
    }

    @Test("a passages-only turn exports its passages and says why there is no answer")
    func passagesOnlyTurnIsComplete() {
        var turn = ChatTurn(question: "pillar of salt", corpus: "sacred-texts", engine: .off)
        turn.retrieval = RetrievalResult(hits: [hit()], kgsQueried: 2, searchMs: 8)

        let out = render([turn])
        #expect(out.contains("Answer generation was off"))
        #expect(out.contains("The Divine Comedy"))
    }

    @Test("a retrieval failure is recorded rather than dropped")
    func failedTurnIsRecorded() {
        var turn = ChatTurn(question: "circles of Hell", corpus: "all", engine: .worker)
        turn.errorMessage = "Could not reach the worker."

        let out = render([turn])
        #expect(out.contains("Could not reach the worker."))
    }

    @Test("every turn in a conversation appears, in order")
    func allTurnsAppearInOrder() {
        var second = answeredTurn()
        second = ChatTurn(question: "and Purgatory?", corpus: "all", engine: .off)
        second.retrieval = RetrievalResult(hits: [], kgsQueried: 1, searchMs: 2)

        let out = render([answeredTurn(), second])
        let first = try! #require(out.range(of: "## circles of Hell"))
        let next = try! #require(out.range(of: "## and Purgatory?"))
        #expect(first.lowerBound < next.lowerBound)
    }

    @Test("a passage is quoted on one line so the blockquote survives")
    func passagesAreSingleLine() {
        let multiline = hit(content: "Midway upon the journey\\nof our life")
        let out = render([answeredTurn(hits: [multiline])])
        // The quote marker appears once for the one passage; a raw newline
        // inside it would break the blockquote into unquoted prose.
        let quoted = out.components(separatedBy: "\n").filter { $0.hasPrefix("  > ") }
        #expect(quoted.count == 1)
        #expect(quoted[0].contains("journey of our life"))
    }

    @Test("the filename is derived from the title and is filesystem-safe")
    func filenameIsSafe() {
        let conversation = Conversation(title: "circles of Hell: Dante/Inferno?", turns: [])
        let name = ConversationMarkdown.filename(for: conversation)
        #expect(name.hasSuffix(".md"))
        #expect(!name.contains("/"))
        #expect(!name.contains(":"))
        #expect(!name.contains("?"))
        #expect(name.contains("circles"))
    }

    @Test("a title with nothing usable still yields a filename")
    func filenameNeverEmpty() {
        #expect(
            ConversationMarkdown.filename(for: Conversation(title: "///", turns: []))
                == "conversation.md")
    }

    @Test("an empty conversation renders a document rather than nothing")
    func emptyConversationStillRenders() {
        let out = render([], title: "empty")
        #expect(out.contains("# empty"))
        #expect(out.contains("The Knowledge Press"))
    }
}
