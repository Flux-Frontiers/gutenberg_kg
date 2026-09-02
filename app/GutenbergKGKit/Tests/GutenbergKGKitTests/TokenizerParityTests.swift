// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The tokenizer, pinned against Python.
//
// `WordPieceTokenizer` is a port of `tokenization_bert.py`, and the corpus
// vectors were produced by the original. If the two split one word
// differently, the query lands elsewhere in the embedding space and the app
// returns fluent, ranked, wrong passages — with nothing thrown and nothing
// logged. The unit tests above check the algorithm's shape against a toy
// vocabulary; this checks its output against the real one.
//
// `Fixtures/vocab.txt` is bge-small-en-v1.5's actual 30,522-token vocabulary
// and `Fixtures/tokenizer_fixture.json` is what Python's BertTokenizer makes
// of 36 inputs: the twelve golden queries, plus the shapes that break a
// hand-written WordPiece — contractions, accents, punctuation runs, em dashes,
// digits, an over-long word, control characters, CJK, and a string long enough
// to truncate. Regenerate both with `scripts/make_tokenizer_fixture.py`.

import Foundation
import Testing

@testable import GutenbergKGKit

private struct ParityFixture: Decodable {
    struct Case: Decodable {
        let text: String
        let tokens: [String]
        let ids: [Int32]
        let encoded: [Int32]
        let mask: [Int32]
    }

    let model: String
    let maxLength: Int
    let lowercase: Bool
    let unk: Int32
    let cls: Int32
    let sep: Int32
    let pad: Int32
    let cases: [Case]

    enum CodingKeys: String, CodingKey {
        case model, lowercase, unk, cls, sep, pad, cases
        case maxLength = "max_length"
    }
}

@Suite struct TokenizerParityTests {

    private static func load() throws -> (WordPieceTokenizer, ParityFixture) {
        let fixtureURL = try #require(
            Bundle.module.url(
                forResource: "tokenizer_fixture", withExtension: "json", subdirectory: "Fixtures"))
        let vocabURL = try #require(
            Bundle.module.url(forResource: "vocab", withExtension: "txt", subdirectory: "Fixtures"))

        let fixture = try JSONDecoder().decode(
            ParityFixture.self, from: Data(contentsOf: fixtureURL))
        let tokenizer = try WordPieceTokenizer(
            vocabularyAt: vocabURL,
            configuration: .init(
                lowercase: fixture.lowercase,
                unknownID: fixture.unk,
                classificationID: fixture.cls,
                separatorID: fixture.sep,
                paddingID: fixture.pad))
        return (tokenizer, fixture)
    }

    @Test func theFixtureDescribesTheModelTheCorpusWasBuiltWith() throws {
        let (_, fixture) = try Self.load()

        #expect(fixture.model == "BAAI/bge-small-en-v1.5")
        #expect(fixture.cases.count == 36)
        // The values embedder.json carries, and the app trusts.
        #expect((fixture.cls, fixture.sep, fixture.pad, fixture.unk) == (101, 102, 0, 100))
    }

    @Test func everyInputTokenizesExactlyAsPythonDoes() throws {
        let (tokenizer, fixture) = try Self.load()

        var divergences: [String] = []
        for testCase in fixture.cases {
            let tokens = tokenizer.tokens(for: testCase.text)
            if tokens != testCase.tokens {
                divergences.append(
                    "\(Self.show(testCase.text))\n    want \(testCase.tokens)\n    got  \(tokens)")
            }
        }

        // Report all of them: one divergence is a character class, and thirty-six
        // is the whole pipeline. Failing at the first hides which.
        let report = divergences.joined(separator: "\n")
        #expect(
            divergences.isEmpty,
            "\(divergences.count) of \(fixture.cases.count) diverge:\n\(report)")
    }

    @Test func idsMatchTheVocabularysOwnNumbering() throws {
        let (tokenizer, fixture) = try Self.load()

        for testCase in fixture.cases {
            #expect(
                tokenizer.tokenIDs(for: testCase.text) == testCase.ids,
                "ids differ for \(Self.show(testCase.text))")
        }
    }

    @Test func encodingMatchesPaddingAndTruncationAsTheModelWasTraced() throws {
        let (tokenizer, fixture) = try Self.load()

        for testCase in fixture.cases {
            let encoding = tokenizer.encode(testCase.text, maxLength: fixture.maxLength)
            #expect(
                encoding.inputIDs == testCase.encoded,
                "input_ids differ for \(Self.show(testCase.text))")
            #expect(
                encoding.attentionMask == testCase.mask,
                "attention_mask differs for \(Self.show(testCase.text))")
            #expect(encoding.inputIDs.count == fixture.maxLength)
        }
    }

    @Test func cjkIdeographsAreSpacedOutIntoSeparateWords() throws {
        // The regression this file was written for. Without
        // `_tokenize_chinese_chars`, a run of ideographs is one "word" and
        // WordPiece prefixes all but the first with `##` — a plausible-looking
        // tokenization that is simply not the one the corpus was built with.
        let (tokenizer, _) = try Self.load()

        let tokens = tokenizer.tokens(for: "Zhōngwén 中文")

        #expect(tokens.suffix(2) == ["中", "文"])
        #expect(!tokens.contains("##文"))
    }

    private static func show(_ text: String) -> String {
        let escaped =
            text
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\t", with: "\\t")
            .replacingOccurrences(of: "\u{0}", with: "\\0")
        return escaped.count > 48 ? String(escaped.prefix(45)) + "…" : escaped
    }
}
