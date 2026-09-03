// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Read side of the corpus packs: the lexical channel, passage hydration, and
// the Browse queries. Plain SQLite through the system library — the packs
// carry no virtual table beyond FTS5, which iOS ships, so there is nothing to
// link and nothing to vendor.

import Foundation
import SQLite3

/// Read-only access to one passage pack (`gutenberg.pack`, `diaries.pack`).
public final class PassagePack: @unchecked Sendable {

    private let database: SQLiteConnection

    /// The vector sidecar beside this pack, when it has one.
    public let vectors: VectorIndex?

    /// The pack's own name, from its `pack_meta` — "gutenberg" or "diaries".
    /// Read from the file rather than inferred from the filename, so a renamed
    /// or re-downloaded pack still knows what it is.
    public let name: String

    /// Whether this pack holds the diaries. The corpus scope switch turns on
    /// this and nothing else.
    public var isDiaries: Bool { name == "diaries" }

    /// Open a pack and map its vectors.
    ///
    /// :param url: Path to a `.pack` file.
    /// :param expectedDimension: The embedder's output width, checked against
    ///     the sidecar's header.
    /// :throws: When the pack will not open, or its sidecar does not match.
    public init(contentsOf url: URL, expectedDimension: Int) throws {
        let database = try SQLiteConnection(readOnly: url)

        var name = url.deletingPathExtension().lastPathComponent
        database.tryEach("SELECT value FROM pack_meta WHERE key = 'pack'") { statement in
            if let value = SQLiteConnection.string(statement, 0) { name = value }
        }

        let sidecar = url.deletingPathExtension().appendingPathExtension("vectors")
        let vectors =
            FileManager.default.fileExists(atPath: sidecar.path)
            ? try VectorIndex(contentsOf: sidecar, expectedDimension: expectedDimension)
            : nil

        self.database = database
        self.name = name
        self.vectors = vectors
    }

    // MARK: - Retrieval

    /// Vector rows eligible for a scoped search, or nil when nothing is excluded.
    ///
    /// Returning nil for an unscoped query matters: the packs hold only
    /// searchable passages, so "all" excludes nothing and the dense scan can
    /// skip a 364 K-row round trip through SQLite.
    ///
    /// :param genre: Genre slug, or nil for the whole pack.
    /// :returns: Row indices into the sidecar, or nil to mean "everything".
    public func eligibleVectorRows(genre: String?) throws -> [Int32]? {
        guard let genre else { return nil }
        var rows: [Int32] = []
        try each(
            "SELECT vector_index FROM passages WHERE vector_index IS NOT NULL AND genre = ?",
            bind: [genre]
        ) { statement in
            rows.append(Int32(sqlite3_column_int64(statement, 0)))
        }
        return rows
    }

    /// BM25-ranked passage ids for a query.
    ///
    /// The MATCH expression quotes each term and ORs them, so an apostrophe or
    /// a question mark in the query cannot become FTS5 syntax and a query is
    /// never rejected wholesale for one odd character. It mirrors
    /// `export_swift.fts_match_expression` exactly — the packs' golden file was
    /// generated with it.
    ///
    /// :param query: Raw query text.
    /// :param limit: Maximum ids to return.
    /// :param genre: Genre slug, or nil.
    /// :returns: Passage ids, best-first by BM25.
    public func lexicalSearch(_ query: String, limit: Int, genre: String?) throws -> [String] {
        // Phrase first, then any-term for recall. A rare phrase diluted in a
        // long chunk is exactly what the dense channel buries, so a literal
        // match deserves to seed the fusion; the OR form keeps a query with no
        // adjacent match from returning nothing at all.
        let phrase = try search(expression: Self.phraseExpression(for: query), limit: limit, genre: genre)
        guard phrase.isEmpty else { return phrase }
        return try search(expression: Self.matchExpression(for: query), limit: limit, genre: genre)
    }

    /// One BM25 pass for an already-built FTS5 expression.
    ///
    /// :param expression: An FTS5 MATCH expression; "" returns no rows.
    /// :param limit: Maximum ids to return.
    /// :param genre: Genre slug, or nil.
    /// :returns: Passage ids, best-first by BM25.
    private func search(expression: String, limit: Int, genre: String?) throws -> [String] {
        guard !expression.isEmpty else { return [] }

        var sql = """
            SELECT p.id FROM passages_fts f JOIN passages p ON p.rowid = f.rowid
             WHERE passages_fts MATCH ?
            """
        var bindings: [String] = [expression]
        if let genre {
            sql += " AND p.genre = ?"
            bindings.append(genre)
        }
        sql += " ORDER BY bm25(passages_fts) LIMIT \(max(1, limit))"

        var ids: [String] = []
        try each(sql, bind: bindings) { statement in
            if let text = sqlite3_column_text(statement, 0) {
                ids.append(String(cString: text))
            }
        }
        return ids
    }

