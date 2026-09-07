// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Three shells, one Settings screen. Same chat, same browse, same settings —
// arranged for the screen they are on: a collapsible sidebar on the Mac
// (closest to the Streamlit layout it ports), tabs and a settings popover on
// iPad, tabs and a settings sheet on iPhone.

import SwiftUI

/// macOS window: settings sidebar + Chat/Browse tabs.
///
/// `columnVisibility` starts `.automatic` — macOS's own default — rather
/// than forcing it open or shut; the point of switching to the explicit
/// binding is only to make `NavigationSplitView`'s built-in sidebar toggle
/// appear in the toolbar, so a Mac window can hide the sidebar the same way
/// Xcode, Mail, and Notes do, without changing the split view's own default.
public struct MacRootView: View {
    @State private var columnVisibility = NavigationSplitViewVisibility.automatic

    public init() {}

    public var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
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

/// iPad: the same tabs-plus-button shell as the iPhone, but Settings opens
/// as a floating popover anchored to the button instead of a sheet.
///
/// This used to reuse `MacRootView`'s permanent sidebar — technically fine
/// (`NavigationSplitView` collapses correctly at compact width), but a
/// full settings form pinned open the rest of the time reads as heavy on a
/// screen this size, next to nothing you're actually reading. A popover is
/// the deliberately lighter middle ground: it opens over the content
/// instead of pushing it aside, and closes with a tap outside rather than
/// a "Done" button.
public struct PadRootView: View {
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
                            .popover(isPresented: $showingSettings) {
                                NavigationStack {
                                    SettingsView()
                                        .navigationTitle("Settings")
                                        .toolbarTitleDisplayMode(.inline)
                                }
                                .frame(minWidth: 380, minHeight: 520)
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
    }
}

#if os(iOS)
    import UIKit

    /// The iOS entry point's root: `PadRootView` on the iPad, `PhoneRootView`
    /// on the iPhone. See each type's own doc comment for why they differ.
    public struct AdaptiveRootView: View {
        public init() {}

        public var body: some View {
            if UIDevice.current.userInterfaceIdiom == .pad {
                PadRootView()
            } else {
                PhoneRootView()
            }
        }
    }
#endif
