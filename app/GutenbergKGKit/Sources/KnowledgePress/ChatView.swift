// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Chat tab — the main loop of chat.py: title, scrolling turns, input bar.

import GutenbergKGKit
import SwiftUI

struct ChatView: View {
    @Environment(AppModel.self) private var model
    @State private var draft = ""
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
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
                        if model.isQuerying {
                            HStack(spacing: 8) {
                                ProgressView().controlSize(.small)
                                Text("Searching the corpus…")
                                    .foregroundStyle(.secondary)
                            }
                            .id("busy")
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
        VStack(alignment: .leading, spacing: 8) {
            Text("Ask about any text in the corpus, or try a suggestion from the sidebar.")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 40)
    }

    private var inputBar: some View {
        HStack {
            TextField("Ask about any text in the corpus…", text: $draft)
                .textFieldStyle(.roundedBorder)
                .focused($inputFocused)
                .onSubmit(submit)
                .disabled(model.isQuerying)
            Button("Send", action: submit)
                .keyboardShortcut(.defaultAction)
                .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty || model.isQuerying)
        }
        .padding()
    }

    private func submit() {
        let text = draft
        draft = ""
        inputFocused = true
        Task { await model.send(text) }
    }
}

/// One question/answer exchange.
struct TurnView: View {
    let turn: ChatTurn

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Spacer()
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
            if let error = turn.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.orange)
            } else if let result = turn.result {
                AssistantTurnView(result: result)
            }
        }
    }
}
