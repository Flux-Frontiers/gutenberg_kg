// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The sidebar column on iPad and Mac: start a chat, browse the corpus, set
// the two controls that change what a question means, and reach every chat
// you have had.
//
// Settings does not live here. A full settings form pinned open beside what
// you are reading is what the iPad shell deliberately moved away from; the
// sidebar carries the two controls worth seeing per chat and a button to the
// rest.

import SwiftUI

/// What the detail column is showing.
enum SidebarItem: Hashable {
    /// The active conversation, or an empty one waiting for a question.
    case chat
    case browse
    /// A saved chat, selected from the list.
    case conversation(UUID)
}

struct ConversationSidebar: View {
    @Environment(AppModel.self) private var model
    @Binding var selection: SidebarItem?
    @Binding var search: String

    /// Presenting Settings is the shell's job on iOS -- a popover anchored
    /// wherever the shell wants it -- so the sidebar only reports the tap.
    /// Unused on macOS, where the footer is a `SettingsLink` to the standard
    /// Settings window instead.
    var onOpenSettings: () -> Void = {}

    var body: some View {
        List(selection: $selection) {
            Section {
                Button("New chat", systemImage: "square.and.pencil") {
                    model.newConversation()
                    selection = .chat
                }
                // A new chat over an empty one would do nothing; saying so
                // is better than a button that silently ignores a tap.
                .disabled(model.turns.isEmpty)

                NavigationLink(value: SidebarItem.browse) {
                    Label("Browse the corpus", systemImage: "books.vertical")
                }
            }

            Section("🤖 Answers") {
                AnswerEnginePicker()
            }

            Section("📖 Corpus") {
                CorpusScopePicker()
            }

            ConversationListView(search: $search)
        }
        .navigationTitle("The Knowledge Press")
        .safeAreaInset(edge: .bottom) {
            HStack {
                #if os(macOS)
                    // The platform-standard route to Settings, which also
                    // means Cmd-comma and the app menu reach the same window.
                    SettingsLink {
                        Label("Settings", systemImage: "slider.horizontal.3")
                    }
                #else
                    Button("Settings", systemImage: "slider.horizontal.3", action: onOpenSettings)
                #endif
                Spacer()
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(.bar)
        }
    }
}