    /// Bare alphanumeric terms, so no character of the query can become FTS5
    /// syntax. `export_swift.fts_terms` does the same split.
    ///
    /// :param query: Raw query text.
    /// :returns: The searchable terms, in order.
    static func terms(in query: String) -> [String] {
        let cleaned = String(query.map { $0.isLetter || $0.isNumber ? $0 : " " })
        return cleaned.split(separator: " ").map(String.init)
    }

    /// FTS5 exact-phrase expression: every term, adjacent and in order.
    ///
    /// :param query: Raw query text.
    /// :returns: A quoted phrase, or "" when nothing is searchable.
    static func phraseExpression(for query: String) -> String {
        let found = terms(in: query)
        return found.isEmpty ? "" : "\"" + found.joined(separator: " ") + "\""
    }

    /// FTS5 any-term expression — the recall fallback behind the phrase.
    ///
    /// :param query: Raw query text.
    /// :returns: A quoted OR-expression, or "" when nothing is searchable.
    static func matchExpression(for query: String) -> String {
        terms(in: query).map { "\"\($0)\"" }.joined(separator: " OR ")
    }

    /// Load full passages by id, keyed for the caller to order as it likes.
    ///
    /// :param ids: Passage ids.
    /// :returns: Row data by id; ids not in this pack are simply absent.
    public func passages(ids: [String]) throws -> [String: PassageRow] {
        guard !ids.isEmpty else { return [:] }
        let placeholders = Array(repeating: "?", count: ids.count).joined(separator: ", ")
        var rows: [String: PassageRow] = [:]
        try each(
            """
            SELECT id, kg_name, kg_kind, kind, name, title, node_title, author, genre,
                   file_path, timestamp, vector_index, content
              FROM passages WHERE id IN (\(placeholders))
            """,
            bind: ids
        ) { statement in
            let row = PassageRow(
                id: Self.text(statement, 0) ?? "",
                kgName: Self.text(statement, 1) ?? "",
                kgKind: Self.text(statement, 2) ?? "",
                kind: Self.text(statement, 3) ?? "chunk",
                name: Self.text(statement, 4),
                title: Self.text(statement, 5),
                nodeTitle: Self.text(statement, 6),
                author: Self.text(statement, 7),
                genre: Self.text(statement, 8),
                filePath: Self.text(statement, 9),
                timestamp: Self.text(statement, 10),
                vectorRow: sqlite3_column_type(statement, 11) == SQLITE_NULL
                    ? nil : Int(sqlite3_column_int64(statement, 11)),
                content: Self.text(statement, 12) ?? "")
            rows[row.id] = row
        }
        return rows
    }

    /// Passage ids for a set of sidecar rows, so a dense result can be named.
    ///
    /// :param rows: Sidecar row indices.
    /// :returns: Passage id per row index.
    public func ids(forVectorRows rows: [Int]) throws -> [Int: String] {
        guard !rows.isEmpty else { return [:] }
        let placeholders = Array(repeating: "?", count: rows.count).joined(separator: ", ")
        var out: [Int: String] = [:]
        try each(
            "SELECT vector_index, id FROM passages WHERE vector_index IN (\(placeholders))",
            ints: rows.map(Int64.init)
        ) { statement in
            if let text = sqlite3_column_text(statement, 1) {
                out[Int(sqlite3_column_int64(statement, 0))] = String(cString: text)
            }
        }
        return out
    }

    // MARK: - Browse

    /// A book's chapters, in reading order.
    ///
    /// Section nodes are the chapter markers; a verse-chunked book that has
    /// none falls back to grouping chunks by their `chapter` column, exactly
    /// as `handler._get_chapters` does.
    ///
    /// :param filePath: The book's document path, from `core.pack`.
    /// :returns: Chapters in order.
    public func chapters(filePath: String) throws -> [Chapter] {
        var chapters: [Chapter] = []
        try each(
            """
            SELECT id, COALESCE(node_title, name) FROM passages
             WHERE file_path = ? AND kind = 'section' ORDER BY char_start
            """,
            bind: [filePath]
        ) { statement in
            chapters.append(
                Chapter(
                    id: Self.text(statement, 0) ?? "",
                    title: Self.text(statement, 1),
                    index: chapters.count))
        }
        if !chapters.isEmpty { return chapters }

        try each(
            """
            SELECT DISTINCT chapter FROM passages
             WHERE file_path = ? AND kind = 'chunk' AND chapter IS NOT NULL
             ORDER BY chapter
            """,
            bind: [filePath]
        ) { statement in
            let number = sqlite3_column_int64(statement, 0)
            chapters.append(
                Chapter(id: "chapter:\(number)", title: "Chapter \(number)", index: chapters.count))
        }
        return chapters
    }

