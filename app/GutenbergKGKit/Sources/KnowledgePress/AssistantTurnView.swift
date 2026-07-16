// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Assistant turn — chat.py's `_render_assistant_turn` + `_render_hit_card`:
// synthesis (or info state), stats caption, and collapsible hit cards with
// KG badges and score bars.

import GutenbergKGKit
import SwiftUI

struct AssistantTurnView: View {
    let result: QueryResult
    @State private var passagesExpanded: Bool

    init(result: QueryResult) {
        self.result = result
        // Same rule as chat.py: expand sources when there is no synthesis.
        _passagesExpanded = State(initialValue: result.synthesis == nil)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if result.hits.isEmpty {
                Label(
                    "No passages matched — try different wording or lower the min score.",
                    systemImage: "magnifyingglass")
                .foregroundStyle(.orange)
            } else {
                synthesisBlock
                statsCaption
                DisclosureGroup(isExpanded: $passagesExpanded) {
                    VStack(spacing: 8) {
                        ForEach(result.hits) { hit in
                            HitCardView(hit: hit)
                        }
                    }
                    .padding(.top, 6)
                } label: {
                    Text("📄 Source passages (\(result.hits.count))")
                        .font(.callout.weight(.medium))
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var synthesisBlock: some View {
        if let synthesis = result.synthesis {
            Text(markdown(synthesis))
                .textSelection(.enabled)
            if let model = result.model {
                Text("🤖 \(model)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        } else if let error = result.synthesisError {
            Label(
                "Answer generation failed — \(error). Check that Ollama/oMLX is running.",
                systemImage: "exclamationmark.triangle")
            .foregroundStyle(.orange)
        } else {
            Label("Answer generation off — see source passages below.", systemImage: "info.circle")
                .foregroundStyle(.secondary)
        }
    }

    private var statsCaption: some View {
        var parts = ["📊 \(result.totalHits) passages · \(result.kgsQueried) KGs queried"]
        if let ms = result.searchMs { parts.append("search \(ms.formatted()) ms") }
        if let ms = result.synthesisMs { parts.append("synthesis \(ms.formatted()) ms") }
        return Text(parts.joined(separator: " · "))
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    private func markdown(_ text: String) -> AttributedString {
        (try? AttributedString(
            markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(text)
    }
}

/// One search hit as a card: badges, title/author line, score bar, and an
/// expandable full passage.
struct HitCardView: View {
    let hit: Hit
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                badge(kgLabel, color: kgColor)
                badge(hit.kind, color: .gray)
                if let timestamp = hit.timestamp {
                    Text(timestamp.prefix(10))
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                }
                Spacer()
                scoreBar
            }
            Text(headline)
                .font(.callout.weight(.semibold))
            if let preview {
                Text(expanded ? preview.full : preview.short)
                    .font(.callout)
                    .textSelection(.enabled)
                    .foregroundStyle(.primary.opacity(0.9))
                if preview.truncated {
                    Button(expanded ? "Show less" : "Show full passage") {
                        expanded.toggle()
                    }
                    .buttonStyle(.link)
                    .font(.caption)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 8))
    }

    private var headline: String {
        let title = hit.title ?? hit.name
        return [title, hit.author].compactMap { $0 }.filter { !$0.isEmpty }
            .joined(separator: " · ")
    }

    private var kgLabel: String {
        hit.kgKind.lowercased().contains("diary") ? "diary" : (hit.genre ?? "gutenberg")
    }

    private var kgColor: Color {
        hit.kgKind.lowercased().contains("diary") ? .purple : .blue
    }

    private var preview: (short: String, full: String, truncated: Bool)? {
        guard let text = (hit.content?.isEmpty == false ? hit.content : hit.summary),
            !text.isEmpty
        else { return nil }
        let full = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if full.count <= 360 { return (full, full, false) }
        // Truncate at a word boundary, like chat.py's `_preview`.
        let cut = full.prefix(360)
        let short = cut[..<(cut.lastIndex(of: " ") ?? cut.endIndex)] + " …"
        return (String(short), full, true)
    }

    private func badge(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.caption2.weight(.medium))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.15), in: Capsule())
            .foregroundStyle(color)
    }

    /// Score bar tinted by magnitude — chat.py's `_score_bar`.
    private var scoreBar: some View {
        HStack(spacing: 4) {
            ProgressView(value: min(max(hit.score, 0), 1))
                .frame(width: 60)
                .tint(hit.score >= 0.7 ? .green : hit.score >= 0.5 ? .orange : .red)
            Text(String(format: "%.3f", hit.score))
                .font(.caption2.monospaced())
                .foregroundStyle(.secondary)
        }
    }
}
