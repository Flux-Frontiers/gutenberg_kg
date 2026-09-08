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
    @State private var confirmingDelete = false

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
                            Button("Delete", systemImage: "trash") {
                                confirmingDelete = true
                            }
                            .disabled(model.activeConversation == nil && model.turns.isEmpty)
                        }
                    }
                    .deleteConversationConfirmation($confirmingDelete)
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

/// iPad: a persistent sidebar of past chats, with the chat itself alongside.
///
/// The tabs are gone. They were the right shape when a chat was a single
/// disposable buffer, but once chats persist the sidebar is what reaches
/// them, and Browse is one row in it rather than half the tab bar.
///
/// Binding `columnVisibility` is what surfaces `NavigationSplitView`'s own
/// toggle (the same reason `MacRootView` binds it): landscape shows both
/// columns, portrait collapses the sidebar to an overlay reachable from the
/// toolbar, exactly as Files and Notes behave.
public struct PadRootView: View {
    @Environment(AppModel.self) private var model
    @State private var columnVisibility = NavigationSplitViewVisibility.automatic
    @State private var selection: SidebarItem? = .chat
    @State private var search = ""
    @State private var showingSettings = false
    @State private var confirmingDelete = false

    public init() {}

    public var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            ConversationSidebar(
                selection: $selection, search: $search,
                onOpenSettings: { showingSettings = true }
            )
            .searchable(text: $search, placement: .sidebar, prompt: "Search chats")
            .navigationSplitViewColumnWidth(min: 260, ideal: 300)
            .popover(isPresented: $showingSettings) {
                NavigationStack {
                    // The sidebar owns engine and scope on this shell, so
                    // Settings does not show a second copy of them.
                    SettingsView(showsEngineAndScope: false)
                        .navigationTitle("Settings")
                        .toolbarTitleDisplayMode(.inline)
                }
                .frame(minWidth: 380, minHeight: 520)
            }
        } detail: {
            NavigationStack {
                detail
                    .toolbarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .primaryAction) {
                            // Also here, not only in the sidebar: in portrait
                            // the sidebar is hidden, and starting a new chat
                            // is too common to cost two taps.
                            Button("New chat", systemImage: "square.and.pencil") {
                                model.newConversation()
                                selection = .chat
                            }
                            .disabled(model.turns.isEmpty)
                        }
                        ToolbarItem(placement: .cancellationAction) {
                            Button("Delete", systemImage: "trash") {
                                confirmingDelete = true
                            }
                            .disabled(model.activeConversation == nil && model.turns.isEmpty)
                        }
                    }
                    .deleteConversationConfirmation($confirmingDelete)
            }
        }
        .onChange(of: selection) { _, item in
            // Choosing a saved chat loads it into the buffer. The selection
            // stays on that row rather than snapping back to `.chat`, so the
            // list keeps showing which conversation is open.
            if case .conversation(let id) = item {
                model.select(id)
            }
        }
        .onChange(of: model.activeConversation?.id) { _, id in
            // The first completed turn creates a conversation, which is the
            // moment its row appears in the list -- move the highlight onto
            // it so the sidebar agrees with the detail column.
            if let id, selection == .chat { selection = .conversation(id) }
        }
    }

    @ViewBuilder
    private var detail: some View {
        switch selection {
        case .browse:
            BrowseView()
        // `nil` is "no row highlighted", which happens after New chat and on
        // a fresh launch; the chat is still what belongs in the detail column.
        case .chat, .conversation, .none:
            ChatView(showsHeader: false)
                .navigationTitle(model.activeConversation?.title ?? "New chat")
        }
    }
}

extension View {
    /// The one confirmation every "delete this chat" control shows.
    ///
    /// Deleting is now irreversible in a way clearing the screen was not --
    /// it removes a file, not a buffer -- so all three call sites ask first,
    /// in the same words.
    @ViewBuilder
    fileprivate func deleteConversationConfirmation(_ presented: Binding<Bool>) -> some View {
        modifier(DeleteConversationConfirmation(presented: presented))
    }
}

private struct DeleteConversationConfirmation: ViewModifier {
    @Environment(AppModel.self) private var model
    @Binding var presented: Bool

    func body(content: Content) -> some View {
        content.confirmationDialog(
            "Delete this conversation?", isPresented: $presented, titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) { model.deleteActiveConversation() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes the questions, answers, and any illustrations. It cannot be undone.")
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
