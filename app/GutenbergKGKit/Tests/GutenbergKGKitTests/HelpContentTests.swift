// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.
//
// Help text is prose, and prose is not something a test can judge. What a
// test can do is catch the ways help rots: a topic id that no longer resolves
// so an info button opens nothing, a page that quietly loses its body, a
// Markdown typo that renders as literal asterisks, and -- the one that
// matters most -- a promise about privacy or safety that stops being true.

import Foundation
import Testing

@testable import KnowledgePressUI

@Suite struct HelpContentTests {

    @Test func everyTopicHasContent() {
        #expect(!HelpContent.topics.isEmpty)
        for topic in HelpContent.topics {
            #expect(!topic.title.isEmpty, "\(topic.id) has no title")
            #expect(!topic.summary.isEmpty, "\(topic.id) has no summary")
            #expect(!topic.symbol.isEmpty, "\(topic.id) has no symbol")
            #expect(!topic.sections.isEmpty, "\(topic.id) has no sections")
            for section in topic.sections {
                #expect(!section.heading.isEmpty, "\(topic.id) has an unnamed section")
                #expect(!section.paragraphs.isEmpty, "\(topic.id)/\(section.heading) is empty")
                for paragraph in section.paragraphs {
                    #expect(
                        paragraph.count > 20,
                        "\(topic.id)/\(section.heading) has a paragraph too short to be one")
                }
            }
        }
    }

    @Test func topicIDsAreUniqueAndResolvable() {
        let ids = HelpContent.topics.map(\.id)
        #expect(Set(ids).count == ids.count, "duplicate topic id")
        for id in ids {
            #expect(HelpContent.topic(id: id) != nil)
        }
        #expect(HelpContent.topic(id: "no-such-topic") == nil)
    }

    /// The info buttons pass literal ids. A renamed topic must not leave one
    /// opening an empty page.
    @Test func idsReferencedByTheUIResolve() {
        for id in [HelpContent.synthesisTopicID, "engines", "search"] {
            #expect(HelpContent.topic(id: id) != nil, "Settings references missing topic '\(id)'")
        }
    }

    /// Paragraphs are rendered as Markdown. An unbalanced `**` shows up as
    /// asterisks in the shipped app, which no one would notice in review.
    @Test func markdownParsesAndIsBalanced() throws {
        for topic in HelpContent.topics {
            for section in topic.sections {
                for paragraph in section.paragraphs {
                    #expect(
                        paragraph.components(separatedBy: "**").count % 2 == 1,
                        "unbalanced ** in \(topic.id)/\(section.heading)")
                    #expect(
                        (try? AttributedString(markdown: paragraph)) != nil,
                        "unparseable Markdown in \(topic.id)/\(section.heading)")
                }
            }
        }
    }

    /// Every control in the Synthesis section is explained. Adding a knob
    /// without adding a paragraph is the failure this catches, and it is the
    /// whole reason these pages exist.
    @Test func synthesisTopicCoversEveryControl() throws {
        let topic = try #require(HelpContent.topic(id: HelpContent.synthesisTopicID))
        let text = topic.sections.map(\.heading).joined(separator: "\n")
        for control in [
            "Temperature", "Greedy decoding", "Instructions", "Passages per work",
            "Permissive guardrails",
        ] {
            #expect(text.contains(control), "Synthesis help does not explain '\(control)'")
        }
    }

    /// The privacy page makes claims the app has to keep. If the app ever
    /// starts collecting anything, this test should be the thing that stops
    /// the claim shipping unchanged.
    @Test func privacyPageClaimsMatchTheApp() throws {
        let topic = try #require(HelpContent.topic(id: "privacy"))
        let text = topic.sections.flatMap(\.paragraphs).joined(separator: " ")
        #expect(text.contains("collects nothing"))
        #expect(text.contains("airplane mode"))
        // Private Cloud sends data to Apple. Saying otherwise would be a lie,
        // so the page must keep saying it.
        #expect(text.contains("Apple's Private Cloud Compute"))
    }

    /// The guardrail page is the one readers reach when something failed. It
    /// must not promise a setting that does not exist: Private Cloud Compute
    /// exposes no guardrail control, on-device does.
    @Test func guardrailPageIsHonestAboutWhatCannotBeChanged() throws {
        let topic = try #require(HelpContent.topic(id: "interruptions"))
        let text = topic.sections.flatMap(\.paragraphs).joined(separator: " ")
        #expect(text.contains("no setting that prevents this"))
        #expect(text.contains("On-device"))
    }

    /// Help talks about the same engines the picker offers.
    @Test func engineTopicNamesEveryEngine() throws {
        let topic = try #require(HelpContent.topic(id: "engines"))
        let headings = topic.sections.map(\.heading).joined(separator: "\n")
        for engine in AnswerEngine.allCases {
            #expect(
                headings.contains(engine.label),
                "help does not cover the '\(engine.label)' engine")
        }
    }
}
