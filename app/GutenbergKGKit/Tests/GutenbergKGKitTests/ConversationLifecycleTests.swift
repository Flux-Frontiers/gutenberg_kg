// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// When a conversation comes into existence, and what happens to the buffer
// when the reader switches away from it or deletes it.

import Foundation
import GutenbergKGKit
import Testing

@testable import KnowledgePressUI

@MainActor
@Suite("Conversation lifecycle")
struct ConversationLifecycleTests {

    /// A model wired to a scratch directory and a scratch defaults domain, so
    /// no test touches the reader's real conversations or settings.
    private func withModel(_ body: (AppModel, ConversationStore) async throws -> Void) async throws {
        let directory = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("ConversationLifecycle.\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let suite = "ConversationLifecycleTests.\(UUID().uuidString)"
        let previous = AppModel.defaults
        AppModel.defaults = UserDefaults(suiteName: suite)!
        defer {
            AppModel.defaults = previous
            UserDefaults.standard.removePersistentDomain(forName: suite)
            try? FileManager.default.removeItem(at: directory)
        }

        let store = ConversationStore(directory: directory)
        try await body(AppModel(store: store), store)
    }

    /// A completed turn, as the query paths leave one before persisting.
    private func completedTurn(_ question: String, corpus: String = "all") -> ChatTurn {
        var turn = ChatTurn(question: question, corpus: corpus, engine: .off)
        turn.retrieval = RetrievalResult(hits: [], kgsQueried: 1, searchMs: 3)
        return turn
    }

    @Test("the first completed turn creates a conversation named after the question")
    func firstTurnCreatesAConversation() async throws {
        try await withModel { model, store in
            #expect(model.activeConversation == nil)

            model.turns = [completedTurn("descriptions of the Great Fire of London")]
            model.persistActiveConversation()
            await model.pendingPersist?.value

            let conversation = try #require(model.activeConversation)
            #expect(conversation.title == "descriptions of the Great Fire of London")
            let saved = try store.summaries()
            #expect(saved.count == 1)
            #expect(model.conversations.count == 1)
        }
    }

    @Test("persisting twice updates one conversation rather than making two")
    func persistingTwiceUpdatesInPlace() async throws {
        try await withModel { model, store in
            model.turns = [completedTurn("circles of Hell")]
            model.persistActiveConversation()
            await model.pendingPersist?.value
            let id = try #require(model.activeConversation?.id)

            model.turns.append(completedTurn("and Purgatory?"))
            model.persistActiveConversation()
            await model.pendingPersist?.value

            #expect(model.activeConversation?.id == id)
            let saved = try store.summaries()
            let reloaded = try store.load(id)
            #expect(saved.count == 1)
            #expect(reloaded.turns.count == 2)
        }
    }

    @Test("New chat on an empty buffer creates nothing")
    func newConversationOnEmptyBufferIsANoOp() async throws {
        try await withModel { model, store in
            model.newConversation()
            await model.pendingPersist?.value

            #expect(model.activeConversation == nil)
            let saved = try store.summaries()
            #expect(saved.isEmpty)
            #expect(model.conversations.isEmpty)
        }
    }

    @Test("New chat saves what is on screen, then clears it")
    func newConversationSavesThenClears() async throws {
        try await withModel { model, store in
            model.turns = [completedTurn("circles of Hell")]
            model.newConversation()
            await model.pendingPersist?.value

            #expect(model.turns.isEmpty)
            #expect(model.activeConversation == nil)
            let saved = try store.summaries()
            #expect(saved.map(\.title) == ["circles of Hell"])
        }
    }

    @Test("selecting a conversation swaps the buffer")
    func selectSwapsTheBuffer() async throws {
        try await withModel { model, _ in
            model.turns = [completedTurn("circles of Hell")]
            model.persistActiveConversation()
            await model.pendingPersist?.value
            let first = try #require(model.activeConversation?.id)

            model.newConversation()
            await model.pendingPersist?.value
            model.turns = [completedTurn("pillar of salt"), completedTurn("and then?")]
            model.persistActiveConversation()
            await model.pendingPersist?.value
            #expect(model.turns.count == 2)

            model.select(first)
            await model.pendingPersist?.value

            #expect(model.activeConversation?.id == first)
            #expect(model.turns.count == 1)
            #expect(model.turns.first?.question == "circles of Hell")
            // Switching away saved the other one rather than dropping it.
            #expect(model.conversations.count == 2)
        }
    }

    @Test("deleting the open conversation clears the buffer")
    func deletingActiveClearsTheBuffer() async throws {
        try await withModel { model, store in
            model.turns = [completedTurn("circles of Hell")]
            model.persistActiveConversation()
            await model.pendingPersist?.value
            let id = try #require(model.activeConversation?.id)

            model.delete(id)
            await model.pendingPersist?.value

            #expect(model.turns.isEmpty)
            #expect(model.activeConversation == nil)
            #expect(model.conversations.isEmpty)
            let saved = try store.summaries()
            #expect(saved.isEmpty)
        }
    }

    @Test("deleting a conversation that is not open leaves the buffer alone")
    func deletingOtherKeepsTheBuffer() async throws {
        try await withModel { model, _ in
            model.turns = [completedTurn("circles of Hell")]
            model.persistActiveConversation()
            await model.pendingPersist?.value
            let first = try #require(model.activeConversation?.id)

            model.newConversation()
            await model.pendingPersist?.value
            model.turns = [completedTurn("pillar of salt")]
            model.persistActiveConversation()
            await model.pendingPersist?.value

            model.delete(first)
            await model.pendingPersist?.value

            #expect(model.turns.first?.question == "pillar of salt")
            #expect(model.activeConversation != nil)
            #expect(model.conversations.count == 1)
        }
    }

    @Test("an unsaved buffer is dropped by delete without a conversation to remove")
    func deleteActiveWithNothingSaved() async throws {
        try await withModel { model, store in
            model.turns = [completedTurn("never persisted")]
            model.deleteActiveConversation()
            await model.pendingPersist?.value

            #expect(model.turns.isEmpty)
            let saved = try store.summaries()
            #expect(saved.isEmpty)
        }
    }

    @Test("rename refuses an empty title and keeps the old one")
    func renameRefusesEmpty() async throws {
        try await withModel { model, store in
            model.turns = [completedTurn("circles of Hell")]
            model.persistActiveConversation()
            await model.pendingPersist?.value
            let id = try #require(model.activeConversation?.id)

            model.rename(id, to: "   \n ")
            await model.pendingPersist?.value
            #expect(model.activeConversation?.title == "circles of Hell")
            let unchanged = try store.load(id)
            #expect(unchanged.title == "circles of Hell")

            model.rename(id, to: "  Dante  ")
            await model.pendingPersist?.value
            #expect(model.activeConversation?.title == "Dante")
            let renamed = try store.load(id)
            #expect(renamed.title == "Dante")
        }
    }

    @Test("cancel marks the in-flight turn stopped and saves it that way")
    func cancelMarksTheTurnStopped() async throws {
        try await withModel { model, store in
            var turn = ChatTurn(question: "circles of Hell", corpus: "all", engine: .onDevice)
            turn.retrieval = RetrievalResult(hits: [], kgsQueried: 1, searchMs: 3)
            model.turns = [turn]
            #expect(model.turns[0].isStreaming)

            model.cancel()
            await model.pendingPersist?.value

            #expect(model.turns[0].synthesisFailure == .cancelled)
            #expect(model.turns[0].isStreaming == false)

            let id = try #require(model.activeConversation?.id)
            let stopped = try store.load(id)
            #expect(stopped.turns[0].synthesisFailure == .cancelled)
        }
    }

    @Test("a model with no store still answers questions, it just saves nothing")
    func noStoreDegradesQuietly() async throws {
        let model = AppModel(store: nil)
        model.turns = [completedTurn("circles of Hell")]
        model.persistActiveConversation()
        await model.pendingPersist?.value

        #expect(model.activeConversation == nil)
        #expect(model.conversations.isEmpty)
        #expect(model.turns.count == 1)
    }

    @Test("a relaunch starts empty, and the saved chat reopens intact from the sidebar")
    func relaunchStartsEmptyAndReopensOnDemand() async throws {
        try await withModel { model, store in
            var turn = ChatTurn(question: "circles of Hell", corpus: "all", engine: .onDevice)
            turn.retrieval = RetrievalResult(hits: [], kgsQueried: 4, searchMs: 31)
            turn.answer = "Dante's Hell is arranged in nine concentric circles."
            turn.metrics = SynthesisMetrics(
                elapsedMs: 900, passagesUsed: 5, passagesDropped: 20,
                estimatedPromptTokens: 3100, model: "Apple Foundation Models (on-device)")
            model.turns = [turn]
            model.persistActiveConversation()
            await model.pendingPersist?.value
            let id = try #require(model.activeConversation?.id)

            // A new model over the same directory is what a relaunch produces.
            let relaunched = AppModel(store: store)
            await relaunched.pendingPersist?.value

            // Listed, but not reopened: the reader gets an empty chat.
            #expect(relaunched.conversations.map(\.title) == ["circles of Hell"])
            #expect(relaunched.activeConversation == nil)
            #expect(relaunched.turns.isEmpty)

            // Everything is still there the moment the sidebar asks for it.
            relaunched.select(id)
            await relaunched.pendingPersist?.value

            #expect(relaunched.activeConversation?.id == id)
            #expect(relaunched.turns.count == 1)
            #expect(relaunched.turns[0].answer.hasPrefix("Dante's Hell"))
            // The stats line reads off these two.
            #expect(relaunched.turns[0].retrieval?.searchMs == 31)
            #expect(relaunched.turns[0].metrics?.elapsedMs == 900)
        }
    }

    @Test("a cancelled turn reopens as stopped, not as one still streaming")
    func reopenedCancelledTurnReadsAsStopped() async throws {
        try await withModel { model, store in
            var turn = ChatTurn(question: "circles of Hell", corpus: "all", engine: .onDevice)
            turn.retrieval = RetrievalResult(hits: [], kgsQueried: 1, searchMs: 3)
            model.turns = [turn]
            model.cancel()
            await model.pendingPersist?.value
            let id = try #require(model.activeConversation?.id)

            let relaunched = AppModel(store: store)
            await relaunched.pendingPersist?.value
            relaunched.select(id)
            await relaunched.pendingPersist?.value

            #expect(relaunched.turns.count == 1)
            #expect(relaunched.turns[0].isStreaming == false)
            #expect(relaunched.turns[0].synthesisFailure?.displayMessage == "Stopped.")
        }
    }

    @Test("the newest chat is the one listed first")
    func theNewestChatSortsFirst() async throws {
        try await withModel { model, store in
            model.turns = [completedTurn("older question")]
            model.persistActiveConversation()
            await model.pendingPersist?.value

            model.newConversation()
            await model.pendingPersist?.value
            model.turns = [completedTurn("newer question")]
            model.persistActiveConversation()
            await model.pendingPersist?.value

            let relaunched = AppModel(store: store)
            await relaunched.pendingPersist?.value

            #expect(relaunched.turns.isEmpty)
            #expect(relaunched.conversations.count == 2)
            // Newest first is what the sidebar shows, and what `select` would
            // reach for -- it is simply no longer opened unasked.
            let newest = try #require(relaunched.conversations.first)
            relaunched.select(newest.id)
            await relaunched.pendingPersist?.value
            #expect(relaunched.turns.first?.question == "newer question")
        }
    }
}
