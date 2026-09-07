// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The store: that a conversation round-trips with its evidence intact, and
// that the index -- which is a cache, not the truth -- repairs itself.

import Foundation
import GutenbergKGKit
import Testing

@testable import KnowledgePressUI

@Suite("Conversation store")
struct ConversationStoreTests {

    /// A scratch directory per test. Nothing here touches the real
    /// Application Support.
    private func withScratchStore(_ body: (ConversationStore) throws -> Void) throws {
        let directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("ConversationStoreTests.\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try body(ConversationStore(directory: directory))
    }

    /// A turn built the way the app builds one, then filled in as a completed
    /// answer would fill it.
    private func completedTurn(
        question: String = "circles of Hell",
        corpus: String = "world-literature"
    ) -> ChatTurn {
        var turn = ChatTurn(question: question, corpus: corpus, engine: .onDevice)
        turn.retrieval = RetrievalResult(hits: [hit()], kgsQueried: 3, searchMs: 42)
        turn.answer = "Dante's Hell is arranged in nine concentric circles."
        turn.metrics = SynthesisMetrics(
            elapsedMs: 1234, passagesUsed: 5, passagesDropped: 20,
            estimatedPromptTokens: 3200, model: "Apple Foundation Models (on-device)")
        return turn
    }

    /// `Hit`'s memberwise init is internal to GutenbergKGKit, so fixtures are
    /// decoded from JSON -- the same approach `ImagePromptTests` uses.
    private func hit() -> Hit {
        let json = """
            {"node_id":"gutenberg:chunk_1","name":"Inferno","kind":"chunk","score":0.81,
             "kg_name":"world-literature","kg_kind":"DocKG","title":"The Divine Comedy",
             "author":"Dante Alighieri","genre":"world-literature","summary":null,
             "source_path":"world-literature/Divine Comedy/inferno.md","timestamp":null,
             "content":"Midway upon the journey of our life."}
            """
        return try! JSONDecoder().decode(Hit.self, from: Data(json.utf8))
    }

    @Test("a saved conversation round-trips with its passages, metrics, and image path")
    func roundTrip() throws {
        try withScratchStore { store in
            var first = completedTurn()
            first.imageFile = "images/\(UUID().uuidString).png"
            var second = ChatTurn(question: "and Purgatory?", corpus: "all", engine: .onDevice)
            second.retrieval = RetrievalResult(hits: [hit()], kgsQueried: 1, searchMs: 9)
            second.synthesisFailure = .cancelled

            let conversation = Conversation(title: "circles of Hell", turns: [first, second])
            try store.save(conversation)

            let loaded = try store.load(conversation.id)
            #expect(loaded.id == conversation.id)
            #expect(loaded.title == "circles of Hell")
            #expect(loaded.schemaVersion == Conversation.currentSchema)
            #expect(loaded.turns.count == 2)

            // The evidence, not just the answer.
            #expect(loaded.turns[0].retrieval?.hits.count == 1)
            #expect(loaded.turns[0].retrieval?.hits.first?.title == "The Divine Comedy")
            #expect(loaded.turns[0].retrieval?.searchMs == 42)
            #expect(loaded.turns[0].metrics?.passagesDropped == 20)
            #expect(loaded.turns[0].engine == .onDevice)
            #expect(loaded.turns[0].imageFile == first.imageFile)
            #expect(loaded.turns[1].synthesisFailure == .cancelled)
            // Ids survive, so a render started before a reload still lands on
            // the turn it belongs to.
            #expect(loaded.turns[0].id == first.id)
        }
    }

    @Test("a cancelled turn does not claim to be streaming when it is read back")
    func cancelledTurnStopsStreaming() throws {
        try withScratchStore { store in
            var turn = ChatTurn(question: "circles of Hell", corpus: "all", engine: .onDevice)
            turn.retrieval = RetrievalResult(hits: [hit()], kgsQueried: 1, searchMs: 5)
            #expect(turn.isStreaming)  // the state cancel() must not leave behind

            turn.synthesisFailure = .cancelled
            let conversation = Conversation(title: "stopped", turns: [turn])
            try store.save(conversation)

            let loaded = try store.load(conversation.id)
            #expect(loaded.turns[0].isStreaming == false)
            #expect(loaded.turns[0].synthesisFailure?.displayMessage == "Stopped.")
            #expect(loaded.turns[0].synthesisFailure?.isRecoverableRemotely == false)
        }
    }

    @Test("summaries are newest first")
    func summariesAreNewestFirst() throws {
        try withScratchStore { store in
            let old = Conversation(
                title: "older", createdAt: .distantPast,
                updatedAt: Date(timeIntervalSince1970: 1_000_000), turns: [completedTurn()])
            let recent = Conversation(
                title: "newer", createdAt: .distantPast,
                updatedAt: Date(timeIntervalSince1970: 2_000_000), turns: [completedTurn()])
            try store.save(old)
            try store.save(recent)

            let summaries = try store.summaries()
            #expect(summaries.map(\.title) == ["newer", "older"])
            #expect(summaries.first?.turnCount == 1)
            #expect(summaries.first?.lastCorpus == "world-literature")
            #expect(summaries.first?.lastEngine == .onDevice)
        }
    }

    @Test("deleting removes the directory and the index entry")
    func deleteRemovesEverything() throws {
        try withScratchStore { store in
            let conversation = Conversation(title: "doomed", turns: [completedTurn()])
            try store.save(conversation)
            let before = try store.summaries()
            #expect(before.count == 1)

            try store.delete(conversation.id)
            let after = try store.summaries()
            #expect(after.isEmpty)
            #expect(
                FileManager.default.fileExists(
                    atPath: store.conversationDirectory(conversation.id).path) == false)
        }
    }

