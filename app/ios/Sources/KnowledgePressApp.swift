// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The Knowledge Press — iPhone shell.
//
// Everything except this file lives in the KnowledgePressUI package target,
// shared with the Mac app. Answers are written by Apple Foundation Models on
// the device itself; passages come from the worker until an on-device corpus
// pack is installed (Phase 2 of analysis/APP_ARCHITECTURE.md).

import KnowledgePressUI
import SwiftUI

@main
struct KnowledgePressApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            PhoneRootView()
                .environment(model)
                .task {
                    // Load model weights while the reader is still reading the
                    // suggestions, so the first answer starts without a pause.
                    model.prewarmOnDevice()
                    await model.refreshSidebar()
                }
        }
    }
}
