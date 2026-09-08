// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Naming a chat after its first question.

import Foundation
import Testing

@testable import KnowledgePressUI

@Suite("Conversation titles")
struct ConversationTitleTests {

    @Test("a short question is the title, unchanged")
    func shortQuestionIsUntouched() {
        #expect(ConversationTitle.title(for: "circles of Hell") == "circles of Hell")
    }

    @Test("a long question is cut at a word boundary, never mid-word")
    func longQuestionTrimsAtAWord() {
        let question =
            "descriptions of the Great Fire of London as Pepys recorded them day by day"
        let title = ConversationTitle.title(for: question)

        #expect(title.hasSuffix("..."))
        #expect(title.count <= ConversationTitle.defaultLimit + 3)
        // The cut lands between words: no partial token before the ellipsis.
        let body = title.dropLast(3)
        #expect(question.hasPrefix(body))
        #expect(body.last != " ")
        #expect(question.dropFirst(body.count).first == " ")
    }

    @Test("whitespace and newlines collapse to a single-line title")
    func whitespaceCollapses() {
        #expect(ConversationTitle.title(for: "  circles\n\tof   Hell  ") == "circles of Hell")
    }

    @Test("a question with no spaces still fits the limit")
    func oneLongTokenIsCutHard() {
        let title = ConversationTitle.title(for: String(repeating: "a", count: 200))
        #expect(title.count == ConversationTitle.defaultLimit + 3)
        #expect(title.hasSuffix("..."))
    }

    @Test("an empty or whitespace-only question gets a name anyway")
    func emptyQuestionGetsAName() {
        #expect(ConversationTitle.title(for: "") == "New chat")
        #expect(ConversationTitle.title(for: "   \n  ") == "New chat")
    }

    @Test("the limit is respected at exactly the boundary")
    func exactLimitIsNotTruncated() {
        let exact = String(repeating: "a", count: ConversationTitle.defaultLimit)
        #expect(ConversationTitle.title(for: exact) == exact)
    }
}
