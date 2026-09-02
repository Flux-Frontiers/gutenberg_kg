// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Settings — a translation of chat.py's `_render_sidebar`: corpus scope,
// search sliders, answer engine, clear chat. Renders as the persistent
// sidebar on macOS and as a sheet on iPhone; same controls either way.

import GutenbergKGKit
import SwiftUI

struct SettingsView: View {
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
                .help(
                    "all = DocKG + DiaryKG · gutenberg = DocKG only · diary = diaries only · <genre> = one genre"
                )
            }

            Section("⚙️ Search") {
                LabeledSlider(
                    label: "Results", value: $model.resultCount, range: 1...50, format: "%.0f")
                LabeledSlider(
                    label: "Min score", value: $model.minScore, range: 0...0.9, format: "%.2f")
                LabeledSlider(
                    label: "Semantic floor", value: $model.semanticFloor, range: 0...0.9,
                    format: "%.2f")
            }

            answerEngineSection

            Section("💡 Try asking") {
                ForEach(AppModel.suggestedQueries, id: \.query) { suggestion in
                    Button {
                        model.send(suggestion.query, corpusOverride: suggestion.corpus)
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
                // Say plainly where the passages come from. Until a corpus
                // pack is installed (Phase 2), retrieval is a network call
                // even when the answer is written on device.
                Text("Passages are retrieved from the worker. The answer engine is separate.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        #if os(macOS)
            .listStyle(.sidebar)
        #endif
    }

    @ViewBuilder
    private var answerEngineSection: some View {
        @Bindable var model = model
        Section("🤖 Answers") {
            Picker("Engine", selection: $model.engine) {
                ForEach(AnswerEngine.allCases, id: \.self) { engine in
                    Text(engine.label).tag(engine)
                }
            }
            .onChange(of: model.engine) { _, engine in
                if engine == .worker { Task { await model.refreshModels() } }
                if engine == .onDevice { model.prewarmOnDevice() }
            }

            Text(model.engine.detail)
                .font(.caption)
                .foregroundStyle(.secondary)

            switch model.engine {
            case .onDevice:
                if let reason = model.onDeviceAvailability.reason {
                    Label(
                        "Unavailable — \(reason). Pick another engine to get answers.",
                        systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                } else {
                    Text("Context window 4,096 tokens — up to 5 passages reach the model.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            case .worker:
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
            case .off:
                EmptyView()
            }
        }
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