    /// One chapter's text, rebuilt from the chunks it spans.
    ///
    /// :param filePath: The book's document path.
    /// :param sectionID: A chapter id from ``chapters(filePath:)``.
    /// :returns: The chapter, or nil when the id is unknown here.
    public func chapter(filePath: String, sectionID: String) throws -> ChapterContent? {
        let all = try chapters(filePath: filePath)
        guard let index = all.firstIndex(where: { $0.id == sectionID }) else { return nil }
        let previous = index > 0 ? all[index - 1].id : nil
        let next = index + 1 < all.count ? all[index + 1].id : nil

        var text = ""
        if sectionID.hasPrefix("chapter:") {
            let number = Int(sectionID.dropFirst("chapter:".count)) ?? -1
            try each(
                """
                SELECT content FROM passages
                 WHERE file_path = ? AND kind = 'chunk' AND chapter = ?
                 ORDER BY char_start
                """,
                bind: [filePath], ints: [Int64(number)]
            ) { statement in
                text += (text.isEmpty ? "" : "\n\n") + (Self.text(statement, 0) ?? "")
            }
        } else {
            // Chunks between this section marker and the next one.
            let start = try sectionStart(filePath: filePath, sectionID: sectionID) ?? 0
            var end: Int?
            if let next, let boundary = try? sectionStart(filePath: filePath, sectionID: next) {
                end = boundary
            }
            var sql = """
                SELECT content FROM passages
                 WHERE file_path = ? AND kind = 'chunk' AND char_start >= ?
                """
            var bounds: [Int64] = [Int64(start)]
            if let end {
                sql += " AND char_start < ?"
                bounds.append(Int64(end))
            }
            sql += " ORDER BY char_start"
            try each(sql, bind: [filePath], ints: bounds) { statement in
                text += (text.isEmpty ? "" : "\n\n") + (Self.text(statement, 0) ?? "")
            }
        }

        return ChapterContent(
            title: all[index].title,
            text: text,
            index: index,
            total: all.count,
            prevId: previous,
            nextId: next)
    }

    // MARK: - Diary entries

    /// The diary identity (`kg_name`) behind a catalog title.
    ///
    /// Diaries carry no `file_path` in `core.pack` — every chunk of a diary
    /// has its own per-entry `file_path` (`entry_0144_chunk_8.md`), so there
    /// is no single document path to hang chapters off the way a book has.
    /// `kg_name` is the shared identity instead, and `title` is the one column
    /// that already matches the catalog's book name exactly.
    ///
    /// :param title: The catalog's book title for this diary.
    /// :returns: The `kg_name` this pack knows it by, or nil if this pack does
    ///     not hold a diary by that title (e.g. it is `gutenberg.pack`).
    public func diaryIdentity(title: String) throws -> String? {
        var kgName: String?
        try each(
            "SELECT kg_name FROM passages WHERE title = ? AND kg_name IS NOT NULL LIMIT 1",
            bind: [title]
        ) { statement in
            kgName = Self.text(statement, 0)
        }
        return kgName
    }

    /// One diary's dated entries, earliest first.
    ///
    /// A diary has no `section` rows, so there is no chapter marker to read —
    /// the entry boundary is a change of `timestamp`. `Chapter.id` carries the
    /// raw timestamp, so ``diaryEntry(kgName:timestamp:)`` can look chunks back
    /// up by it; `Chapter.title` is the same date, formatted for reading.
    ///
    /// :param kgName: The diary's identity in this pack.
    /// :returns: One chapter per dated entry.
    public func diaryEntries(kgName: String) throws -> [Chapter] {
        var chapters: [Chapter] = []
        try each(
            """
            SELECT DISTINCT timestamp FROM passages
             WHERE kg_name = ? AND timestamp IS NOT NULL
             ORDER BY timestamp
            """,
            bind: [kgName]
        ) { statement in
            guard let timestamp = Self.text(statement, 0) else { return }
            chapters.append(
                Chapter(
                    id: timestamp, title: Self.formatDiaryDate(timestamp), index: chapters.count))
        }
        return chapters
    }

