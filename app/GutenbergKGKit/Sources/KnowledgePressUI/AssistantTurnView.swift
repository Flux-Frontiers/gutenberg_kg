// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Assistant turn — chat.py's `_render_assistant_turn` + `_render_hit_card`:
// the answer (streaming, or one of the honest not-answered states), the stats
// caption, and collapsible hit cards with KG badges and score bars.

import GutenbergKGKit
import SwiftUI

struct AssistantTurnView: View {
    let turn: ChatTurn
    @State private var passagesExpanded: Bool?

    private var hits: [Hit] { turn.retrieval?.hits ?? [] }

    /// Same rule as chat.py — sources open when there is no answer to read —
    /// but a manual toggle wins once the reader has expressed a preference.
    private var showPassages: Bool {
        passagesExpanded ?? (turn.answer.isEmpty && turn.engine != .off)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let error = turn.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
            } else if turn.retrieval == nil {
                searchingRow
            } else if hits.isEmpty {
                Label(
                    "No passages matched — try different wording or lower the min score.",
                    systemImage: "magnifyingglass")
                .foregroundStyle(.orange)
            } else {
                answerBlock
                statsCaption
                DisclosureGroup(
                    isExpanded: Binding(
                        get: { showPassages },
                        set: { passagesExpanded = $0 })
                ) {
                    VStack(spacing: 8) {
                        ForEach(hits) { hit in
                            HitCardView(hit: hit)
                        }
                    }
                    .padding(.top, 6)
                } label: {
                    Text("📄 Source passages (\(hits.count))")
                        .font(.callout.weight(.medium))
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var searchingRow: some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small)
            Text("Searching the corpus…").foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var answerBlock: some View {
        if !turn.answer.isEmpty {
            // The on-device model streams snapshots of the whole answer, so
            // this text is replaced rather than appended — no flicker, and
            // Markdown stays parseable at every intermediate state.
            Text(markdown(turn.answer))
                .textSelection(.enabled)
            if turn.isStreaming {
                StreamingCaret()
            }
            if let metrics = turn.metrics {
                HStack(spacing: 6) {
                    if turn.engine == .onDevice {
                        Text("on-device")
                            .font(.caption2.monospaced())
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(.tint.opacity(0.15), in: Capsule())
                    }
                    Text("🤖 \(metrics.model)")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        } else if let failure = turn.synthesisFailure {
            VStack(alignment: .leading, spacing: 6) {
                Label(failure.displayMessage, systemImage: "info.circle")
                    .foregroundStyle(failure == .noPassages ? Color.secondary : Color.orange)
                if failure.isRecoverableRemotely {
                    Text("Switch the answer engine to the worker in Settings to retry this one.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        } else if turn.engine == .off {
            Label("Answer generation off — see source passages below.", systemImage: "info.circle")
                .foregroundStyle(.secondary)
        } else {
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text("Writing an answer from \(hits.count) passages…")
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var statsCaption: some View {
        var parts = ["📊 \(hits.count) passages"]
        if let retrieval = turn.retrieval {
            parts.append("\(retrieval.kgsQueried) KGs queried")
            if let ms = retrieval.searchMs { parts.append("search \(ms.formatted()) ms") }
        }
        if let metrics = turn.metrics {
            parts.append("synthesis \(metrics.elapsedMs.formatted()) ms")
            if metrics.passagesDropped > 0 {
                // Say so rather than quietly answering from half the evidence:
                // the on-device context window is small enough that this is
                // ordinary, not exceptional.
                parts.append("\(metrics.passagesUsed) of \(hits.count) in context")
            }
        }
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

/// A blinking block caret, so a slow first token reads as "working" rather
/// than "stuck".
struct StreamingCaret: View {
    @State private var on = true

    var body: some View {
        RoundedRectangle(cornerRadius: 1)
            .frame(width: 7, height: 14)
            .opacity(on ? 1 : 0.15)
            .foregroundStyle(.tint)
            .animation(.easeInOut(duration: 0.5).repeatForever(autoreverses: true), value: on)
            .onAppear { on.toggle() }
            .accessibilityHidden(true)
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
                    .buttonStyle(.plain)
                    .foregroundStyle(.tint)
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
