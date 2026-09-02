// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The parts of the on-device query path that are pure logic, and where being
// wrong is silent: a tokenizer that splits one word differently sends the
// query to a different place in the embedding space, and the app returns
// fluent, ranked, wrong passages. Nothing throws.
//
// The end-to-end gate is the packs' golden.json; these are the unit-level
// checks that say *where* a divergence is.

import Foundation
import Testing

@testable import GutenbergKGKit

// MARK: - WordPiece

/// A miniature vocabulary in vocab.txt order — id is line number.
private let vocabularyTokens = [
    "[PAD]", "[UNK]", "[CLS]", "[SEP]",
    "un", "##aff", "##able", "want", "##want", "##ed", "wa", "ru", "##nn", "##ing",
    "don", "'", "t", "cafe", "the", "great", "fire", "of", "london", "?",
]

private func makeTokenizer() -> WordPieceTokenizer {
    var vocabulary: [String: Int32] = [:]
    for (index, token) in vocabularyTokens.enumerated() { vocabulary[token] = Int32(index) }
    return WordPieceTokenizer(
        vocabulary: vocabulary,
        configuration: .init(
            lowercase: true,
            unknownID: 1,
            classificationID: 2,
            separatorID: 3,
            paddingID: 0))
}

@Suite struct WordPieceTokenizerTests {

    @Test func greedyLongestMatchSplitsSubwords() {
        // The canonical BERT case: longest prefix first, `##` on the rest.
        #expect(makeTokenizer().tokens(for: "unaffable") == ["un", "##aff", "##able"])
    }

    @Test func punctuationBecomesItsOwnToken() {
        // _run_split_on_punc: "don't" is three tokens, and a trailing "?" never
        // fuses onto the word before it.
        #expect(makeTokenizer().tokens(for: "don't") == ["don", "'", "t"])
        #expect(makeTokenizer().tokens(for: "london?") == ["london", "?"])
    }

    @Test func lowercasesAndStripsAccents() {
        #expect(makeTokenizer().tokens(for: "Café") == ["cafe"])
        #expect(makeTokenizer().tokens(for: "CAFE") == ["cafe"])
    }

    @Test func anUnmatchableWordIsOneUnknownNotAPartialSplit() {
        // The subtle one: "wanted" splits, but a word whose *tail* is missing
        // from the vocabulary must not emit its matched prefix.
        #expect(makeTokenizer().tokens(for: "wanted") == ["want", "##ed"])
        #expect(makeTokenizer().tokens(for: "wantedx") == ["[UNK]"])
    }

    @Test func collapsesWhitespaceRuns() {
        let tokens = makeTokenizer().tokens(for: "  the   great\tfire\nof london ")
        #expect(tokens == ["the", "great", "fire", "of", "london"])
    }

    @Test func encodingIsWrappedAndPaddedToWidth() {
        let encoding = makeTokenizer().encode("the great fire", maxLength: 8)

        #expect(encoding.inputIDs.count == 8)
        #expect(encoding.attentionMask.count == 8)
        #expect(encoding.inputIDs.first == 2)  // [CLS]
        #expect(encoding.inputIDs[4] == 3)  // [SEP] after three content tokens
        #expect(Array(encoding.inputIDs.suffix(3)) == [0, 0, 0])  // [PAD]
        #expect(encoding.attentionMask == [1, 1, 1, 1, 1, 0, 0, 0])
    }

    @Test func encodingTruncatesToLeaveRoomForSpecialTokens() {
        let encoding = makeTokenizer().encode("the great fire of london", maxLength: 4)

        #expect(encoding.inputIDs.count == 4)
        #expect(encoding.inputIDs.first == 2)
        #expect(encoding.inputIDs.last == 3)
        #expect(encoding.attentionMask == [1, 1, 1, 1])
    }

    @Test func emptyQueryIsStillWellFormed() {
        let encoding = makeTokenizer().encode("   ", maxLength: 4)

        #expect(encoding.inputIDs == [2, 3, 0, 0])
        #expect(encoding.attentionMask == [1, 1, 0, 0])
    }
}

