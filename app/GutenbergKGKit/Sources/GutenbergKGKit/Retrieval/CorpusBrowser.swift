// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The Browse tab's four operations, behind one protocol so the reader does not
// know whether the book came off the network or off the disk.

import Foundation

/// Genres → books → chapters → chapter text.
///
/// The signatures are the worker's, so ``WorkerClient`` conforms with nothing
/// added and ``LocalBrowser`` has a shape to match rather than invent.
public protocol CorpusBrowser: Sendable {
    func listGenres() async throws -> [GenreCount]
    func listBooks(genre: String) async throws -> [Book]
    func chapters(genre: String, book: String) async throws -> [Chapter]
    func chapter(genre: String, book: String, sectionId: String) async throws -> ChapterContent
}

extension WorkerClient: CorpusBrowser {}

/// Browse served from the installed packs — works in airplane mode.
public struct LocalBrowser: CorpusBrowser {

    public enum BrowseError: Error, LocalizedError {
        case noCatalog
        case unknownBook(String)
        case unknownChapter(String)

        public var errorDescription: String? {
            switch self {
            case .noCatalog:
                return "This corpus has no core.pack, so its books cannot be listed."
            case .unknownBook(let book):
                return "\(book) is not in the installed corpus."
            case .unknownChapter(let id):
                return "That chapter is not in the installed corpus (\(id))."
            }
        }
    }

    private let packs: CorpusPacks

    public init(packs: CorpusPacks) {
        self.packs = packs
    }

    public func listGenres() async throws -> [GenreCount] {
        guard let catalog = packs.catalog else { throw BrowseError.noCatalog }
        return catalog.genres()
    }

    public func listBooks(genre: String) async throws -> [Book] {
        guard let catalog = packs.catalog else { throw BrowseError.noCatalog }
        return catalog.books(genre: genre)
    }

    public func chapters(genre: String, book: String) async throws -> [Chapter] {
        if genre == "diaries" { return try diaryChapters(book: book) }
        let (pack, path) = try locate(genre: genre, book: book)
        return try pack.chapters(filePath: path)
    }

    public func chapter(genre: String, book: String, sectionId: String) async throws
        -> ChapterContent
    {
        if genre == "diaries" {
            guard let content = try diaryChapter(book: book, sectionId: sectionId) else {
                throw BrowseError.unknownChapter(sectionId)
            }
            return content
        }
        let (pack, path) = try locate(genre: genre, book: book)
        guard let content = try pack.chapter(filePath: path, sectionID: sectionId) else {
            throw BrowseError.unknownChapter(sectionId)
        }
        return content
    }

    /// Resolve a book to the pack holding its passages and its document path.
    ///
    /// The catalog knows the path; which pack carries it is a lookup, because a
    /// diary's chapters live in `diaries.pack` and a book's in `gutenberg.pack`.
    private func locate(genre: String, book: String) throws -> (PassagePack, String) {
        guard let catalog = packs.catalog else { throw BrowseError.noCatalog }
        guard let path = catalog.documentPath(genre: genre, book: book) else {
            throw BrowseError.unknownBook("\(genre)/\(book)")
        }
        for pack in packs.packs where !((try? pack.chapters(filePath: path))?.isEmpty ?? true) {
            return (pack, path)
        }
        guard let first = packs.packs.first else { throw BrowseError.unknownBook(book) }
        return (first, path)
    }

    // MARK: - Diaries
    //
    // A diary has no `file_path` in `core.pack` (every chunk has its own) and
    // no `section` rows, so `locate(genre:book:)` cannot resolve one — this is
    // the gap `app/RUNBOOK.md` used to log as "diaries cannot be browsed".
    // `title` in `diaries.pack` matches the catalog's book name exactly, so it
    // stands in for the path lookup `locate` uses for everything else.

    private func diaryPack() -> PassagePack? {
        packs.packs.first { $0.isDiaries }
    }

    private func diaryChapters(book: String) throws -> [Chapter] {
        guard let pack = diaryPack(), let kgName = try pack.diaryIdentity(title: book) else {
            throw BrowseError.unknownBook("diaries/\(book)")
        }
        return try pack.diaryEntries(kgName: kgName)
    }

    private func diaryChapter(book: String, sectionId: String) throws -> ChapterContent? {
        guard let pack = diaryPack(), let kgName = try pack.diaryIdentity(title: book) else {
            throw BrowseError.unknownBook("diaries/\(book)")
        }
        return try pack.diaryEntry(kgName: kgName, timestamp: sectionId)
    }
}
