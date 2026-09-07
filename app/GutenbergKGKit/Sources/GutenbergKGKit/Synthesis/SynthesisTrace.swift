// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// A verbatim record of one synthesis call: the exact instructions and prompt
// the Foundation Models framework was handed, and the exact completion it
// returned.
//
// This exists because two devices on the same OS build, running the same
// binary against byte-identical corpus packs at temperature 0, answered the
// same question differently -- and every layer this project controls was
// verified identical first (corpus, scope, budgeter, streaming, rendering).
// Comparing screenshots cannot distinguish "the model was asked something
// different" from "the model answered differently"; a diff of two of these
// files can.

import Foundation

/// One synthesis call, recorded whole.
public struct SynthesisTrace: Codable, Sendable {
    public let recordedAt: String
    /// Hardware identifier, e.g. `iPad16,3` -- the field a bug report needs,
    /// rather than the marketing name.
    public let hardware: String
    /// Includes the build number, e.g. "Version 27.0 (Build 24A5430a)".
    public let systemVersion: String
    public let modelDescription: String
    public let temperature: Double
    public let question: String
    public let passagesUsed: Int
    public let passagesDropped: Int
    public let estimatedPromptTokens: Int
    public let elapsedMs: Int
    public let passageIds: [String]
    public let passageHeaders: [String]
    /// The session's system instructions, verbatim.
    public let instructions: String
    /// The user prompt, verbatim, passages included.
    public let prompt: String
    /// What the model returned, verbatim and unmodified.
    public let answer: String
    public let answerCharacters: Int
    /// Distinct vs. total lines. A model stuck in a repetition loop shows up
    /// here as a count mismatch without anyone having to read the answer.
    public let answerLines: Int
    public let answerUniqueLines: Int
}

extension SynthesisTrace {

    /// Where traces are written. Sibling of the corpus, excluded from backup.
    public static func directory() -> URL? {
        guard
            var url = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)
                .first
        else { return nil }
        url.appendPathComponent("Diagnostics", isDirectory: true)
        if !FileManager.default.fileExists(atPath: url.path) {
            try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            var resource = URLResourceValues()
            resource.isExcludedFromBackup = true
            try? url.setResourceValues(resource)
        }
        return url
    }

    /// `iPad16,3`, `iPhone18,1`. Empty when `uname` gives nothing usable.
    static func hardwareIdentifier() -> String {
        var info = utsname()
        uname(&info)
        return withUnsafeBytes(of: &info.machine) { raw in
            String(decoding: raw.prefix { $0 != 0 }, as: UTF8.self)
        }
    }

    /// Record one call. Never throws and never blocks the answer: the caller
    /// yields `.completed` first, and any failure here is a lost diagnostic,
    /// not a lost answer.
    static func record(
        question: String,
        instructions: String,
        prompt: String,
        answer: String,
        passages: [ContextBudgeter.Passage],
        metrics: SynthesisMetrics,
        temperature: Double
    ) {
        let lines = answer.split(separator: "\n").map(String.init)
        let stamp = ISO8601DateFormatter()
        stamp.formatOptions = [.withInternetDateTime]

        let trace = SynthesisTrace(
            recordedAt: stamp.string(from: Date()),
            hardware: hardwareIdentifier(),
            systemVersion: ProcessInfo.processInfo.operatingSystemVersionString,
            modelDescription: metrics.model,
            temperature: temperature,
            question: question,
            passagesUsed: metrics.passagesUsed,
            passagesDropped: metrics.passagesDropped,
            estimatedPromptTokens: metrics.estimatedPromptTokens,
            elapsedMs: metrics.elapsedMs,
            passageIds: passages.map(\.id),
            passageHeaders: passages.map(\.header),
            instructions: instructions,
            prompt: prompt,
            answer: answer,
            answerCharacters: answer.count,
            answerLines: lines.count,
            answerUniqueLines: Set(lines).count)

        guard let directory = directory() else { return }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(trace) else { return }

        let name = trace.recordedAt.replacingOccurrences(of: ":", with: "-")
        try? data.write(to: directory.appendingPathComponent("synthesis-\(name).json"))
    }
}
