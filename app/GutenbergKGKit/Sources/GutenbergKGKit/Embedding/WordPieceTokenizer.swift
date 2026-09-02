// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// BERT WordPiece, ported from tokenization_bert.py.
//
// This is the piece most likely to be silently wrong. The corpus vectors were
// produced by Python's BertTokenizer feeding bge-small; if this tokenizer
// splits one word differently, the query lands somewhere else in the embedding
// space and the app returns confident, plausible, wrong passages. Nothing
// crashes, so only the golden-query gate catches it — which is why every step
// below names the Python function it mirrors.

import Foundation

/// BERT WordPiece tokenizer for query text.
///
/// Lowercasing and accent stripping are properties of the checkpoint, read
/// from `embedder.json` rather than assumed, so a future uncased-to-cased swap
/// is a data change and not a code change.
public struct WordPieceTokenizer: Sendable {

    /// Token ids plus the mask, padded to the model's fixed input width.
    public struct Encoding: Sendable, Equatable {
        public let inputIDs: [Int32]
        public let attentionMask: [Int32]
    }

    /// Vocabulary and special tokens, as `embedder.json` describes them.
    public struct Configuration: Sendable {
        public var lowercase: Bool
        public var unknownID: Int32
        public var classificationID: Int32
        public var separatorID: Int32
        public var paddingID: Int32
        public var continuingPrefix: String
        /// Longer "words" than this become a single unknown token, as BERT does.
        public var maxCharactersPerWord: Int

        public init(
            lowercase: Bool = true,
            unknownID: Int32,
            classificationID: Int32,
            separatorID: Int32,
            paddingID: Int32,
            continuingPrefix: String = "##",
            maxCharactersPerWord: Int = 200
        ) {
            self.lowercase = lowercase
            self.unknownID = unknownID
            self.classificationID = classificationID
            self.separatorID = separatorID
            self.paddingID = paddingID
            self.continuingPrefix = continuingPrefix
            self.maxCharactersPerWord = maxCharactersPerWord
        }
    }

    private let vocabulary: [String: Int32]
    private let configuration: Configuration

    /// :param vocabulary: Token → id, in the order `vocab.txt` lists them.
    /// :param configuration: Special-token ids and casing behavior.
    public init(vocabulary: [String: Int32], configuration: Configuration) {
        self.vocabulary = vocabulary
        self.configuration = configuration
    }

    /// Build a tokenizer from a `vocab.txt` written by `gutenkg export-embedder`.
    ///
    /// :param url: The vocabulary file — one token per line, id = line number.
    /// :param configuration: Special-token ids and casing behavior.
    /// :throws: If the file cannot be read or holds no tokens.
    public init(vocabularyAt url: URL, configuration: Configuration) throws {
        let text = try String(contentsOf: url, encoding: .utf8)
        // Python builds this with `enumerate(reader.readlines())`, so a line's
        // position *is* its id and a later duplicate wins. The file ends with a
        // newline, which readlines() does not turn into a final empty token.
        var lines = text.components(separatedBy: "\n")
        if lines.last == "" { lines.removeLast() }
        var vocabulary: [String: Int32] = [:]
        for (index, line) in lines.enumerated() {
            vocabulary[line] = Int32(index)
        }
        guard vocabulary.count > 1 else {
            throw TokenizerError.emptyVocabulary(url)
        }
        self.init(vocabulary: vocabulary, configuration: configuration)
    }

    public enum TokenizerError: Error, LocalizedError {
        case emptyVocabulary(URL)

        public var errorDescription: String? {
            switch self {
            case .emptyVocabulary(let url):
                return "\(url.lastPathComponent) holds no tokens — re-run `gutenkg export-embedder`."
            }
        }
    }

    // MARK: - Encoding

    /// Tokenize `text` and pad to `maxLength`.
    ///
    /// The sequence is `[CLS] … [SEP]`, truncated to fit and then padded, which
    /// is what `padding="max_length", truncation=True` produces on the Python
    /// side — the exact call `export-embedder` traces the model with.
    ///
    /// :param text: Query text.
    /// :param maxLength: The model's fixed input width.
    /// :returns: Ids and mask, both exactly `maxLength` long.
    public func encode(_ text: String, maxLength: Int) -> Encoding {
        var ids = tokenIDs(for: text)
        // Two slots are spoken for by [CLS] and [SEP].
        if ids.count > maxLength - 2 { ids = Array(ids.prefix(maxLength - 2)) }

        var inputIDs: [Int32] = [configuration.classificationID]
        inputIDs.append(contentsOf: ids)
        inputIDs.append(configuration.separatorID)

        var mask = [Int32](repeating: 1, count: inputIDs.count)
        if inputIDs.count < maxLength {
            let padding = maxLength - inputIDs.count
            inputIDs.append(contentsOf: [Int32](repeating: configuration.paddingID, count: padding))
            mask.append(contentsOf: [Int32](repeating: 0, count: padding))
        }
        return Encoding(inputIDs: inputIDs, attentionMask: mask)
    }

    /// The WordPiece ids for `text`, without special tokens.
    ///
    /// :param text: Query text.
    /// :returns: Vocabulary ids in order.
    public func tokenIDs(for text: String) -> [Int32] {
        basicTokenize(text).flatMap(wordPiece(_:))
    }

    /// The WordPiece *tokens* for `text` — the readable form, for tests and
    /// for diagnosing a parity failure against Python.
    ///
    /// :param text: Query text.
    /// :returns: Tokens in order, `##` prefixes included.
    public func tokens(for text: String) -> [String] {
        let byID = Dictionary(uniqueKeysWithValues: vocabulary.map { ($0.value, $0.key) })
        return tokenIDs(for: text).compactMap { byID[$0] }
    }

