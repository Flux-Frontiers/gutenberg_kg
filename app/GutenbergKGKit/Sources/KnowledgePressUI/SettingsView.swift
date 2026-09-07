// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Settings — a translation of chat.py's `_render_sidebar`: corpus scope,
// search sliders, answer engine, clear chat. Renders as the persistent
// sidebar on macOS and as a sheet on iPhone; same controls either way.

import Foundation
import GutenbergKGKit
import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var confirmingDelete = false
    #if !os(macOS)
        @State private var showingAbout = false
    #endif

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

            illustrationSection

            Section {
                Button("🗑️ Delete conversation", role: .destructive) {
                    confirmingDelete = true
                }
                .disabled(model.activeConversation == nil && model.turns.isEmpty)
            }

            corpusSection

            workerSection

            #if !os(macOS)
                // macOS keeps About in the app menu — the platform-standard
                // place — via `.commands` in KnowledgePressApp.swift, so this
                // row exists only where that menu doesn't.
                Section {
                    Button("ℹ️ About") { showingAbout = true }
                }
            #endif
        }
        .confirmationDialog(
            "Delete this conversation?", isPresented: $confirmingDelete, titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) { model.deleteActiveConversation() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes the questions, answers, and any illustrations. It cannot be undone.")
        }
        #if os(macOS)
            .listStyle(.sidebar)
        #else
            .sheet(isPresented: $showingAbout) {
                NavigationStack {
                    AboutView()
                        .toolbar {
                            ToolbarItem(placement: .confirmationAction) {
                                Button("Done") { showingAbout = false }
                            }
                        }
                }
            }
        #endif
    }

    /// Worker address.
    ///
    /// Shown unconditionally. It used to be hidden once packs were installed,
    /// on the reasoning that a local corpus makes the worker redundant — but
    /// `.worker` stays a selectable answer engine, and picking it with the
    /// field hidden left no way to say where the worker is.
    @ViewBuilder
    private var workerSection: some View {
        @Bindable var model = model
        Section("Worker") {
            TextField(AppModel.workerURLPlaceholder, text: $model.workerURLString)
                .textFieldStyle(.roundedBorder)
                .font(.caption)
                #if !os(macOS)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                #endif
                .onSubmit { Task { await model.probeWorker() } }

            HStack {
                Button("Test") { Task { await model.probeWorker() } }
                    .disabled(!model.hasWorkerURL)
                Spacer()
                switch model.workerProbe {
                case .idle:
                    EmptyView()
                case .probing:
                    ProgressView().controlSize(.small)
                case .reachable(let summary):
                    Label(summary, systemImage: "checkmark.circle.fill")
                        .font(.caption2)
                        .foregroundStyle(.green)
                case .unreachable(let why):
                    Label(why, systemImage: "xmark.circle.fill")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                        .lineLimit(2)
                }
            }

            Text(
                model.packs == nil
                    ? "With no corpus installed, passages come from the worker."
                    : "Passages come from this device. The worker is only used by the Worker answer engine."
            )
            .font(.caption2)
            .foregroundStyle(.secondary)

            #if !os(macOS)
                Text("`localhost` is this phone, not your Mac — use its name or IP.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            #endif
        }
    }

    /// Size of a rendered illustration — chat.py's "Resolution" selectbox.
    ///
    /// Sits beside the answer engine rather than in the Worker section
    /// because it is a choice about the picture, not about the connection,
    /// even though the worker is what draws it.
    @ViewBuilder
    private var illustrationSection: some View {
        @Bindable var model = model
        Section("🎨 Illustrations") {
            Picker("Resolution", selection: $model.imageResolution) {
                ForEach(ImageResolution.allCases, id: \.self) { resolution in
                    Text(resolution.label).tag(resolution)
                }
            }
            Text("Smaller renders faster. Illustrations always come from the worker.")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
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
            case .privateCloud:
                if let reason = model.privateCloudAvailability.reason {
                    Label(
                        "Unavailable — \(reason). Pick another engine to get answers.",
                        systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.orange)
                } else {
                    Text("Context window 32,768 tokens — up to 12 passages reach the model.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    if let quota = model.privateCloudQuotaCaption {
                        Label(quota, systemImage: "gauge.with.needle")
                            .font(.caption)
                            .foregroundStyle(.orange)
                        Button("Show usage options") { model.presentPrivateCloudLimitIncrease() }
                            .font(.caption)
                    }
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

extension SettingsView {
    /// Where the passages come from, and whether the answer needs the network.
    @ViewBuilder
    fileprivate var corpusSection: some View {
        Section("📦 Corpus") {
            if model.isLoadingPacks {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Opening the installed corpus…")
                }
                .font(.caption)
            } else if let packs = model.packs {
                LabeledContent("Passages", value: "on this device")
                LabeledContent("Vectors", value: packs.manifest.vectorDtype)
                LabeledContent("Embedder", value: packs.manifest.embedder.model)
                LabeledContent(
                    "Size",
                    value: ByteCountFormatter.string(
                        fromByteCount: Int64(packs.manifest.totalBytes), countStyle: .file))
                if model.isFullyLocal {
                    Label(
                        "Search and answers both run here. Airplane mode changes nothing.",
                        systemImage: "airplane")
                        .font(.caption)
                        .foregroundStyle(Color.green)
                } else {
                    Text("Passages are local; the answer engine is not.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Label(
                    model.packsError
                        ?? "No corpus installed — passages come from the worker. Build one with `gutenkg export-swift`.",
                    systemImage: model.packsError == nil ? "info.circle" : "exclamationmark.triangle"
                )
                .font(.caption)
                .foregroundStyle(model.packsError == nil ? Color.secondary : Color.orange)
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
