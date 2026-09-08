// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// "Export as Markdown" -- the open conversation, through the system share
// sheet.
//
// It shares the *open* conversation rather than offering the action on every
// row in the list, and that is a deliberate narrowing of the plan. A row
// carries only a ConversationSummary; exporting one would mean reading its
// file to build the share item, and `ShareLink` needs that item up front, so
// every context menu that merely *opened* would hit the disk on the main
// actor. The chat on screen is already in memory, which is where the share
// sheet can be offered for free.

import CoreTransferable
import SwiftUI
import UniformTypeIdentifiers

/// A conversation rendered for sharing, with a filename the receiving app
/// can use.
struct ExportedConversation: Transferable {
    let markdown: String
    let filename: String

    static var transferRepresentation: some TransferRepresentation {
        // Plain text rather than a Markdown UTType: every destination that
        // matters (Mail, Notes, Files, Messages) accepts it, and the `.md`
        // extension is what tells an editor how to read it.
        DataRepresentation(exportedContentType: .plainText) { exported in
            Data(exported.markdown.utf8)
        }
        .suggestedFileName { $0.filename }
    }
}

struct ExportConversationButton: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if let conversation = exportable {
            ShareLink(
                item: ExportedConversation(
                    markdown: ConversationMarkdown.render(conversation),
                    filename: ConversationMarkdown.filename(for: conversation)),
                preview: SharePreview(conversation.title)
            ) {
                Label("Export as Markdown", systemImage: "square.and.arrow.up")
            }
        }
    }

    /// The conversation to share: the saved one when there is one, otherwise
    /// whatever is on screen, so a chat can be exported before its first turn
    /// has finished being written to disk.
    private var exportable: Conversation? {
        if let active = model.activeConversation { return active }
        guard !model.turns.isEmpty else { return nil }
        return Conversation(
            title: ConversationTitle.title(for: model.turns[0].question),
            turns: model.turns)
    }
}
