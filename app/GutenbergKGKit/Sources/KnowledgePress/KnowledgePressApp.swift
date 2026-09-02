// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The Knowledge Press — macOS shell.
// Run from app/GutenbergKGKit with:  swift run KnowledgePress
//
// Answers come from Apple Foundation Models when the Mac can run them
// (macOS 26 on Apple silicon); passages still come from the worker, so
// `make up` at the repo root is required either way until the on-device
// corpus pack lands (Phase 2 of analysis/APP_ARCHITECTURE.md).

import AppKit
import KnowledgePressUI
import SwiftUI

@main
struct KnowledgePressApp: App {
    @State private var model = AppModel()

    init() {
        // Running via `swift run` (no app bundle): become a regular foreground
        // app so the window appears and takes focus.
        NSApplication.shared.setActivationPolicy(.regular)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    var body: some Scene {
        WindowGroup("The Knowledge Press") {
            MacRootView()
                .environment(model)
                .frame(minWidth: 900, minHeight: 600)
                .task {
                    model.prewarmOnDevice()
                    await model.refreshSidebar()
                }
        }
    }
}
