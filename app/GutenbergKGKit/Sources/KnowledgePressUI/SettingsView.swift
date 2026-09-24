// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.
//
// Settings — a translation of chat.py's `_render_sidebar`: corpus scope,
// search sliders, answer engine, clear chat. Renders as the persistent
// sidebar on macOS and as a sheet on iPhone; same controls either way.

import Foundation
import GutenbergKGKit
import SwiftUI

public struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var confirmingDelete = false
    /// Which help topic is open, or nil. Drives one sheet for both the Help
    /// row and every section's info button, so there is a single presentation
    /// path rather than one per entry point.
    @State private var helpTopicID: String?
    @State private var showingHelpList = false

    /// Whether to show the answer engine and corpus scope here.
    ///
    /// False on the shells whose sidebar already carries them: one home per
    /// control, so a reader who changed the scope in the sidebar does not
    /// find a second copy of it here that may or may not agree.
    let showsEngineAndScope: Bool

    /// Public so the macOS app module can put it in a `Settings` scene,
    /// which is what gives Cmd-comma its standard behaviour.
    public init(showsEngineAndScope: Bool = true) {
        self.showsEngineAndScope = showsEngineAndScope
    }
    #if !os(macOS)
        @State private var showingAbout = false
    #endif

    public var body: some View {
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

            if showsEngineAndScope {
                Section("📖 Corpus") {
                    CorpusScopePicker()
                }
            }

            Section {
                LabeledSlider(
                    label: "Results", value: $model.resultCount, range: 1...50, format: "%.0f")
                LabeledSlider(
                    label: "Min score", value: $model.minScore, range: 0...0.9, format: "%.2f")
                LabeledSlider(
                    label: "Semantic floor", value: $model.semanticFloor, range: 0...0.9,
                    format: "%.2f")
                Button("↩️ Reset search to defaults") { model.resetSearchSettings() }
                    .disabled(model.searchSettingsAreDefault)
            } header: {
                HelpSectionHeader(
                    title: "⚙️ Search", topicID: "search", presentedTopicID: $helpTopicID)
            }

            if showsEngineAndScope {
                Section {
                    AnswerEnginePicker()
                } header: {
                    HelpSectionHeader(
                        title: "🤖 Answers", topicID: "engines", presentedTopicID: $helpTopicID)
                }
            }

            synthesisSection

            illustrationSection

            Section {
                Button("🗑️ Delete conversation", role: .destructive) {
                    confirmingDelete = true
                }
                .disabled(model.activeConversation == nil && model.turns.isEmpty)
            }

            corpusSection

            workerSection

            Section {
                Button("❓ Help") { showingHelpList = true }
                #if !os(macOS)
                    // macOS keeps About in the app menu — the platform-standard
                    // place — via `.commands` in KnowledgePressApp.swift, so
                    // this row exists only where that menu doesn't. Help has a
                    // row on both: the Mac gets a Help menu item as well, but
                    // a reader already in Settings should not have to leave it.
                    Button("ℹ️ About") { showingAbout = true }
                #endif
            }
        }
        .confirmationDialog(
            "Delete this conversation?", isPresented: $confirmingDelete, titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) { model.deleteActiveConversation() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes the questions, answers, and any illustrations. It cannot be undone.")
        }
        // One sheet for the section info buttons, one for the Help row. Both
        // present `HelpView`; only the starting page differs.
        .sheet(item: Binding(
            get: { helpTopicID.map(HelpTopicIdentifier.init) },
            set: { helpTopicID = $0?.id })
        ) { wrapper in
            HelpSheet { done in HelpView(initialTopicID: wrapper.id, onDone: done) }
        }
        .sheet(isPresented: $showingHelpList) {
            HelpSheet { done in HelpView(onDone: done) }
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

    /// The Foundation Models knobs, on-device and Private Cloud Compute.
    ///
    /// Every control here changes the *next* answer, since `AppModel` builds
    /// the backend per question from `synthesisTuning`. The per-work stepper
    /// reads 0 as "engine default" rather than as zero passages, which would
    /// be an answer from nothing.
    @ViewBuilder
    private var synthesisSection: some View {
        @Bindable var model = model
        let perSource = Binding<Int>(
            get: { model.synthesisTuning.maxPassagesPerSource ?? 0 },
            set: { model.synthesisTuning.maxPassagesPerSource = $0 == 0 ? nil : $0 })
        Section {
            LabeledSlider(
                label: "Temperature", value: $model.synthesisTuning.temperature, range: 0...1,
                format: "%.2f"
            )
            .disabled(model.synthesisTuning.greedy)
            Toggle("Greedy decoding", isOn: $model.synthesisTuning.greedy)
            Picker("Instructions", selection: $model.synthesisTuning.instructions) {
                ForEach(SynthesisTuning.Instructions.allCases, id: \.self) { set in
                    Text(set.label).tag(set)
                }
            }
            Stepper(value: perSource, in: 0...6) {
                HStack {
                    Text("Passages per work")
                    Spacer()
                    Text(perSource.wrappedValue == 0 ? "engine default" : "\(perSource.wrappedValue)")
                        .foregroundStyle(.secondary)
                }
            }
            Toggle("Permissive guardrails (on-device)", isOn: $model.synthesisTuning.permissiveGuardrails)
            Text("Changes apply to the next answer. Traces in Diagnostics record the settings each answer used.")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Button("↩️ Reset synthesis to defaults") { model.resetSynthesisTuning() }
                .disabled(model.synthesisTuning == .default)
        } header: {
            HelpSectionHeader(
                title: "🧪 Synthesis", topicID: HelpContent.synthesisTopicID,
                presentedTopicID: $helpTopicID)
        }
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
            Picker("Backend", selection: $model.imageBackendChoice) {
                Text("Auto").tag(AppModel.imageAuto)
                ForEach(model.imageBackends, id: \.key) { backend in
                    Text(backend.label).tag(backend.key)
                }
            }
            Text(
                "Smaller renders faster. Illustrations always come from the worker. "
                    + "Auto follows the provider: OpenAI images for OpenAI, the local image "
                    + "server for oMLX or Ollama. Only backends the worker can use right now "
                    + "are listed."
            )
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .task { await model.refreshImageBackends() }
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

/// `sheet(item:)` needs an `Identifiable`; a bare topic id string is not one.
private struct HelpTopicIdentifier: Identifiable {
    let id: String
}

/// Sizes the help sheet and supplies the dismissal each platform expects.
///
/// The Done action is passed *into* `HelpView` rather than wrapped around it:
/// the button has to live inside that view's own `NavigationStack` to appear
/// in the navigation bar. macOS gets no button, since a sheet there already
/// closes from its title bar, and a fixed frame instead.
private struct HelpSheet<Content: View>: View {
    @Environment(\.dismiss) private var dismiss
    @ViewBuilder let content: (@escaping () -> Void) -> Content

    var body: some View {
        #if os(macOS)
            content({ dismiss() })
                .frame(width: 560, height: 560)
        #else
            content({ dismiss() })
        #endif
    }
}
