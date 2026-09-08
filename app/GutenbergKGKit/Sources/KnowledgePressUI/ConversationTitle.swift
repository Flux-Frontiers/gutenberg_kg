// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Naming a conversation from its first question. Deterministic and instant,
// rather than asking the on-device model: a wrong title is more visible than
// a wrong answer, and the model's behaviour currently differs by device
// (analysis/FOUNDATION_MODELS_DIVERGENCE_20260907.md).

import Foundation

enum ConversationTitle {
    /// The longest title a sidebar row shows without truncating it itself.
    static let defaultLimit = 48

    /// Title a conversation after its first question.
    ///
    /// Whitespace is collapsed so a pasted multi-line question does not become
    /// a multi-line row, and an over-long question is cut at a word boundary
    /// -- mid-word truncation reads as a bug rather than as a shortening.
    ///
    /// :param question: The first question, verbatim.
    /// :param limit: Maximum characters before the ellipsis.
    /// :returns: A single-line title, or "New chat" when nothing is left.
    static func title(for question: String, limit: Int = defaultLimit) -> String {
        let collapsed = question.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        guard !collapsed.isEmpty else { return "New chat" }
        guard collapsed.count > limit else { return collapsed }

        let cut = collapsed.prefix(limit)
        // Fall back to the hard cut when the first `limit` characters hold no
        // space at all -- one very long token, where there is no boundary to
        // prefer.
        guard let lastSpace = cut.lastIndex(of: " ") else { return cut + "..." }
        let trimmed = cut[..<lastSpace]
        return trimmed.isEmpty ? cut + "..." : trimmed + "..."
    }
}
