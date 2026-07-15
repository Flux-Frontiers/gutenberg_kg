// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Codable mirrors of the GutenbergKG worker's JSON payloads.
// Source of truth: src/gutenberg_kg/serve/handler.py (request/response schema
// in the module docstring; hit shape in _rows_to_hits + _enrich_catalog).

import Foundation

/// One retrieved passage, as shaped by the worker's `_rows_to_hits` and
/// enriched with catalog metadata (`genre`/`title`/`author`).
public struct Hit: Codable, Sendable, Identifiable, Hashable {
    public let kgName: String
    public let kgKind: String
    public let nodeId: String
    public let name: String
    public let kind: String
    public let score: Double
    public let summary: String?
    public let sourcePath: String?
    public let content: String?
    /// ISO-8601 timestamp for diary hits; nil for prose.
    public let timestamp: String?
    public let genre: String?
    public let title: String?
    public let author: String?

    public var id: String { nodeId }

    enum CodingKeys: String, CodingKey {
        case kgName = "kg_name"
        case kgKind = "kg_kind"
        case nodeId = "node_id"
        case name, kind, score, summary
        case sourcePath = "source_path"
        case content, timestamp, genre, title, author
    }
}

/// Full response to a corpus query (the worker's main op).
public struct QueryResult: Codable, Sendable {
    public let query: String
    public let corpus: String
    public let totalHits: Int
    public let kgsQueried: Int
    public let hits: [Hit]
    public let searchMs: Int?
    public let synthesis: String?
    public let synthesisMs: Int?
    public let synthesisError: String?
    public let model: String?

    enum CodingKeys: String, CodingKey {
        case query, corpus
        case totalHits = "total_hits"
        case kgsQueried = "kgs_queried"
        case hits
        case searchMs = "search_ms"
        case synthesis
        case synthesisMs = "synthesis_ms"
        case synthesisError = "synthesis_error"
        case model
    }
}

/// Live corpus totals (`op: "stats"`) — drives the sidebar header, no
/// hardcoded counts.
public struct CorpusStats: Codable, Sendable {
    public let books: Int
    public let genres: Int
    public let diaries: Int
    public let nodes: Int
    public let edges: Int
    public let embedModel: String?

    enum CodingKeys: String, CodingKey {
        case books, genres, diaries, nodes, edges
        case embedModel = "embed_model"
    }
}

/// One genre with its book count (`op: "list_genres"`).
public struct GenreCount: Codable, Sendable, Identifiable, Hashable {
    public let genre: String
    public let bookCount: Int

    public var id: String { genre }

    enum CodingKeys: String, CodingKey {
        case genre
        case bookCount = "book_count"
    }
}

struct GenreList: Codable {
    let genres: [GenreCount]
}

/// One book in a genre (`op: "list_books"`).
public struct Book: Codable, Sendable, Identifiable, Hashable {
    /// Directory name — the key used by `get_chapters`/`get_chapter`.
    public let book: String
    public let title: String?
    public let author: String?
    public let ebookId: Int?

    public var id: String { book }

    enum CodingKeys: String, CodingKey {
        case book, title, author
        case ebookId = "ebook_id"
    }
}

struct BookList: Codable {
    let genre: String
    let books: [Book]
}

/// One chapter entry (`op: "get_chapters"`).
public struct Chapter: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let title: String?
    public let index: Int?
}

struct ChapterList: Codable {
    let book: String?
    let chapters: [Chapter]
}

/// Reconstructed chapter text (`op: "get_chapter"`).
public struct ChapterContent: Codable, Sendable {
    public let title: String?
    public let text: String
    public let index: Int?
    public let total: Int?
    public let prevId: String?
    public let nextId: String?

    enum CodingKeys: String, CodingKey {
        case title, text, index, total
        case prevId = "prev_id"
        case nextId = "next_id"
    }
}

/// Synthesis model inventory (`op: "models"`).
public struct ModelList: Codable, Sendable {
    public let models: [String]
    public let defaultModel: String?

    enum CodingKeys: String, CodingKey {
        case models
        case defaultModel = "default"
    }
}

/// Result of `op: "imagine"` — a base64 PNG plus provenance labels.
public struct GeneratedImage: Codable, Sendable {
    public let imageB64: String
    public let imageModel: String?
    public let imageBackend: String?

    enum CodingKeys: String, CodingKey {
        case imageB64 = "image_b64"
        case imageModel = "image_model"
        case imageBackend = "image_backend"
    }
}

struct RewriteResult: Codable {
    let prompt: String?
    let error: String?
}
