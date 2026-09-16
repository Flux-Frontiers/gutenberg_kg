// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.
//
// The help browser: a list of topics, each opening a page of prose.
//
// Reached three ways, and the third is the reason this exists. A Help row in
// Settings and, on macOS, a Help menu command both open at the topic list. An
// info button on a Settings section header opens *that section's* topic
// directly -- a reader wondering what "Greedy decoding" means should not have
// to find the answer, and is not going to go looking for a manual.
//
// Content lives in HelpContent.swift so it can be revised, and tested,
// without touching layout.

import SwiftUI

/// The topic list, or one topic when `initialTopicID` names one.
public struct HelpView: View {
    /// Open straight to this topic instead of the list. The section info
    /// buttons pass one; the Help row does not.
    let initialTopicID: String?
    /// Called by the Done button. Nil hides it -- the macOS window is closed
    /// by its own title bar and needs no button of ours.
    let onDone: (() -> Void)?

    @State private var path: [HelpTopic] = []

    public init(initialTopicID: String? = nil, onDone: (() -> Void)? = nil) {
        self.initialTopicID = initialTopicID
        self.onDone = onDone
    }

    public var body: some View {
        NavigationStack(path: $path) {
            List(HelpContent.topics) { topic in
                NavigationLink(value: topic) {
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(topic.title)
                            Text(topic.summary)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: topic.symbol)
                            .foregroundStyle(.tint)
                    }
                }
            }
            .navigationTitle("Help")
            #if !os(macOS)
                .navigationBarTitleDisplayMode(.inline)
            #endif
            .navigationDestination(for: HelpTopic.self) { HelpTopicView(topic: $0) }
            // Inside the NavigationStack, or it never reaches the navigation
            // bar: a toolbar attached outside has no bar to attach to.
            .toolbar {
                if let onDone {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done", action: onDone)
                    }
                }
            }
        }
        .task {
            // Pushed rather than shown in place of the list, so Back still
            // reaches the other topics -- someone who arrived asking about
            // one control often has a second question.
            if let id = initialTopicID, let topic = HelpContent.topic(id: id) {
                path = [topic]
            }
        }
    }
}

/// One topic, rendered as headings and paragraphs.
struct HelpTopicView: View {
    let topic: HelpTopic

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text(topic.summary)
                    .font(.callout)
                    .foregroundStyle(.secondary)

                ForEach(topic.sections) { section in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(section.heading)
                            .font(.headline)
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, text in
                            // Markdown so **bold** works; a paragraph that
                            // fails to parse is shown verbatim rather than
                            // dropped, since help that silently vanishes is
                            // worse than help that looks plain.
                            Text((try? AttributedString(markdown: text)) ?? AttributedString(text))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            .padding()
            .frame(maxWidth: 640, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .navigationTitle(topic.title)
        #if !os(macOS)
            .navigationBarTitleDisplayMode(.inline)
        #endif
        .textSelection(.enabled)
    }
}

/// The ⓘ button that sits on a Settings section header.
///
/// Small and unobtrusive by design: it answers a question for the reader who
/// has one without implying the section needs explaining before use.
struct HelpSectionHeader: View {
    let title: String
    let topicID: String
    @Binding var presentedTopicID: String?

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            Button {
                presentedTopicID = topicID
            } label: {
                Image(systemName: "info.circle")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.tint)
            .accessibilityLabel("About \(title)")
        }
    }
}
