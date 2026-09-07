// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Siri and Shortcuts support: "Ask The Knowledge Press <question>" runs the
// same retrieval + synthesis path as typing it into chat.
//
// `openAppWhenRun` runs `perform()` in-process rather than in an extension,
// because answering needs the live `AppModel` the chat UI already has open —
// the on-device embedder, the installed corpus packs, whichever answer
// engine Settings has selected. There is no other way to reach that `@State`
// instance from an intent, so this posts a notification and `AppModel`
// (see its `init()`) is the one live thing guaranteed to be listening by the
// time `openAppWhenRun` has finished bringing the app to the foreground.

import AppIntents
import Foundation

public struct AskKnowledgePressIntent: AppIntent {
    public static let title: LocalizedStringResource = "Ask The Knowledge Press"
    public static let description = IntentDescription(
        "Search the installed corpus and get an answer, the same way the chat does."
    )
    public static let openAppWhenRun: Bool = true

    @Parameter(title: "Question", requestValueDialog: "What do you want to ask?")
    public var question: String

    public init() {
        question = ""
    }

    public init(question: String) {
        self.question = question
    }

    public func perform() async throws -> some IntentResult {
        NotificationCenter.default.post(
            name: .askKnowledgePress, object: nil, userInfo: ["question": question])
        return .result()
    }
}

/// Surfaces `AskKnowledgePressIntent` to Siri and the Shortcuts app.
///
/// One shortcut, not per-genre ones — corpus scope is already a Settings
/// choice, and multiplying shortcuts by 21 genres would clutter Shortcuts
/// for a distinction Siri phrasing cannot express cleanly anyway.
///
/// The phrase cannot embed `$question` — App Intents only allows an
/// `AppEntity`/`AppEnum` parameter inside an invocation phrase, since Siri
/// needs a bounded vocabulary to match against, and free text has none.
/// Saying "Ask The Knowledge Press" triggers the intent with `question`
/// still unset, and its `requestValueDialog` prompts for it by voice.
public struct KnowledgePressShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AskKnowledgePressIntent(),
            phrases: [
                "Ask \(.applicationName)",
                "Ask \(.applicationName) a question",
            ],
            shortTitle: "Ask a Question",
            systemImageName: "text.bubble"
        )
    }
}

extension Notification.Name {
    /// Carries `["question": String]` in `userInfo`. Posted by
    /// `AskKnowledgePressIntent.perform()`, observed by `AppModel`.
    public static let askKnowledgePress = Notification.Name("askKnowledgePress")
}
