// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.
//
// Help text, as data rather than as view code.
//
// Settings offers a dozen controls whose names are honest but not
// self-explanatory -- "Greedy decoding" and "Passages per work" mean nothing
// to a reader who has not built a retrieval system. The explanations belong
// somewhere they can be read in full, checked by a test, and revised without
// touching layout.
//
// Every number quoted here was measured on real hardware rather than assumed;
// where behaviour is a guess, the text says so. See
// analysis/SYNTHESIS_TUNING_NOTES.md for the measurements.

import Foundation

/// One help page.
public struct HelpTopic: Identifiable, Sendable, Hashable {
    public let id: String
    /// Shown in the topic list and as the page title.
    public let title: String
    /// SF Symbol for the list row.
    public let symbol: String
    /// One line, shown under the title in the list.
    public let summary: String
    public let sections: [HelpSection]

    public init(
        id: String, title: String, symbol: String, summary: String, sections: [HelpSection]
    ) {
        self.id = id
        self.title = title
        self.symbol = symbol
        self.summary = summary
        self.sections = sections
    }
}

/// A heading and its paragraphs. Paragraphs are rendered as Markdown, so
/// `**bold**` and `*italic*` work and nothing else needs to.
public struct HelpSection: Identifiable, Sendable, Hashable {
    public var id: String { heading }
    public let heading: String
    public let paragraphs: [String]

    public init(heading: String, paragraphs: [String]) {
        self.heading = heading
        self.paragraphs = paragraphs
    }
}

public enum HelpContent {

    /// Every topic, in the order the list shows them: what the app does
    /// first, then the controls, then the things that go wrong.
    public static let topics: [HelpTopic] = [
        howItWorks, answerEngines, synthesis, search, whenAnswersStop, privacy,
    ]

    /// The topic the Synthesis section's info button opens.
    public static let synthesisTopicID = "synthesis"

    public static func topic(id: String) -> HelpTopic? {
        topics.first { $0.id == id }
    }

    // MARK: - Topics

    static let howItWorks = HelpTopic(
        id: "how-it-works",
        title: "How answers are made",
        symbol: "book.closed",
        summary: "Search first, then write from what was found",
        sections: [
            HelpSection(
                heading: "Two steps, always in this order",
                paragraphs: [
                    "When you ask a question, the app first **searches the corpus** for passages that match it. Only then does it ask a language model to write an answer, and the model is shown nothing except those passages.",
                    "This is the whole design. The model is not answering from what it learned during training; it is reading a handful of pages that were just pulled off the shelf and reporting what they say. That is why an answer can cite a work and a page, and why it will tell you when the passages do not cover your question.",
                ]),
            HelpSection(
                heading: "Why answers sometimes miss the obvious",
                paragraphs: [
                    "If the search does not find the right passage, no amount of model quality will rescue the answer -- the model never sees the page you had in mind. When an answer seems to ignore something you know is in the book, open **Source passages** under the answer and look at what it was actually given.",
                    "Passages that reached the model are marked. The others were found but did not fit, which the next page explains.",
                ]),
        ])

    static let answerEngines = HelpTopic(
        id: "engines",
        title: "Answer engines",
        symbol: "cpu",
        summary: "On-device, Private Cloud, worker, or none",
        sections: [
            HelpSection(
                heading: "On-device",
                paragraphs: [
                    "Apple's built-in model, running on this device. **Nothing leaves the phone** -- no network, no account, no record anywhere else. It works in airplane mode.",
                    "Its limit is size. The model is small, and it can read about 4,000 tokens at once, which in practice is ten short passages. Answers are shorter and plainer than the alternatives, and it occasionally repeats itself.",
                    "This is the default, and it is the point of the app.",
                ]),
            HelpSection(
                heading: "Private Cloud",
                paragraphs: [
                    "Apple's larger model, running on Apple's Private Cloud Compute servers. Your question and the passages are sent to Apple under their privacy guarantees; they are not sent to us, and we never see them.",
                    "It reads about 32,000 tokens -- eight times as much -- so it gets twelve full-length passages instead of ten short ones, and it writes noticeably better prose.",
                    "Two costs. It needs a network connection, and it draws on your iCloud allowance. There is also a content filter you cannot turn off, which is the next page's subject.",
                ]),
            HelpSection(
                heading: "Worker",
                paragraphs: [
                    "A server you run yourself, set under **Worker** in Settings. Useful if you have a machine with a large model on it; irrelevant otherwise.",
                ]),
            HelpSection(
                heading: "Passages only",
                paragraphs: [
                    "No answer is written at all -- you get the search results and read them yourself. Faster, and entirely free of any model's interpretation. A good choice when you want the text rather than a summary of it.",
                ]),
        ])