    // MARK: - BasicTokenizer

    /// Clean, space out CJK, lowercase, strip accents, and split on whitespace
    /// and punctuation.
    ///
    /// Mirrors `BasicTokenizer.tokenize`, in that order — the CJK pass has to
    /// precede the whitespace split or its spaces do nothing.
    func basicTokenize(_ text: String) -> [String] {
        var cleaned = String.UnicodeScalarView()
        for scalar in text.unicodeScalars {
            if scalar.value == 0 || scalar.value == 0xFFFD || isControl(scalar) { continue }
            if isWhitespace(scalar) {
                cleaned.append(" ")
            } else if isChineseCharacter(scalar) {
                // `_tokenize_chinese_chars`: space out every CJK ideograph so
                // each becomes its own word. Without this, a run of them is one
                // "word" and WordPiece prefixes all but the first with `##` —
                // a different, wrong tokenization rather than an obvious break.
                cleaned.append(" ")
                cleaned.append(scalar)
                cleaned.append(" ")
            } else {
                cleaned.append(scalar)
            }
        }

        var prepared = String(cleaned)
        if configuration.lowercase {
            prepared = prepared.lowercased().decomposedStringWithCanonicalMapping
            prepared = String(String.UnicodeScalarView(
                prepared.unicodeScalars.filter { $0.properties.generalCategory != .nonspacingMark }
            ))
        }

        var output: [String] = []
        for word in prepared.split(separator: " ", omittingEmptySubsequences: true) {
            output.append(contentsOf: splitOnPunctuation(String(word)))
        }
        return output
    }

    /// Split a whitespace token so each punctuation character stands alone.
    ///
    /// Mirrors `BasicTokenizer._run_split_on_punc`, which is why "don't"
    /// becomes three tokens and a trailing "?" never fuses to the last word.
    private func splitOnPunctuation(_ word: String) -> [String] {
        var pieces: [String] = []
        var current = String.UnicodeScalarView()
        for scalar in word.unicodeScalars {
            if isPunctuation(scalar) {
                if !current.isEmpty {
                    pieces.append(String(current))
                    current = String.UnicodeScalarView()
                }
                pieces.append(String(scalar))
            } else {
                current.append(scalar)
            }
        }
        if !current.isEmpty { pieces.append(String(current)) }
        return pieces
    }

    // MARK: - WordpieceTokenizer

    /// Greedy longest-match-first subword split.
    ///
    /// Mirrors `WordpieceTokenizer.tokenize`: match the longest prefix in the
    /// vocabulary, prefix every later piece with `##`, and emit a single
    /// unknown token if any position fails to match at all — never a partial
    /// word, which is the subtle one.
    private func wordPiece(_ word: String) -> [Int32] {
        let characters = Array(word)
        guard characters.count <= configuration.maxCharactersPerWord else {
            return [configuration.unknownID]
        }

        var pieces: [Int32] = []
        var start = 0
        while start < characters.count {
            var end = characters.count
            var matched: Int32?
            while start < end {
                var candidate = String(characters[start..<end])
                if start > 0 { candidate = configuration.continuingPrefix + candidate }
                if let id = vocabulary[candidate] {
                    matched = id
                    break
                }
                end -= 1
            }
            guard let id = matched else { return [configuration.unknownID] }
            pieces.append(id)
            start = end
        }
        return pieces
    }

    // MARK: - Character classes (tokenization_bert.py's _is_* helpers)

    /// The ranges `_is_chinese_char` treats as CJK.
    ///
    /// Deliberately not all of "CJK" as Unicode blocks it: BERT excludes
    /// Hiragana, Katakana and Hangul, which are written with spaces between
    /// words and so tokenize correctly without help.
    private func isChineseCharacter(_ scalar: Unicode.Scalar) -> Bool {
        switch scalar.value {
        case 0x4E00...0x9FFF,  // CJK Unified Ideographs
            0x3400...0x4DBF,  // Extension A
            0x20000...0x2A6DF,  // Extension B
            0x2A700...0x2B73F,  // Extension C
            0x2B740...0x2B81F,  // Extension D
            0x2B820...0x2CEAF,  // Extension E
            0xF900...0xFAFF,  // Compatibility Ideographs
            0x2F800...0x2FA1F:  // Compatibility Supplement
            return true
        default:
            return false
        }
    }

    private func isWhitespace(_ scalar: Unicode.Scalar) -> Bool {
        if scalar == " " || scalar == "\t" || scalar == "\n" || scalar == "\r" { return true }
        return scalar.properties.generalCategory == .spaceSeparator
    }

    private func isControl(_ scalar: Unicode.Scalar) -> Bool {
        if scalar == "\t" || scalar == "\n" || scalar == "\r" { return false }
        switch scalar.properties.generalCategory {
        case .control, .format, .surrogate, .privateUse, .unassigned: return true
        default: return false
        }
    }

    private func isPunctuation(_ scalar: Unicode.Scalar) -> Bool {
        let value = scalar.value
        // BERT treats the ASCII symbol ranges as punctuation even though
        // Unicode files several of them under Symbol.
        if (33...47).contains(value) || (58...64).contains(value)
            || (91...96).contains(value) || (123...126).contains(value)
        {
            return true
        }
        switch scalar.properties.generalCategory {
        case .connectorPunctuation, .dashPunctuation, .openPunctuation, .closePunctuation,
            .initialPunctuation, .finalPunctuation, .otherPunctuation:
            return true
        default:
            return false
        }
    }
}
