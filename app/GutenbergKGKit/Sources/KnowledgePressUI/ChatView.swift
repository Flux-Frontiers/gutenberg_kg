// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Chat tab — the main loop of chat.py: title, scrolling turns, input bar.

import GutenbergKGKit
import SwiftUI

struct ChatView: View {
    @Environment(AppModel.self) private var model
    @State private var draft = ""
    @FocusState private var inputFocused: Bool

    /// The Mac window carries the title in its own chrome and the settings in
    /// the sidebar; the phone needs both inline.
    let showsHeader: Bool

    init(showsHeader: Bool = true) {
        self.showsHeader = showsHeader
    }

    var body: some View {
        VStack(spacing: 0) {
            if showsHeader {
                header
                Divider()
            }
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        if model.turns.isEmpty {
                            emptyState
                        }
                        ForEach(model.turns) { turn in
                            TurnView(turn: turn)
                                .id(turn.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: model.turns.count) { _, _ in
                    withAnimation { proxy.scrollTo(model.turns.last?.id, anchor: .top) }
                }
            }
            Divider()
            inputBar
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("📚 The Knowledge Press")
                .font(.largeTitle.bold())
            Text("Semantic search across the Project Gutenberg corpus — \(model.statsCaption)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding([.horizontal, .top])
        .padding(.bottom, 8)
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Ask about any text in the corpus.")
                .foregroundStyle(.secondary)
            EngineBadge()
            VStack(alignment: .leading, spacing: 8) {
                ForEach(AppModel.suggestedQueries, id: \.query) { suggestion in
                    Button {
                        model.send(suggestion.query, corpusOverride: suggestion.corpus)
                    } label: {
                        HStack(spacing: 8) {
                            Text(suggestion.corpus)
                                .font(.caption2.monospaced())
                                .padding(.horizontal, 6)
                                .padding(.vertical, 3)
                                .background(.tint.opacity(0.15), in: Capsule())
                            Text(suggestion.query)
                                .multilineTextAlignment(.leading)
                            Spacer(minLength: 0)
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 10))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 24)
    }

    private var inputBar: some View {
        HStack {
            TextField("Ask about any text in the corpus…", text: $draft)
                .textFieldStyle(.roundedBorder)
                .focused($inputFocused)
                .onSubmit(submit)
                .disabled(model.isQuerying)
            if model.isQuerying {
                Button("Stop", systemImage: "stop.circle", action: model.cancel)
                    .labelStyle(.iconOnly)
            } else {
                Button("Send", action: submit)
                    .keyboardShortcut(.defaultAction)
                    .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding()
    }

    private func submit() {
        let text = draft
        draft = ""
        inputFocused = true
        model.send(text)
    }
}

/// "Answers from Apple Intelligence, on this device" — or the reason it cannot.
struct EngineBadge: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let availability = model.onDeviceAvailability
        HStack(spacing: 7) {
            Image(systemName: symbol(availability))
            Text(message(availability))
        }
        .font(.caption)
        .foregroundStyle(availability.isAvailable ? Color.secondary : Color.orange)
    }

    private func symbol(_ availability: SynthesisAvailability) -> String {
        if !availability.isAvailable { return "exclamationmark.triangle" }
        return model.isFullyLocal ? "airplane" : "iphone.gen3"
    }

    private func message(_ availability: SynthesisAvailability) -> String {
        if let reason = availability.reason {
            return "On-device answers unavailable — \(reason)."
        }
        if model.isFullyLocal {
            return "Passages and answers both come from this device. Works in airplane mode."
        }
        return "Answers are written on this device; passages come from the worker."
    }
}

/// One question/answer exchange.
struct TurnView: View {
    let turn: ChatTurn

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Spacer(minLength: 40)
                HStack(spacing: 6) {
                    if turn.corpus != "all" {
                        Text(turn.corpus)
                            .font(.caption2.monospaced())
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(.tint.opacity(0.15), in: Capsule())
                    }
                    Text(turn.question)
                }
                .padding(10)
                .background(.tint.opacity(0.1), in: RoundedRectangle(cornerRadius: 10))
            }
            AssistantTurnView(turn: turn)
        }
    }
}
