// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The prompt contract, ported verbatim from kg_utils.synthesis._text so the
// on-device model is held to the same discipline as the worker's: answer only
// from the passages, never from what the model already believes it knows.
//
// Keep this file and _text.py's _RAG_SYSTEM / _IMAGE_REWRITE_SYSTEM in sync —
// a drift here is a silent change in what every answer is allowed to say.

import Foundation

/// Prompt construction for grounded synthesis.
public enum SynthesisPrompt {

    /// `_RAG_SYSTEM` from `kg_utils/synthesis/_text.py`, word for word.
    public static let ragInstructions = """
        You are a literary guide to the Project Gutenberg corpus. \
        Answer the question using ONLY the provided source passages. \
        Do NOT use any prior knowledge — if something is in the passages, \
        report it; if it is not in the passages, say so. \
        Never contradict or override what the passages say based on what \
        you believe to be true. Be concise and specific. \
        Cite the author and work when relevant.
        """

    /// `_IMAGE_REWRITE_SYSTEM` — prose to image prompt, run on device so the
    /// "🎨 Render response" path needs one fewer server round-trip.
    public static let imageRewriteInstructions = """
        You are an expert art director. Given a passage of historical text, \
        write a single concise image generation prompt (one paragraph, no \
        bullet points, no quotation marks) that vividly describes the scene \
        for a text-to-image model. Focus on visual elements: setting, \
        lighting, figures, mood, and artistic style. Do NOT include any text, \
        labels, captions, or words in the scene description. Output ONLY the \
        prompt, nothing else.
        """

    /// The user turn: the context block, then the question.
    ///
    /// Byte-identical in shape to `synthesize_rag`'s message — `[header]`,
    /// newline, passage, blank line between passages, then the question.
    ///
    /// :param question: The user's question, verbatim.
    /// :param passages: Already packed by ``ContextBudgeter``.
    public static func ragUserPrompt(
        question: String,
        passages: [ContextBudgeter.Passage]
    ) -> String {
        let context = passages
            .map { "[\($0.header)]\n\($0.text)" }
            .joined(separator: "\n\n")
        return "Source passages:\n\(context)\n\nQuestion: \(question)"
    }
}
