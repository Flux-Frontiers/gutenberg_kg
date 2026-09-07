// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The two shells. Same chat, same browse, same settings — arranged for the
// screen they are on: a persistent sidebar on the Mac (closest to the
// Streamlit layout it ports), tabs and a settings sheet on iPhone.

import SwiftUI

/// macOS window: settings sidebar + Chat/Browse tabs.
public struct MacRootView: View {
    public init() {}

    public var body: some View {
        NavigationSplitView {
            SettingsView()
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

/// iPhone: Chat and Browse as tabs, settings behind a toolbar button.
///
/// The sidebar does not survive the trip to a phone, so the controls move to
/// a sheet. The corpus/version caption that used to sit under the nav title
/// here now lives only in About (Settings ▸ About) — one home for it,
/// instead of the same line shown twice.
public struct PhoneRootView: View {
    @Environment(AppModel.self) private var model
    @State private var showingSettings = false

    public init() {}

    public var body: some View {
        TabView {
            NavigationStack {
                ChatView(showsHeader: false)
                    .navigationTitle("The Knowledge Press")
                    .toolbarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .primaryAction) {
                            Button("Settings", systemImage: "slider.horizontal.3") {
                                showingSettings = true
                            }
                        }
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Clear", systemImage: "trash") {
                                model.turns.removeAll()
                            }
                            .disabled(model.turns.isEmpty)
                        }
                    }
            }
            .tabItem { Label("Chat", systemImage: "text.bubble") }

            BrowseView()
                .tabItem { Label("Browse", systemImage: "books.vertical") }
        }
        .sheet(isPresented: $showingSettings) {
            NavigationStack {
                SettingsView()
                    .navigationTitle("Settings")
                    .toolbarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Done") { showingSettings = false }
                        }
                    }
            }
        }
    }
}

#if os(iOS)
    import UIKit

    /// The iOS entry point's root: the iPad gets the same permanent sidebar
    /// as the Mac, since a phone-style settings sheet wastes most of the
    /// screen it has; the iPhone keeps the tabs-plus-sheet shell above.
    ///
    /// `MacRootView`'s body is already idiom-agnostic SwiftUI —
    /// `NavigationSplitView` collapses to one column in a compact-width
    /// scene and shows the sidebar in regular width, which is exactly the
    /// portrait/landscape behavior an iPad needs — so this reuses it as-is
    /// rather than duplicating the same layout under a new name.
    public struct AdaptiveRootView: View {
        public init() {}

        public var body: some View {
            if UIDevice.current.userInterfaceIdiom == .pad {
                MacRootView()
            } else {
                PhoneRootView()
            }
        }
    }
#endif
