// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// What a saved chat is. A conversation is the existing `ChatTurn` values plus
// an identity -- a title and two timestamps -- so nothing about a turn's shape
// changes for the view code.

import Foundation
import GutenbergKGKit

/// One saved chat: its turns, in order, and enough identity to list it.
struct Conversation: Codable, Identifiable, Sendable {
    /// Bumped when the on-disk shape changes in a way a reader must handle.
    ///
    /// Costs nothing now and makes the first migration a `switch` rather than
    /// a guess about which of two shapes a file is in.
    static let currentSchema = 1

    var schemaVersion: Int = Conversation.currentSchema
    let id: UUID
    var title: String
    let createdAt: Date
    var updatedAt: Date
    var turns: [ChatTurn]

    init(
        id: UUID = UUID(),
        title: String,
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        turns: [ChatTurn]
    ) {
        self.id = id
        self.title = title
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.turns = turns
    }

    /// A conversation missing `schemaVersion` predates the field; treat it as
    /// version 1 rather than refusing to open it.
    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion =
            try container.decodeIfPresent(Int.self, forKey: .schemaVersion)
            ?? Conversation.currentSchema
        id = try container.decode(UUID.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        createdAt = try container.decode(Date.self, forKey: .createdAt)
        updatedAt = try container.decode(Date.self, forKey: .updatedAt)
        turns = try container.decode([ChatTurn].self, forKey: .turns)
    }

    /// What the sidebar shows for this conversation.
    var summary: ConversationSummary {
        ConversationSummary(
            id: id,
            title: title,
            createdAt: createdAt,
            updatedAt: updatedAt,
            turnCount: turns.count,
            lastEngine: turns.last?.engine ?? .off,
            lastCorpus: turns.last?.corpus ?? "all")
    }
}

/// A conversation's listing row, so the sidebar never decodes an answer it is
/// not going to show.
struct ConversationSummary: Codable, Identifiable, Hashable, Sendable {
    let id: UUID
    var title: String
    let createdAt: Date
    var updatedAt: Date
    var turnCount: Int
    /// Engine and scope of the most recent turn, for the row's badge. Scope in
    /// particular is worth showing: it is the largest single lever on answer
    /// quality, so "which corpus was this asked against" is part of reading an
    /// old chat correctly.
    var lastEngine: AnswerEngine
    var lastCorpus: String
}