    static let synthesis = HelpTopic(
        id: synthesisTopicID,
        title: "Synthesis settings",
        symbol: "flask",
        summary: "Temperature, decoding, instructions, passage limits",
        sections: [
            HelpSection(
                heading: "These change the next answer",
                paragraphs: [
                    "Nothing here rewrites an answer you already have. Each setting applies from your next question onwards, and every answer records the settings that produced it.",
                    "If you change several at once and the result gets worse, **Reset synthesis to defaults** puts all of them back.",
                ]),
            HelpSection(
                heading: "Temperature",
                paragraphs: [
                    "How much the model varies its wording. At **0** it always picks the most likely next word, so the same question gives the same answer. Higher values let it choose less obvious words.",
                    "The default is **0.2** -- low, but deliberately not zero. At exactly zero these models can fall into loops, repeating a phrase over and over, and it happens most when several passages come from the same book. A little variation breaks the loop without inviting the model to embroider.",
                    "Above about 0.5 answers start drifting from the passages toward the model's own phrasing, which is the opposite of what this app is for.",
                ]),
            HelpSection(
                heading: "Greedy decoding",
                paragraphs: [
                    "Always take the single most likely next word. This is temperature 0 by another name, and it overrides the temperature slider, which greys out while it is on.",
                    "Worth turning on when you want to compare two other settings fairly, since it removes randomness as an explanation for any difference you see. Worth leaving off the rest of the time, for the looping reason above.",
                ]),
            HelpSection(
                heading: "Instructions",
                paragraphs: [
                    "Which set of directions the model is given before it sees your question.",
                    "**Guide** is the default, written for the small models this app uses. It asks for two or three paragraphs of plain prose and tells the model to draw only on the passages.",
                    "**Worker parity** is the original wording, written for the much larger model on the server. It is kept because it is useful for comparison -- but on the on-device model it produces very short answers. Asking a small model to \"be concise\" reliably gets you one sentence, even when the passages contain a whole story.",
                ]),
            HelpSection(
                heading: "Passages per work",
                paragraphs: [
                    "How many passages from the *same* book may be used in one answer. Search often returns five chunks of one translation; without a limit the model sees the same voice repeatedly and begins to echo it.",
                    "**Engine default** is the right setting for almost everyone: 2 for on-device, 4 for Private Cloud, chosen for each model's tolerance.",
                    "Raise it when a question is genuinely about one book and you want depth rather than breadth. Lower it to force variety across authors. A capped passage does not free its slot for another book, so raising this can mean fewer works in the answer, not more.",
                ]),
            HelpSection(
                heading: "Permissive guardrails",
                paragraphs: [
                    "On-device only; it has no effect on Private Cloud, which offers no such control.",
                    "Apple checks both your question and the model's answer against a content filter. Classic literature trips it more than you would expect -- scripture, Dante's hell, a diary of the Great Fire. This setting relaxes that check for the on-device model.",
                    "It does not disable safety entirely. Apple's model keeps its own judgement and may still decline. The passages themselves are never filtered -- you can always read them yourself.",
                ]),
        ])

