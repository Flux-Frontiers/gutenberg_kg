// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// `core.pack`: the catalog behind the scope picker, the sidebar caption, and
// the Browse tab's first two screens. Five megabytes, so it can be opened
// eagerly and queried without ceremony.

import Foundation
import SQLite3

/// Read-only access to `core.pack`.
public final class CatalogPack: @unchecked Sendable {

    private let database: SQLiteConnection

    /// :param url: Path to `core.pack`.
    /// :throws: When the file will not open.
    public init(contentsOf url: URL) throws {
        self.database = try SQLiteConnection(readOnly: url)
    }

    /// Every genre with its book count, sorted — the worker's `list_genres`.
    public func genres() -> [GenreCount] {
        var out: [GenreCount] = []
        database.tryEach("SELECT genre, book_count FROM genres ORDER BY genre") { statement in
            guard let genre = SQLiteConnection.string(statement, 0) else { return }
            out.append(
                GenreCount(genre: genre, bookCount: SQLiteConnection.integer(statement, 1) ?? 0))
        }
        return out
    }

    /// Books in one genre, title-sorted — the worker's `list_books`.
    ///
    /// :param genre: Genre slug.
    /// :returns: The genre's books.
    public func books(genre: String) -> [Book] {
        var out: [Book] = []
        database.tryEach(
            "SELECT book, title, author, ebook_id FROM books WHERE genre = ? ORDER BY title",
            text: [genre]
        ) { statement in
            out.append(
                Book(
                    book: SQLiteConnection.string(statement, 0) ?? "",
                    title: SQLiteConnection.string(statement, 1),
                    author: SQLiteConnection.string(statement, 2),
                    ebookId: SQLiteConnection.integer(statement, 3)))
        }
        return out
    }

    /// The document path a book's chapters hang off.
    ///
    /// This is the pack's answer to `handler._resolve_book_file_path`, resolved
    /// once at export time instead of by a prefix scan per request.
    ///
    /// :param genre: Genre slug.
    /// :param book: Book directory name.
    /// :returns: The book's document `file_path`, or nil if unknown.
    public func documentPath(genre: String, book: String) -> String? {
        var path: String?
        database.tryEach(
            "SELECT file_path FROM books WHERE genre = ? AND book = ? LIMIT 1",
            text: [genre, book]
        ) { statement in
            path = SQLiteConnection.string(statement, 0)
        }
        return path
    }

    /// Live corpus totals for the header caption — the worker's `stats` op.
    ///
    /// :param embedModel: The embedder named by the manifest, so the caption
    ///     reports what actually built these vectors.
    /// :returns: The totals, or nil when the pack carries none.
    public func stats(embedModel: String) -> CorpusStats? {
        var stats: CorpusStats?
        database.tryEach("SELECT books, genres, diaries, nodes, edges FROM corpus_stats LIMIT 1") {
            statement in
            stats = CorpusStats(
                books: SQLiteConnection.integer(statement, 0) ?? 0,
                genres: SQLiteConnection.integer(statement, 1) ?? 0,
                diaries: SQLiteConnection.integer(statement, 2) ?? 0,
                nodes: SQLiteConnection.integer(statement, 3) ?? 0,
                edges: SQLiteConnection.integer(statement, 4) ?? 0,
                embedModel: embedModel)
        }
        return stats
    }
}
