// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Sidebar controls — a 1:1 translation of chat.py's `_render_sidebar`:
// corpus scope, search sliders, synthesis provider/model, clear chat.

import GutenbergKGKit
import SwiftUI

struct SettingsSidebarView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        List {
            Section {
                Text("📚 GutenbergKG")
                    .font(.title2.bold())
                Text(model.statsCaption)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let error = model.connectionError {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                    Button("Retry") {
                        Task { await model.refreshSidebar() }
                    }
                }
            }

            Section("📖 Corpus") {
                Picker("Scope", selection: $model.corpus) {
                    ForEach(model.corpusOptions, id: \.self) { Text($0).tag($0) }
                }
                .help("all = DocKG + DiaryKG · gutenberg = DocKG only · diary = diaries only · <genre> = one genre")
            }

            Section("⚙️ Search") {
                LabeledSlider(label: "Results", value: $model.resultCount, range: 1...50, format: "%.0f")
                LabeledSlider(label: "Min score", value: $model.minScore, range: 0...0.9, format: "%.2f")
                LabeledSlider(label: "Semantic floor", value: $model.semanticFloor, range: 0...0.9, format: "%.2f")
                Toggle("Synthesize response", isOn: $model.synthesize)
                    .onChange(of: model.synthesize) { _, on in
                        if on { Task { await model.refreshModels() } }
                    }

                if model.synthesize {
                    Picker("Provider", selection: $model.backend) {
                        ForEach(AppModel.providers, id: \.key) { provider in
                            Text(provider.label).tag(provider.key)
                        }
                    }
                    .onChange(of: model.backend) { _, _ in
                        Task { await model.refreshModels() }
                    }
                    if model.models.isEmpty {
                        Text("⚠️ No models reported — using provider default.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Picker("Model", selection: $model.model) {
                            ForEach(model.models, id: \.self) { Text($0).tag($0) }
                        }
                    }
                }
            }

            Section("💡 Try asking") {
                ForEach(AppModel.suggestedQueries, id: \.query) { suggestion in
                    Button {
                        Task { await model.send(suggestion.query, corpusOverride: suggestion.corpus) }
                    } label: {
                        Text("[\(suggestion.corpus)] \(suggestion.query)")
                            .font(.caption)
                            .lineLimit(2)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.tint)
                }
            }

            Section {
                Button("🗑️ Clear chat", role: .destructive) {
                    model.turns.removeAll()
                }
                .disabled(model.turns.isEmpty)
            }

            Section("Worker") {
                TextField("URL", text: $model.workerURLString)
                    .textFieldStyle(.roundedBorder)
                    .font(.caption)
                    .onSubmit { Task { await model.refreshSidebar() } }
            }
        }
        .listStyle(.sidebar)
    }
}

/// Slider with an inline value readout, matching Streamlit's labeled sliders.
struct LabeledSlider: View {
    let label: String
    @Binding var value: Double
    let range: ClosedRange<Double>
    let format: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label)
                Spacer()
                Text(String(format: format, value))
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
            .font(.caption)
            Slider(value: $value, in: range)
        }
    }
}