    @Test("a missing index is rebuilt from the conversation directories")
    func indexRebuildsWhenDeleted() throws {
        try withScratchStore { store in
            try store.save(Conversation(title: "one", turns: [completedTurn()]))
            try store.save(Conversation(title: "two", turns: [completedTurn()]))

            try FileManager.default.removeItem(
                at: store.directory.appendingPathComponent("index.json"))

            let summaries = try store.summaries()
            #expect(summaries.count == 2)
            #expect(Set(summaries.map(\.title)) == ["one", "two"])
        }
    }

    @Test("a corrupt index is rebuilt rather than believed")
    func indexRebuildsWhenCorrupt() throws {
        try withScratchStore { store in
            try store.save(Conversation(title: "survivor", turns: [completedTurn()]))
            try Data("this is not json".utf8).write(
                to: store.directory.appendingPathComponent("index.json"))

            let summaries = try store.summaries()
            #expect(summaries.map(\.title) == ["survivor"])
        }
    }

    @Test("a half-written temporary file is never listed as a conversation")
    func temporaryFilesAreInvisible() throws {
        try withScratchStore { store in
            let conversation = Conversation(title: "real", turns: [completedTurn()])
            try store.save(conversation)

            // What a crash mid-save leaves behind: a directory whose name is a
            // UUID, holding a partial temporary file and no conversation.json.
            let orphan = store.conversationDirectory(UUID())
            try FileManager.default.createDirectory(at: orphan, withIntermediateDirectories: true)
            try Data("{\"turns\": [".utf8).write(
                to: orphan.appendingPathComponent("conversation.json.\(UUID().uuidString).tmp"))

            try FileManager.default.removeItem(
                at: store.directory.appendingPathComponent("index.json"))
            let summaries = try store.summaries()
            #expect(summaries.map(\.title) == ["real"])
        }
    }

    @Test("an illustration is written beside its conversation, not inside it")
    func imagesGoOutOfLine() throws {
        try withScratchStore { store in
            let conversation = Conversation(title: "illustrated", turns: [completedTurn()])
            try store.save(conversation)

            let png = Data([0x89, 0x50, 0x4E, 0x47])
            let turnID = conversation.turns[0].id
            let file = try store.writeImage(png, conversation: conversation.id, turn: turnID)

            #expect(file == "images/\(turnID.uuidString).png")
            let url = store.imageURL(conversation: conversation.id, file: file)
            #expect(try Data(contentsOf: url) == png)

            // The bytes must not have found their way into the JSON.
            let json = try String(
                contentsOf: store.conversationDirectory(conversation.id)
                    .appendingPathComponent("conversation.json"), encoding: .utf8)
            #expect(json.contains("iVBOR") == false)
        }
    }

    @Test("a turn encodes without its transient rendering state")
    func transientStateIsNotEncoded() throws {
        var turn = completedTurn()
        turn.isRenderingImage = true
        turn.generatedImage = try JSONDecoder().decode(
            GeneratedImage.self,
            from: Data(#"{"image_b64":"iVBORw0KGgo=","image_model":"mflux"}"#.utf8))

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let json = try String(data: encoder.encode(turn), encoding: .utf8)!

        // A 4.2 MB base64 blob inside the conversation file is exactly what
        // `imageFile` exists to avoid.
        #expect(json.contains("generatedImage") == false)
        #expect(json.contains("iVBOR") == false)
        #expect(json.contains("isRenderingImage") == false)
        #expect(json.contains("\"question\"") == true)
    }

    @Test("a conversation file written before schemaVersion existed still opens")
    func missingSchemaVersionDefaults() throws {
        let json = """
            {"id":"\(UUID().uuidString)","title":"legacy",
             "createdAt":"2026-09-01T00:00:00Z","updatedAt":"2026-09-01T00:00:00Z",
             "turns":[]}
            """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let conversation = try decoder.decode(Conversation.self, from: Data(json.utf8))
        #expect(conversation.schemaVersion == 1)
        #expect(conversation.title == "legacy")
    }
}
