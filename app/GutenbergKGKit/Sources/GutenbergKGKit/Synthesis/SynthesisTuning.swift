// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.
//
// The knobs on Apple Foundation Models synthesis that are worth turning by
// hand: decoding, packing density, which instructions, and whether the
// framework's content guardrail gets to veto the Inferno.
//
// Everything here maps onto something Apple documents. `temperature` and
// `greedy` are `GenerationOptions`; `permissiveGuardrails` is
// `SystemLanguageModel(guardrails: .permissiveContentTransformations)`, the
// mode Apple describes for apps that "work with certain inputs ... that
// might contain sensitive content"; the rest is this app's own packing and
// prompting. A trace (`SynthesisTrace`) records temperature and the exact
// instructions, so a saved answer can always be tied back to its settings.

import Foundation

/// Per-request settings for the Foundation Models backends.
public struct SynthesisTuning: Sendable, Equatable, Codable {

    /// Which instruction block the session opens with.
    public enum Instructions: String, Sendable, Codable, CaseIterable {
        /// `SynthesisPrompt.guideInstructions` -- written for a small model:
        /// role, task, paragraph shape, and no request to be brief.
        case guide
        /// `SynthesisPrompt.ragInstructions` -- the worker's `_RAG_SYSTEM`
        /// verbatim, kept so on-device and server answers can be compared
        /// under identical instructions.
        case workerParity

        public var label: String {
            switch self {
            case .guide: return "Guide"
            case .workerParity: return "Worker parity"
            }
        }
    }

    /// Sampling temperature, 0...1. Ignored when `greedy` is set.
    ///
    /// 0.2 rather than 0: greedy decoding loops on repeated text when
    /// several passages share a source, and 0.2 is low enough that answers
    /// still restate the passages rather than paraphrase freely.
    public var temperature: Double

    /// `GenerationOptions.SamplingMode.greedy` -- always the most likely
    /// token. What `/usr/bin/fm --greedy` does, and what makes a replay
    /// reproducible byte for byte.
    public var greedy: Bool

    /// Override for `ContextBudgeter.Budget.maxPassagesPerSource`, or nil to
    /// keep each engine's own preset (2 on-device, 4 for Private Cloud
    /// Compute).
    public var maxPassagesPerSource: Int?

    public var instructions: Instructions

    /// Skip the framework's input/output guardrail for string generation.
    ///
    /// On-device only; the Private Cloud Compute model takes no guardrail
    /// parameter. Apple's note: "the on-device system language model still
    /// has a layer of safety", so refusals can still happen, just less often
    /// against a corpus that includes the Old Testament and Frankenstein.
    public var permissiveGuardrails: Bool

    public init(
        temperature: Double = 0.2,
        greedy: Bool = false,
        maxPassagesPerSource: Int? = nil,
        instructions: Instructions = .guide,
        permissiveGuardrails: Bool = false
    ) {
        self.temperature = temperature
        self.greedy = greedy
        self.maxPassagesPerSource = maxPassagesPerSource
        self.instructions = instructions
        self.permissiveGuardrails = permissiveGuardrails
    }

    public static let `default` = SynthesisTuning()

    /// The instruction text this tuning selects.
    public var instructionText: String {
        switch instructions {
        case .guide: return SynthesisPrompt.guideInstructions
        case .workerParity: return SynthesisPrompt.ragInstructions
        }
    }

    /// `budget` with the per-source cap override applied, if any.
    public func apply(to budget: ContextBudgeter.Budget) -> ContextBudgeter.Budget {
        var budget = budget
        if let cap = maxPassagesPerSource { budget.maxPassagesPerSource = max(1, cap) }
        return budget
    }
}
