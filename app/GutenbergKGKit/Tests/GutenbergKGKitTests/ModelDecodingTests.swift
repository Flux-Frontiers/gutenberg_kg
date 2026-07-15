// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Fixture JSON in these tests mirrors real worker responses
// (src/gutenberg_kg/serve/handler.py) — if the worker schema changes, these
// fixtures are the contract that must be updated in lockstep.

import Foundation
import Testing

@testable import GutenbergKGKit

private func decode<T: Decodable>(_ json: String) throws -> T {
    try WorkerClient.decodePayload(Data(json.utf8), decoder: JSONDecoder())
}

@Suite struct ModelDecodingTests {
    @Test func queryResultFullShape() throws {
        let json = """
        {"output": {
          "query": "pillar of salt",
          "corpus": "all",
          "total_hits": 2,
          "kgs_queried": 5,
          "search_ms": 142,
          "synthesis": "Lot's wife looked back…",
          "synthesis_ms": 2210,
          "model": "Qwen3-8B-MLX-4bit",
          "hits": [
            {"kg_name": "gutenberg-all", "kg_kind": "KGKind.doc",
             "node_id": "chunk:sacred-texts/kjv.md:412", "name": "Genesis 19",
             "kind": "chunk", "score": 0.7412,
             "summary": "…", "source_path": "sacred-texts/The Bible/kjv.md",
             "content": "But his wife looked back from behind him…",
             "timestamp": null,
             "genre": "sacred-texts", "title": "The King James Bible", "author": null},
            {"kg_name": "pepys", "kg_kind": "KGKind.diary",
             "node_id": "chunk:1666-09-02", "name": "September 2nd 1666",
             "kind": "chunk", "score": 0.61,
             "summary": null, "source_path": null,
             "content": "…", "timestamp": "1666-09-02T00:00:00",
             "genre": null, "title": null, "author": null}
          ]
        }}
        """
        let result: QueryResult = try decode(json)
        #expect(result.totalHits == 2)
        #expect(result.kgsQueried == 5)
        #expect(result.searchMs == 142)
        #expect(result.synthesis?.hasPrefix("Lot's wife") == true)
        #expect(result.synthesisError == nil)
        #expect(result.hits[0].nodeId == "chunk:sacred-texts/kjv.md:412")
        #expect(result.hits[0].score == 0.7412)
        #expect(result.hits[0].genre == "sacred-texts")
        #expect(result.hits[1].timestamp == "1666-09-02T00:00:00")
    }

    @Test func queryResultSynthesisOff() throws {
        let json = """
        {"output": {"query": "q", "corpus": "philosophy", "total_hits": 0,
          "kgs_queried": 1, "hits": [], "search_ms": 9,
          "synthesis": null, "synthesis_ms": null, "model": null}}
        """
        let result: QueryResult = try decode(json)
        #expect(result.hits.isEmpty)
        #expect(result.synthesis == nil)
        #expect(result.synthesisMs == nil)
    }

    @Test func corpusStats() throws {
        let json = """
        {"output": {"books": 241, "genres": 20, "diaries": 4,
          "nodes": 1270591, "edges": 5094446,
          "embed_model": "BAAI/bge-small-en-v1.5"}}
        """
        let stats: CorpusStats = try decode(json)
        #expect(stats.books == 241)
        #expect(stats.edges == 5_094_446)
        #expect(stats.embedModel == "BAAI/bge-small-en-v1.5")
    }

    @Test func genreList() throws {
        let json = """
        {"output": {"genres": [
          {"genre": "horror", "book_count": 16},
          {"genre": "philosophy", "book_count": 22}]}}
        """
        let list: GenreList = try decode(json)
        #expect(list.genres.count == 2)
        #expect(list.genres[0].genre == "horror")
        #expect(list.genres[0].bookCount == 16)
    }

    @Test func bookAndChapterShapes() throws {
        let books: BookList = try decode(
            """
            {"output": {"genre": "horror", "books": [
              {"book": "Frankenstein", "title": "Frankenstein",
               "author": "Mary Shelley", "ebook_id": 84}]}}
            """)
        #expect(books.books[0].ebookId == 84)

        let chapters: ChapterList = try decode(
            """
            {"output": {"book": "Frankenstein", "chapters": [
              {"id": "section:frankenstein.md:3", "title": "Chapter 1", "index": 0}]}}
            """)
        #expect(chapters.chapters[0].id == "section:frankenstein.md:3")

        let content: ChapterContent = try decode(
            """
            {"output": {"title": "Chapter 1", "text": "I am by birth a Genevese…",
              "index": 0, "total": 24, "prev_id": null,
              "next_id": "section:frankenstein.md:4"}}
            """)
        #expect(content.prevId == nil)
        #expect(content.nextId == "section:frankenstein.md:4")
    }

    @Test func modelListUsesDefaultKey() throws {
        let json = """
        {"output": {"models": ["Qwen3-8B-MLX-4bit", "llama3.1:8b"],
          "default": "Qwen3-8B-MLX-4bit"}}
        """
        let list: ModelList = try decode(json)
        #expect(list.models.count == 2)
        #expect(list.defaultModel == "Qwen3-8B-MLX-4bit")
    }

    @Test func envelopeUnwrapsBarePayload() throws {
        // Local serve mode may return the payload without the RunPod wrapper.
        let json = """
        {"books": 241, "genres": 20, "diaries": 4, "nodes": 1, "edges": 2,
         "embed_model": null}
        """
        let stats: CorpusStats = try decode(json)
        #expect(stats.books == 241)
        #expect(stats.embedModel == nil)
    }

    @Test func topLevelErrorThrows() {
        #expect(throws: WorkerError.application("boom")) {
            let _: CorpusStats = try decode(#"{"error": "boom"}"#)
        }
    }

    @Test func outputErrorThrows() {
        #expect(throws: WorkerError.application("unknown corpus 'x'")) {
            let _: QueryResult = try decode(#"{"output": {"error": "unknown corpus 'x'"}}"#)
        }
    }
}