// MARK: - Fusion

@Suite struct FusionTests {

    @Test func matchesTheHandlersArithmetic() {
        // The same case tests/test_export_swift.py pins on the Python side.
        let fused = LocalRetrieval.fuse(
            dense: ["a", "b", "c"], lexical: ["c", "d"], k: 3, rrfK: 60)

        #expect(fused == ["c", "a", "b"])
    }

    @Test func aHitBothChannelsFindWinsOutright() {
        let fused = LocalRetrieval.fuse(
            dense: ["a", "b", "c"], lexical: ["c"], k: 1, rrfK: 60)

        #expect(fused == ["c"])
    }

    @Test func tiesKeepFirstSeenOrder() {
        // Python's stable sort over an insertion-ordered dict does the same,
        // and golden.json records that order.
        let fused = LocalRetrieval.fuse(dense: ["a"], lexical: ["b"], k: 2, rrfK: 60)

        #expect(fused == ["a", "b"])
    }

    @Test func lexicalOnlyResultsStillRank() {
        #expect(LocalRetrieval.fuse(dense: [], lexical: ["x", "y"], k: 2, rrfK: 60) == ["x", "y"])
    }
}

// MARK: - Scope

@Suite struct CorpusScopeTests {

    @Test func packSelectorsAreNotGenreFilters() {
        // "all", "gutenberg" and "diary" choose packs; anything else is a genre.
        #expect(LocalRetrieval.genreScope(for: "all") == nil)
        #expect(LocalRetrieval.genreScope(for: "gutenberg") == nil)
        #expect(LocalRetrieval.genreScope(for: "diary") == nil)
        #expect(LocalRetrieval.genreScope(for: "sacred-texts") == "sacred-texts")
    }
}

// MARK: - Selection

@Suite struct TopKTests {

    @Test func keepsTheBestKInOrder() {
        let scores: [Float] = [0.1, 0.9, 0.5, 0.7, 0.3]
        let rows: [Int32] = [10, 11, 12, 13, 14]
        let best = VectorIndex.topK(scores: scores, rows: rows, k: 3)

        #expect(best.map(\.row) == [11, 13, 12])
        #expect(best.map(\.similarity) == [0.9, 0.7, 0.5])
    }

    @Test func returnsEverythingWhenKExceedsTheInput() {
        let best = VectorIndex.topK(scores: [0.2, 0.4], rows: [0, 1], k: 10)

        #expect(best.count == 2)
        #expect(best.first?.row == 1)
    }

    @Test func handlesAnEmptyScan() {
        #expect(VectorIndex.topK(scores: [], rows: [], k: 5).isEmpty)
    }
}

// MARK: - FTS expression

@Suite struct MatchExpressionTests {

    @Test func quotesTermsSoPunctuationCannotBecomeSyntax() {
        // Mirrors export_swift.fts_match_expression — the packs' golden file
        // was generated with that exact construction.
        #expect(
            PassagePack.matchExpression(for: "What does the Quran say about Moses?")
                == "\"What\" OR \"does\" OR \"the\" OR \"Quran\" OR \"say\" OR \"about\" OR \"Moses\""
        )
    }

    @Test func purePunctuationYieldsNoExpression() {
        #expect(PassagePack.matchExpression(for: "!!! ???").isEmpty)
    }

    @Test func phraseKeepsTheTermsAdjacent() {
        // Mirrors export_swift.fts_phrase_expression. lexicalSearch runs this
        // first and only falls back to the OR above when it finds nothing —
        // the order GraphStore.search_lexical uses.
        #expect(PassagePack.phraseExpression(for: "pillar of salt") == "\"pillar of salt\"")
        #expect(PassagePack.phraseExpression(for: "Moses?") == "\"Moses\"")
        #expect(PassagePack.phraseExpression(for: "!!! ???").isEmpty)
    }
}
