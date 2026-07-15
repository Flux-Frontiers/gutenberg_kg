// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0

import Foundation
import Testing

@testable import GutenbergKGKit

/// URLProtocol stub: captures the request and returns a canned response.
final class StubURLProtocol: URLProtocol {
    nonisolated(unsafe) static var lastRequestBody: Data?
    nonisolated(unsafe) static var lastRequestURL: URL?
    nonisolated(unsafe) static var responseBody: Data = Data()
    nonisolated(unsafe) static var responseStatus: Int = 200

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lastRequestURL = request.url
        // httpBody is transported as a stream by URLSession.
        if let stream = request.httpBodyStream {
            stream.open()
            var body = Data()
            let bufferSize = 4096
            let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
            defer { buffer.deallocate() }
            while stream.hasBytesAvailable {
                let read = stream.read(buffer, maxLength: bufferSize)
                if read <= 0 { break }
                body.append(buffer, count: read)
            }
            stream.close()
            Self.lastRequestBody = body
        } else {
            Self.lastRequestBody = request.httpBody
        }
        let response = HTTPURLResponse(
            url: request.url!, statusCode: Self.responseStatus,
            httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.responseBody)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private func makeClient(secret: String = "") -> WorkerClient {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [StubURLProtocol.self]
    return WorkerClient(
        baseURL: URL(string: "http://localhost:8000")!,
        secret: secret,
        session: URLSession(configuration: config))
}

private func sentInput() throws -> [String: Any] {
    let body = try #require(StubURLProtocol.lastRequestBody)
    let top = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
    return try #require(top["input"] as? [String: Any])
}

@Suite(.serialized) struct WorkerClientTests {
    @Test func queryPostsRunpodEnvelope() async throws {
        StubURLProtocol.responseStatus = 200
        StubURLProtocol.responseBody = Data(
            """
            {"output": {"query": "whale", "corpus": "all", "total_hits": 0,
              "kgs_queried": 1, "hits": [], "search_ms": 5,
              "synthesis": null, "synthesis_ms": null, "model": null}}
            """.utf8)

        let client = makeClient(secret: "hunter2")
        let result = try await client.query(
            "whale", corpus: "all", k: 12, minScore: 0.5,
            semanticFloor: 0.1, synthesize: true, backend: "omlx")

        #expect(result.query == "whale")
        #expect(StubURLProtocol.lastRequestURL?.path == "/runsync")

        let input = try sentInput()
        #expect(input["query"] as? String == "whale")
        #expect(input["k"] as? Int == 12)
        #expect(input["min_score"] as? Double == 0.5)
        #expect(input["semantic_floor"] as? Double == 0.1)
        #expect(input["synthesize"] as? Bool == true)
        #expect(input["backend"] as? String == "omlx")
        #expect(input["secret"] as? String == "hunter2")
        #expect(input["model"] == nil)  // empty model is omitted
    }

    @Test func statsRoundTrip() async throws {
        StubURLProtocol.responseStatus = 200
        StubURLProtocol.responseBody = Data(
            """
            {"output": {"books": 241, "genres": 20, "diaries": 4,
              "nodes": 10, "edges": 20, "embed_model": "BAAI/bge-small-en-v1.5"}}
            """.utf8)

        let stats = try await makeClient().stats()
        #expect(stats.books == 241)
        let input = try sentInput()
        #expect(input["op"] as? String == "stats")
        #expect(input["secret"] == nil)  // no secret configured → key omitted
    }

    @Test func applicationErrorSurfaces() async throws {
        StubURLProtocol.responseStatus = 200
        StubURLProtocol.responseBody = Data(#"{"output": {"error": "query is required"}}"#.utf8)

        await #expect(throws: WorkerError.application("query is required")) {
            _ = try await makeClient().query("")
        }
    }

    @Test func httpErrorSurfaces() async throws {
        StubURLProtocol.responseStatus = 500
        StubURLProtocol.responseBody = Data("{}".utf8)

        await #expect(throws: WorkerError.httpStatus(500)) {
            _ = try await makeClient().stats()
        }
    }

    @Test func rewriteFallsBackToOriginalText() async throws {
        StubURLProtocol.responseStatus = 200
        StubURLProtocol.responseBody = Data(#"{"output": {"prompt": null, "error": null}}"#.utf8)

        let prompt = try await makeClient().rewrite("original prose")
        #expect(prompt == "original prose")
    }
}
