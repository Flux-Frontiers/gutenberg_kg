// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The list of saved chats, grouped by day and searchable. One component,
// used by the iPad/Mac sidebar now and the iPhone sheet in phase 3 -- the
// rows behave the same in both, which is the point of extracting it.

import SwiftUI

struct ConversationListView: View {
    @Environment(AppModel.self) private var model

    /// Text typed into the search field, owned by whoever presents the list
    /// so the sidebar and a sheet can each site `.searchable` where it
    /// belongs on their platform.
    @Binding var search: String

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

    private func row(_ summary: ConversationSummary) -> some View {
        NavigationLink(value: SidebarItem.conversation(summary.id)) {
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
            }
        }
        .simultaneousGesture(TapGesture().onEnded { onSelect() })
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

    private var renamingBinding: Binding<Bool> {
        Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })
    }
}
