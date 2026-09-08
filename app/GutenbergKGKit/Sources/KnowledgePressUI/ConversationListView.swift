// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The list of saved chats, grouped by day and searchable. One component,
// used by the iPad/Mac sidebar now and the iPhone sheet in phase 3 -- the
// rows behave the same in both, which is the point of extracting it.

import SwiftUI

struct ConversationListView: View {
    @Environment(AppModel.self) private var model

    /// How a row is activated.
    ///
    /// The one thing the two hosts genuinely disagree about. In a split
    /// view's sidebar a row is a *destination*: it carries a value, the list's
    /// selection binding highlights it, and the detail column follows. In a
    /// sheet there is no detail column and no persistent selection -- a row is
    /// a button that loads the chat and closes the sheet. Everything else
    /// (grouping, search, swipe, rename) is identical, which is why this is a
    /// parameter rather than two components.
    enum Presentation {
        case sidebar
        case sheet
    }

    /// Text typed into the search field, owned by whoever presents the list
    /// so the sidebar and a sheet can each site `.searchable` where it
    /// belongs on their platform.
    @Binding var search: String

    var presentation: Presentation = .sidebar

    /// Called after a row is chosen, so a sheet can dismiss itself. The
    /// sidebar has nothing to do here.
    var onSelect: () -> Void = {}

    @State private var renaming: ConversationSummary?
    @State private var newTitle = ""

    private var sections: [RecentsGrouping.Section] {
        RecentsGrouping.group(filtered)
    }

    /// Title search only.
    ///
    /// Searching the questions inside each chat would mean loading every
    /// conversation to type one character; the summaries carry titles, and a
    /// title *is* the first question, so this already finds most of what a
    /// reader is looking for. Full-text search over answers is its own job.
    private var filtered: [ConversationSummary] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return model.conversations }
        return model.conversations.filter {
            $0.title.localizedCaseInsensitiveContains(query)
        }
    }

    var body: some View {
        ForEach(sections) { section in
            Section(section.title) {
                ForEach(section.items) { summary in
                    row(summary)
                }
            }
        }

        if model.conversations.isEmpty {
            Text("Chats you have will be listed here.")
                .font(.caption)
                .foregroundStyle(.secondary)
        } else if sections.isEmpty {
            Text("No chat matches \"\(search)\".")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private func row(_ summary: ConversationSummary) -> some View {
        Group {
            switch presentation {
            case .sidebar:
                NavigationLink(value: SidebarItem.conversation(summary.id)) {
                    label(summary)
                }
            case .sheet:
                Button {
                    model.select(summary.id)
                    onSelect()
                } label: {
                    label(summary)
                }
                .buttonStyle(.plain)
            }
        }
        .swipeActions(edge: .trailing) {
            Button("Delete", systemImage: "trash", role: .destructive) {
                model.delete(summary.id)
            }
        }
        .contextMenu {
            Button("Rename", systemImage: "pencil") {
                newTitle = summary.title
                renaming = summary
            }
            Button("Delete", systemImage: "trash", role: .destructive) {
                model.delete(summary.id)
            }
        }
        .alert("Rename chat", isPresented: renamingBinding, presenting: renaming) { summary in
            TextField("Title", text: $newTitle)
            Button("Save") { model.rename(summary.id, to: newTitle) }
            Button("Cancel", role: .cancel) {}
        }
    }

    /// A row's contents: the title, and the scope it was asked against.
    private func label(_ summary: ConversationSummary) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(summary.title)
                .lineLimit(2)
            HStack(spacing: 6) {
                if summary.lastCorpus != "all" {
                    Text(summary.lastCorpus)
                        .font(.caption2.monospaced())
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(.tint.opacity(0.15), in: Capsule())
                }
                Text("\(summary.turnCount) \(summary.turnCount == 1 ? "question" : "questions")")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        // The whole row is the target, not just the text: a plain-styled
        // button in a sheet would otherwise only respond on its glyphs.
        .contentShape(Rectangle())
    }

    private var renamingBinding: Binding<Bool> {
        Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })
    }
}
