// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The Knowledge Press — macOS thin client (Phase 1 of analysis/APP_ARCHITECTURE.md).
// Run from app/GutenbergKGKit with:  swift run KnowledgePress
// (needs a worker on http://localhost:8000 — `make up` at repo root).

import AppKit
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
            RootView()
                .environment(model)
                .frame(minWidth: 900, minHeight: 600)
                .task {
                    await model.refreshSidebar()
                }
        }
    }
}

/// Sidebar (settings) + Chat/Browse tabs — the macOS translation of the
/// Streamlit layout: the settings sidebar is persistent, like chat.py's.
struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationSplitView {
            SettingsSidebarView()
                .navigationSplitViewColumnWidth(min: 260, ideal: 300)
        } detail: {
            TabView {
                ChatView()
                    .tabItem { Label("Chat", systemImage: "text.bubble") }
                BrowseView()
                    .tabItem { Label("Browse", systemImage: "books.vertical") }
            }
        }
    }
}
