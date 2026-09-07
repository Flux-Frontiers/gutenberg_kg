// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Conversations on disk: one directory each, JSON inside, images beside it.
//
// Plain files rather than SwiftData or Core Data, for the reason every
// on-device question in this project has been answered so far -- they can be
// pulled off a device with `devicectl device copy from` and read in an
// editor, the same way the synthesis traces were.
//
//   Conversations/
//     index.json                 [ConversationSummary], newest first
//     3F2504E0-.../
//       conversation.json
//       images/9A1B2C3D-....png

import Foundation

/// Reading and writing saved conversations under a directory.
///
/// A `struct` over an injected directory, mirroring the seam `AppModel.defaults`
/// provides for `UserDefaults`: tests point it at a scratch directory and never
/// touch the real Application Support.
struct ConversationStore: Sendable {
    let directory: URL

    private static let indexFile = "index.json"
    private static let conversationFile = "conversation.json"
    private static let imagesDirectory = "images"

    init(directory: URL) {
        self.directory = directory
    }

    /// `Application Support/Conversations`, created on first use.
    ///
    /// Deliberately *not* marked `isExcludedFromBackup`, unlike
    /// `CorpusPacks.defaultDirectory`. The corpus is regenerable from the
    /// repo and costs a gigabyte; these are the reader's own questions and
    /// answers, which nothing else can reproduce.
    static func defaultDirectory() -> URL? {
        guard
            var url = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)
                .first
        else { return nil }
        url.appendPathComponent("Conversations", isDirectory: true)
        if !FileManager.default.fileExists(atPath: url.path) {
            try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        }
        return url
    }

    // MARK: - Coding

    /// ISO-8601 *with* fractional seconds.
    ///
    /// The precision is not cosmetic: `JSONEncoder`'s stock `.iso8601` writes
    /// whole seconds, so two conversations saved in the same second read back
    /// with identical `updatedAt` values and "newest first" becomes whichever
    /// order the directory happened to enumerate in. Start a chat, start
    /// another, and the sidebar could list them backwards.
    private static let timestamps = Date.ISO8601FormatStyle(includingFractionalSeconds: true)

    /// The same format without the fraction, accepted on the way in so a file
    /// written by any other ISO-8601 producer still opens.
    private static let plainTimestamps = Date.ISO8601FormatStyle()

    private static var encoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            try container.encode(date.formatted(timestamps))
        }
        // Sorted and indented so a conversation file diffs cleanly and reads
        // as text -- the whole reason for choosing files over a database.
        encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
        return encoder
    }

    private static var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            if let date = try? Date(text, strategy: timestamps) { return date }
            if let date = try? Date(text, strategy: plainTimestamps) { return date }
            throw DecodingError.dataCorruptedError(
                in: try decoder.singleValueContainer(),
                debugDescription: "not an ISO-8601 date: \(text)")
        }
        return decoder
    }

    /// Newest first, with `createdAt` and then the id breaking ties, so the
    /// order is total rather than merely mostly-defined -- two chats can still
    /// share a millisecond, and a list that reshuffles between launches reads
    /// as a bug.
    private static func newestFirst(_ a: ConversationSummary, _ b: ConversationSummary) -> Bool {
        if a.updatedAt != b.updatedAt { return a.updatedAt > b.updatedAt }
        if a.createdAt != b.createdAt { return a.createdAt > b.createdAt }
        return a.id.uuidString > b.id.uuidString
    }

    // MARK: - Paths

    func conversationDirectory(_ id: UUID) -> URL {
        directory.appendingPathComponent(id.uuidString, isDirectory: true)
    }

    private func conversationURL(_ id: UUID) -> URL {
        conversationDirectory(id).appendingPathComponent(Self.conversationFile)
    }

    private var indexURL: URL {
        directory.appendingPathComponent(Self.indexFile)
    }

    /// Where a turn's illustration lives, given the relative path recorded on
    /// the turn.
    func imageURL(conversation: UUID, file: String) -> URL {
        conversationDirectory(conversation).appendingPathComponent(file)
    }

    // MARK: - Reading

    /// Every conversation, newest first.
    ///
    /// Reads `index.json` when it can and rebuilds it from the directories
    /// when it cannot. The index is a cache: it exists so the sidebar lists
    /// titles without decoding every answer, and it is never the authority on
    /// what conversations exist.
    func summaries() throws -> [ConversationSummary] {
        if let data = try? Data(contentsOf: indexURL),
            let decoded = try? Self.decoder.decode([ConversationSummary].self, from: data)
        {
            return decoded.sorted(by: Self.newestFirst)
        }
        return try rebuildIndex()
    }

    /// One conversation, in full.
    func load(_ id: UUID) throws -> Conversation {
        let data = try Data(contentsOf: conversationURL(id))
        return try Self.decoder.decode(Conversation.self, from: data)
    }

    // MARK: - Writing

    /// Write a conversation and refresh the index.
    ///
    /// The JSON goes to a temporary file in its own directory and is renamed
    /// into place, so a crash or a kill mid-write leaves the previous version
    /// intact rather than a truncated file that will not decode.
    func save(_ conversation: Conversation) throws {
        let directory = conversationDirectory(conversation.id)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let data = try Self.encoder.encode(conversation)
        let temporary = directory.appendingPathComponent(
            "\(Self.conversationFile).\(UUID().uuidString).tmp")
        try data.write(to: temporary, options: .atomic)
        _ = try FileManager.default.replaceItemAt(conversationURL(conversation.id), withItemAt: temporary)

        _ = try? rebuildIndex()
    }

    /// Remove a conversation and everything under it, then refresh the index.
    func delete(_ id: UUID) throws {
        let directory = conversationDirectory(id)
        if FileManager.default.fileExists(atPath: directory.path) {
            try FileManager.default.removeItem(at: directory)
        }
        _ = try? rebuildIndex()
    }

    /// Write a turn's illustration beside its conversation.
    ///
    /// :returns: The path to record on the turn, relative to the conversation
    ///     directory.
    func writeImage(_ data: Data, conversation: UUID, turn: UUID) throws -> String {
        let images = conversationDirectory(conversation)
            .appendingPathComponent(Self.imagesDirectory, isDirectory: true)
        try FileManager.default.createDirectory(at: images, withIntermediateDirectories: true)
        let name = "\(turn.uuidString).png"
        try data.write(to: images.appendingPathComponent(name), options: .atomic)
        return "\(Self.imagesDirectory)/\(name)"
    }

    // MARK: - The index

    /// Rebuild `index.json` by reading every conversation directory.
    ///
    /// This is both the repair path and the write path -- the index is
    /// rewritten from the directories on every save, so it cannot drift from
    /// them by more than one failed write.
    @discardableResult
    private func rebuildIndex() throws -> [ConversationSummary] {
        let contents =
            (try? FileManager.default.contentsOfDirectory(
                at: directory, includingPropertiesForKeys: nil)) ?? []

        var summaries: [ConversationSummary] = []
        for url in contents {
            guard UUID(uuidString: url.lastPathComponent) != nil else { continue }
            let file = url.appendingPathComponent(Self.conversationFile)
            guard let data = try? Data(contentsOf: file),
                let conversation = try? Self.decoder.decode(Conversation.self, from: data)
            else { continue }
            summaries.append(conversation.summary)
        }
        summaries.sort(by: Self.newestFirst)

        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if let data = try? Self.encoder.encode(summaries) {
            try? data.write(to: indexURL, options: .atomic)
        }
        return summaries
    }
}
