// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Grouping saved chats by how recent they are. Pure, so the boundaries can be
// tested against a fixed `now` rather than against whatever time the suite
// happens to run at -- the bug this shape prevents is a list that groups
// correctly all day and wrongly at ten to midnight.

import Foundation

enum RecentsGrouping {

    /// One heading and the conversations under it.
    struct Section: Identifiable, Equatable {
        var id: String { title }
        let title: String
        let items: [ConversationSummary]
    }

    static let today = "Today"
    static let yesterday = "Yesterday"
    static let previousWeek = "Previous 7 days"
    static let older = "Older"

    /// Group conversations into date sections, newest section first.
    ///
    /// Sections are by *calendar day*, not by elapsed hours: a chat from
    /// 23:59 last night is "Yesterday" at 00:05 this morning, six minutes
    /// later, which is what a reader means by the word. Comparing elapsed
    /// time instead would call it "Today" for another 24 hours.
    ///
    /// Empty sections are dropped, so the list never shows a heading with
    /// nothing under it.
    ///
    /// :param summaries: Conversations, already newest-first.
    /// :param now: The moment to measure from.
    /// :param calendar: The calendar defining day boundaries.
    /// :returns: Non-empty sections, in Today/Yesterday/week/older order.
    static func group(
        _ summaries: [ConversationSummary],
        now: Date = Date(),
        calendar: Calendar = .current
    ) -> [Section] {
        var buckets: [String: [ConversationSummary]] = [:]
        for summary in summaries {
            buckets[title(for: summary.updatedAt, now: now, calendar: calendar), default: []]
                .append(summary)
        }
        return [today, yesterday, previousWeek, older]
            .compactMap { title in
                guard let items = buckets[title], !items.isEmpty else { return nil }
                return Section(title: title, items: items)
            }
    }

    /// Which section a date belongs to.
    ///
    /// A date in the future -- a clock change, or a file copied from a device
    /// running ahead -- counts as today rather than falling through to
    /// "Older", where it would sort above nothing and confuse the reader.
    static func title(for date: Date, now: Date, calendar: Calendar = .current) -> String {
        let start = calendar.startOfDay(for: date)
        let reference = calendar.startOfDay(for: now)
        let days = calendar.dateComponents([.day], from: start, to: reference).day ?? 0

        switch days {
        case ..<1: return today
        case 1: return yesterday
        // Seven days back inclusive: the seventh day is still "previous 7
        // days", which is where a reader counting on their fingers puts it.
        case 2...7: return previousWeek
        default: return older
        }
    }
}
