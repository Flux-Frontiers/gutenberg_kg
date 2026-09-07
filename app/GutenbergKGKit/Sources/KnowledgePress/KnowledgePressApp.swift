// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The Knowledge Press — macOS shell.
// Run from app/GutenbergKGKit with:  swift run KnowledgePress
//
// Answers come from Apple Foundation Models when the Mac can run them
// (macOS 26 on Apple silicon), and passages from the corpus packs when they
// are installed — `gutenkg export-swift` builds them. With no packs the app
// falls back to the worker, so `make up` at the repo root is needed then.

import AppKit
import KnowledgePressUI
import SwiftUI

@main
struct KnowledgePressApp: App {
    @State private var model = AppModel()
    @Environment(\.openWindow) private var openWindow

    init() {
        // Running via `swift run` (no app bundle): become a regular foreground
        // app so the window appears and takes focus.
        NSApplication.shared.setActivationPolicy(.regular)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    var body: some Scene {
        WindowGroup("The Knowledge Press") {
            SplashOverlay {
                MacRootView()
                    .environment(model)
            }
            .frame(minWidth: 900, minHeight: 600)
            .task {
                model.prewarmOnDevice()
                await model.loadCorpusPacks()
                await model.refreshSidebar()
            }
        }
        .commands {
            // Replaces the system-supplied "About KnowledgePress" (which
            // would otherwise show a generic panel with no build-specific
            // info) with the same AboutView the iOS row presents.
            CommandGroup(replacing: .appInfo) {
                Button("About The Knowledge Press") { openWindow(id: "about") }
            }
        }

        Window("About The Knowledge Press", id: "about") {
            AboutView()
                .environment(model)
        }
        .windowResizability(.contentSize)
    }
}