    static let search = HelpTopic(
        id: "search",
        title: "Search settings",
        symbol: "magnifyingglass",
        summary: "How many passages, and how close a match",
        sections: [
            HelpSection(
                heading: "Results",
                paragraphs: [
                    "How many passages the search returns. This is not how many the model reads -- it reads as many as fit its context window, best first.",
                    "Raising it gives you more to browse under **Source passages** and gives the model a deeper pool to draw the best from. It does not make answers longer.",
                ]),
            HelpSection(
                heading: "Min score",
                paragraphs: [
                    "Discard matches weaker than this. Raise it when answers keep drawing on passages that merely share a word with your question; lower it when a search comes back empty.",
                ]),
            HelpSection(
                heading: "Semantic floor",
                paragraphs: [
                    "The corpus is searched two ways at once: by meaning, and by exact wording. Exact wording is what finds a phrase like \"pillar of salt\" when a purely meaning-based search would drift to related themes.",
                    "This floor is the minimum meaning-based similarity a word-match must also clear, so that sharing a rare word is not on its own enough to be called a result.",
                ]),
            HelpSection(
                heading: "Corpus scope",
                paragraphs: [
                    "Narrowing to a genre is the most effective setting on this page. An unscoped search spreads a small context window across every book in the library; narrowing to *sacred texts* or *diaries* spends all of it where the answer actually is.",
                    "Scope is remembered between launches, deliberately -- it is a lens you chose, not a preference to be reset.",
                ]),
        ])

    static let whenAnswersStop = HelpTopic(
        id: "interruptions",
        title: "When an answer stops early",
        symbol: "exclamationmark.triangle",
        summary: "Content filters, refusals, and what to do",
        sections: [
            HelpSection(
                heading: "\"The content guardrail stopped the answer partway\"",
                paragraphs: [
                    "Apple's content filter watches the answer as it is written and can halt it mid-sentence. What had been written is kept and shown; the rest never arrives.",
                    "This is not about you, and not about the app. It is a filter applied to centuries-old literature: an eyewitness account of the Great Fire of London stops at the point where the diarist records who was blamed for it. Scripture stops at the destruction of a city.",
                    "**On Private Cloud there is no setting that prevents this** -- Apple exposes no control over it. What you can do: ask again, since the filter is inconsistent and often lets the same question through on a second attempt; switch to **On-device**, which is more permissive and, with **Permissive guardrails** on, more permissive still; or read the passages directly, which are never filtered.",
                ]),
            HelpSection(
                heading: "\"The model declined to answer\"",
                paragraphs: [
                    "The filter rejected the passages before writing began, so there is no partial answer. The same remedies apply, and the passages are still below, unfiltered.",
                ]),
            HelpSection(
                heading: "\"No passage carried enough text\"",
                paragraphs: [
                    "The search found nothing usable. Try different wording, lower **Min score**, or widen the corpus scope.",
                ]),
            HelpSection(
                heading: "An answer that repeats itself",
                paragraphs: [
                    "Usually several passages from one book, with the model echoing them. Lower **Passages per work**, or raise **Temperature** slightly if it is at zero.",
                ]),
        ])

    static let privacy = HelpTopic(
        id: "privacy",
        title: "What leaves this device",
        symbol: "lock",
        summary: "Short answer: nothing, unless you choose it",
        sections: [
            HelpSection(
                heading: "By default, nothing",
                paragraphs: [
                    "The books, the search index and the model all live on this device. With the **On-device** engine the app works in airplane mode, and no question you ask is transmitted anywhere.",
                    "Your conversations are stored on this device only. They are not backed up to iCloud, not sent to us, and not sent to anyone else.",
                ]),
            HelpSection(
                heading: "If you choose Private Cloud",
                paragraphs: [
                    "Your question and the selected passages go to Apple's Private Cloud Compute, under Apple's privacy guarantees. They do not come to us -- we operate no servers in that path and could not see them if we wanted to.",
                    "This is per-answer and entirely your choice. Switching back to On-device stops it immediately.",
                ]),
            HelpSection(
                heading: "If you set a worker",
                paragraphs: [
                    "Your question and passages go to the address you entered, which is a machine you chose and control. The app has no default worker and contacts nothing unless you fill that field in.",
                ]),
            HelpSection(
                heading: "No analytics",
                paragraphs: [
                    "The app collects nothing, tracks nothing, and contains no advertising or analytics code of any kind.",
                ]),
        ])
}
