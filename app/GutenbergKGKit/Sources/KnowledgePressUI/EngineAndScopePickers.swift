// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The two controls that change what a question *means*, extracted from
// SettingsView so the sidebar and the settings screen share one
// implementation rather than two that drift.
//
// Both are the same rows SettingsView always had, moved rather than
// rewritten: the engine picker keeps the onChange that prewarms the
// on-device model and refreshes the worker's model list, because losing
// that would make the first on-device answer slow again for no visible
// reason.

import GutenbergKGKit
import SwiftUI

/// Which engine writes the answer, plus what that choice costs.
struct AnswerEnginePicker: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
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

/// Which part of the corpus a question is asked against.
///
/// This one earns its place in the sidebar. Scope is the single largest lever
/// on answer quality -- unscoped, "circles of Hell" retrieves Les Miserables
/// and Lovecraft next to Dante, because the on-device context budget is spread
/// across every book plus the diaries. A control that consequential should be
/// visible while reading, not three taps away.
struct CorpusScopePicker: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        Picker("Scope", selection: $model.corpus) {
            ForEach(model.corpusOptions, id: \.self) { Text($0).tag($0) }
        }
        .help(
            "all = DocKG + DiaryKG · gutenberg = DocKG only · diary = diaries only · <genre> = one genre"
        )
    }
}