    /// One dated entry's text, rebuilt from the chunks it spans.
    ///
    /// A day's chunks are not necessarily one contiguous `file_path` — an
    /// entry can straddle more than one `entry_NNNN_chunk_M.md` file — so they
    /// are ordered by `file_path` first and `char_start` second, matching the
    /// order they were chunked in rather than a lexical accident.
    ///
    /// :param kgName: The diary's identity in this pack.
    /// :param timestamp: An entry id from ``diaryEntries(kgName:)``.
    /// :returns: The entry, or nil when the timestamp is unknown here.
    public func diaryEntry(kgName: String, timestamp: String) throws -> ChapterContent? {
        let all = try diaryEntries(kgName: kgName)
        guard let index = all.firstIndex(where: { $0.id == timestamp }) else { return nil }
        let previous = index > 0 ? all[index - 1].id : nil
        let next = index + 1 < all.count ? all[index + 1].id : nil

        var text = ""
        try each(
            """
            SELECT content FROM passages
             WHERE kg_name = ? AND timestamp = ?
             ORDER BY file_path, char_start
            """,
            bind: [kgName, timestamp]
        ) { statement in
            text += (text.isEmpty ? "" : "\n\n") + (Self.text(statement, 0) ?? "")
        }
        guard !text.isEmpty else { return nil }

        return ChapterContent(
            title: all[index].title,
            text: text,
            index: index,
            total: all.count,
            prevId: previous,
            nextId: next)
    }

    /// A diary timestamp (`"1645-02-15T00:00"`) as a reading date.
    ///
    /// The stored value is not full ISO 8601 — no seconds, no timezone — so a
    /// generic parser is the wrong tool; the shape is fixed by the pipeline
    /// that wrote it, and this parses exactly that shape.
    ///
    /// :param timestamp: The raw value from the `timestamp` column.
    /// :returns: A long-form date, or the raw value if it does not parse.
    static func formatDiaryDate(_ timestamp: String) -> String {
        let parser = DateFormatter()
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.dateFormat = "yyyy-MM-dd'T'HH:mm"
        guard let date = parser.date(from: timestamp) else { return timestamp }
        return date.formatted(.dateTime.day().month(.wide).year())
    }

    private func sectionStart(filePath: String, sectionID: String) throws -> Int? {
        var start: Int?
        try each(
            "SELECT char_start FROM passages WHERE id = ? AND file_path = ?",
            bind: [sectionID, filePath]
        ) { statement in
            if sqlite3_column_type(statement, 0) != SQLITE_NULL {
                start = Int(sqlite3_column_int64(statement, 0))
            }
        }
        return start
    }

    // MARK: - SQLite plumbing

    /// Run `sql` and hand each row to `body`.
    ///
    /// Serialised on a lock: the pack is opened `NOMUTEX` for speed, so this
    /// type owns the exclusion rather than paying SQLite's per-call mutex.
    private func each(
        _ sql: String,
        bind text: [String] = [],
        ints: [Int64] = [],
        _ body: (OpaquePointer) -> Void
    ) throws {
        try database.each(sql, text: text, ints: ints, body)
    }

    private static func text(_ statement: OpaquePointer, _ column: Int32) -> String? {
        SQLiteConnection.string(statement, column)
    }
}

/// One packed passage, before it becomes a ``Hit``.
public struct PassageRow: Sendable {
    public let id: String
    public let kgName: String
    public let kgKind: String
    public let kind: String
    public let name: String?
    public let title: String?
    public let nodeTitle: String?
    public let author: String?
    public let genre: String?
    public let filePath: String?
    public let timestamp: String?
    public let vectorRow: Int?
    public let content: String

    /// Shape this row as the worker would, so a hit card cannot tell the
    /// difference between a local answer and a remote one.
    ///
    /// :param score: The fused cosine score for this passage.
    /// :returns: A ``Hit`` in the worker's schema.
    public func hit(score: Double) -> Hit {
        Hit(
            kgName: kgName,
            kgKind: kgKind,
            nodeId: id,
            name: name ?? title ?? "",
            kind: kind,
            score: score,
            summary: content,
            sourcePath: filePath,
            content: content,
            timestamp: timestamp,
            genre: genre,
            title: title,
            author: author)
    }
}
