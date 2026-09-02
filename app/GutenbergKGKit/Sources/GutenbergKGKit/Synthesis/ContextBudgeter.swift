// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Fits retrieval hits into a small context window.
//
// The worker feeds up to SYNTH_MAX_K=12 passages to a server-class model.
// Apple's on-device model has a ~4,096-token window shared by instructions,
// passages, question and the response, so the passages have to be both fewer
// and shorter.  This type makes that trade explicit and testable: retrieval
// still returns the full k for the hit cards, and only synthesis sees the
// packed subset.

import Foundation

/// Greedy best-first passage packer for a fixed context window.
public struct ContextBudgeter: Sendable {

    /// Tunable limits. The defaults target Apple's on-device model; a larger
    /// remote model can raise `contextWindow` and `maxPassages` to match the
    /// worker's `SYNTH_MAX_K`.
    public struct Budget: Sendable, Equatable {
        /// Total tokens the model will accept for prompt + response.
        public var contextWindow: Int
        /// Tokens held back so the answer itself has room.
        public var reservedForResponse: Int
        /// Tokens charged to the instructions block and prompt scaffolding.
        public var reservedForOverhead: Int
        /// Hard cap on passages regardless of remaining budget.
        public var maxPassages: Int
        /// Characters kept from each passage before trimming at a word break.
        public var maxCharactersPerPassage: Int
        /// A passage trimmed below this is dropped instead — a 40-character
        /// fragment costs budget without carrying an answer.
        public var minCharactersPerPassage: Int

        public init(
            contextWindow: Int = 4096,
            reservedForResponse: Int = 512,
            reservedForOverhead: Int = 240,
            maxPassages: Int = 5,
            maxCharactersPerPassage: Int = 500,
            minCharactersPerPassage: Int = 120
        ) {
            self.contextWindow = contextWindow
            self.reservedForResponse = reservedForResponse
            self.reservedForOverhead = reservedForOverhead
            self.maxPassages = maxPassages
            self.maxCharactersPerPassage = maxCharactersPerPassage
            self.minCharactersPerPassage = minCharactersPerPassage
        }

        /// Tokens actually available to passage text.
        public var passageAllowance: Int {
            max(0, contextWindow - reservedForResponse - reservedForOverhead)
        }

        /// The on-device default.
        public static let onDevice = Budget()

        /// Parity with the worker's server-class synthesis.
        public static let worker = Budget(
            contextWindow: 32_768,
            reservedForResponse: 1_024,
            reservedForOverhead: 240,
            maxPassages: 12,
            maxCharactersPerPassage: 2_000)
    }

    /// One passage as the model will see it.
    public struct Passage: Sendable, Equatable, Identifiable {
        /// The hit's node id — carried through so a cited passage can be
        /// traced back to its card.
        public let id: String
        /// `genre · author · title`, the bracketed header from
        /// `synthesize_rag`'s context block.
        public let header: String
        /// Passage text, trimmed at a word boundary.
        public let text: String

        public init(id: String, header: String, text: String) {
            self.id = id
            self.header = header
            self.text = text
        }
    }

    /// The packing result.
    public struct Packed: Sendable, Equatable {
        public let passages: [Passage]
        /// Hits that carried content but did not fit.
        public let dropped: Int
        /// Estimated prompt size, instructions and question included.
        public let estimatedPromptTokens: Int

        public var isEmpty: Bool { passages.isEmpty }
    }

    public let budget: Budget

    public init(budget: Budget = .onDevice) {
        self.budget = budget
    }

    /// Pack `hits` best-first until the budget is spent.
    ///
    /// Hits are taken in the order retrieval returned them (already sorted by
    /// fused score), so the packer never reorders evidence — it only truncates.
    ///
    /// :param hits: Retrieval hits, best-first.
    /// :param question: The question, charged against the same budget.
    /// :returns: The passages to send, and how many were left behind.
    public func pack(_ hits: [Hit], question: String) -> Packed {
        let allowance = budget.passageAllowance - Self.estimateTokens(question)
        var spent = 0
        var packed: [Passage] = []
        var dropped = 0

        for hit in hits {
            guard let content = hit.synthesisText, !content.isEmpty else { continue }

            guard packed.count < budget.maxPassages else {
                dropped += 1
                continue
            }

            let header = Self.header(for: hit)
            let clean = content.trimmingCharacters(in: .whitespacesAndNewlines)
            let text = Self.trim(clean, to: budget.maxCharactersPerPassage)
            // Keep a short passage only when it is short because that is all
            // there was — never because trimming ground it down to a fragment.
            guard text.count >= budget.minCharactersPerPassage || text.count == clean.count
            else {
                dropped += 1
                continue
            }

            // "[header]\ntext\n\n" — the same shape synthesize_rag builds.
            let cost = Self.estimateTokens(header) + Self.estimateTokens(text) + 4
            guard spent + cost <= allowance else {
                dropped += 1
                continue
            }

            spent += cost
            packed.append(Passage(id: hit.nodeId, header: header, text: text))
        }

        return Packed(
            passages: packed,
            dropped: dropped,
            estimatedPromptTokens: spent
                + Self.estimateTokens(question)
                + budget.reservedForOverhead)
    }

    // MARK: - Helpers

    /// Conservative token estimate: ~4 characters per token for English prose.
    ///
    /// The Foundation Models framework exposes no public tokenizer, so the
    /// budget deliberately over-counts rather than risk an
    /// `exceededContextWindowSize` failure mid-answer. Verified against the
    /// golden-query set at export time.
    public static func estimateTokens(_ text: String) -> Int {
        (text.count + 3) / 4
    }

    /// `genre · author · title`, skipping the parts a hit does not carry.
    ///
    /// Mirrors `synthesize_rag`: genre falls back to `kg_kind`, title falls
    /// back to `name`.
    public static func header(for hit: Hit) -> String {
        let genre = hit.genre ?? hit.kgKind
        let title = hit.title ?? hit.name
        return [genre, hit.author, title]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }

    /// Truncate at the last word boundary inside `limit`, like chat.py's
    /// `_preview`. Returns the input unchanged when it already fits.
    public static func trim(_ text: String, to limit: Int) -> String {
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard clean.count > limit else { return clean }
        let cut = clean.prefix(limit)
        guard let lastSpace = cut.lastIndex(where: { $0.isWhitespace }) else {
            return String(cut) + "…"
        }
        return cut[..<lastSpace].trimmingCharacters(in: .whitespacesAndNewlines) + "…"
    }
}

extension Hit {
    /// The text synthesis should quote from: full content, else the summary.
    ///
    /// `synthesize_rag` requires `content`; the summary fallback exists because
    /// section-kind hits sometimes carry only a summary, and an answer from a
    /// summary beats no answer at all.
    var synthesisText: String? {
        if let content, !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return content
        }
        if let summary, !summary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return summary
        }
        return nil
    }
}
