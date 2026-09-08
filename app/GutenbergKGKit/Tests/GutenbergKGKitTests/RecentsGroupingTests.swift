// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Where the day boundaries fall. Every case fixes `now`, because the defect
// this guards against is a list that groups correctly at noon and wrongly at
// ten to midnight -- a suite that used the real clock would only catch it on
// an unlucky night.

import Foundation
import Testing

@testable import KnowledgePressUI

@Suite("Recents grouping")
struct RecentsGroupingTests {

    /// Fixed calendar and clock: 2026-09-07 at 10:00, UTC.
    private var calendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    private var now: Date {
        calendar.date(from: DateComponents(year: 2026, month: 9, day: 7, hour: 10))!
    }

    private func at(_ month: Int, _ day: Int, _ hour: Int = 12, _ minute: Int = 0) -> Date {
        calendar.date(
            from: DateComponents(year: 2026, month: month, day: day, hour: hour, minute: minute))!
    }

    private func summary(_ title: String, _ updated: Date) -> ConversationSummary {
        ConversationSummary(
            id: UUID(), title: title, createdAt: updated, updatedAt: updated,
            turnCount: 1, lastEngine: .onDevice, lastCorpus: "all")
    }

    private func title(_ date: Date) -> String {
        RecentsGrouping.title(for: date, now: now, calendar: calendar)
    }

    @Test("a chat from earlier today is Today")
    func earlierTodayIsToday() {
        #expect(title(at(9, 7, 9)) == RecentsGrouping.today)
        #expect(title(at(9, 7, 0, 1)) == RecentsGrouping.today)
    }

    @Test("23:59 yesterday is Yesterday, not Today")
    func lateLastNightIsYesterday() {
        // Six minutes before `now` would be "today" by elapsed time. By
        // calendar day -- which is what the word means -- it is yesterday.
        #expect(title(at(9, 6, 23, 59)) == RecentsGrouping.yesterday)
        #expect(title(at(9, 6, 0, 0)) == RecentsGrouping.yesterday)
    }

    @Test("two days back begins the previous 7 days")
    func twoDaysBackIsTheWeek() {
        #expect(title(at(9, 5)) == RecentsGrouping.previousWeek)
    }

    @Test("exactly seven days old is still the previous 7 days")
    func sevenDaysIsInclusive() {
        #expect(title(at(8, 31)) == RecentsGrouping.previousWeek)
    }

    @Test("eight days old is Older")
    func eightDaysIsOlder() {
        #expect(title(at(8, 30)) == RecentsGrouping.older)
        #expect(title(at(1, 1)) == RecentsGrouping.older)
    }

    @Test("a timestamp in the future counts as today rather than falling to Older")
    func futureCountsAsToday() {
        // A clock change or a file from a device running ahead. "Older" would
        // be actively wrong, and it would sort at the bottom.
        #expect(title(at(9, 8)) == RecentsGrouping.today)
    }

    @Test("empty input produces no sections at all")
    func emptyGivesNoSections() {
        #expect(RecentsGrouping.group([], now: now, calendar: calendar).isEmpty)
    }

    @Test("sections come back in order, and empty ones are dropped")
    func sectionsAreOrderedAndDense() {
        let summaries = [
            summary("today", at(9, 7, 9)),
            summary("last night", at(9, 6, 23, 59)),
            summary("ancient", at(1, 1)),
        ]
        let sections = RecentsGrouping.group(summaries, now: now, calendar: calendar)

        // No "Previous 7 days" heading, because nothing falls in it.
        #expect(
            sections.map(\.title) == [
                RecentsGrouping.today, RecentsGrouping.yesterday, RecentsGrouping.older,
            ])
        #expect(sections.map(\.items.count) == [1, 1, 1])
        #expect(sections.first?.items.first?.title == "today")
    }

    @Test("order within a section is the order it was given")
    func orderWithinASectionIsPreserved() {
        // The store hands over newest-first; grouping must not reshuffle.
        let summaries = [
            summary("newer", at(9, 7, 9)),
            summary("older", at(9, 7, 8)),
        ]
        let sections = RecentsGrouping.group(summaries, now: now, calendar: calendar)
        #expect(sections.count == 1)
        #expect(sections[0].items.map(\.title) == ["newer", "older"])
    }

    @Test("every conversation lands in exactly one section")
    func nothingIsLostOrDuplicated() {
        let summaries = [
            summary("a", at(9, 7)), summary("b", at(9, 6)), summary("c", at(9, 3)),
            summary("d", at(8, 31)), summary("e", at(8, 30)), summary("f", at(2, 2)),
        ]
        let sections = RecentsGrouping.group(summaries, now: now, calendar: calendar)
        let regrouped = sections.flatMap(\.items).map(\.title)
        #expect(regrouped.count == summaries.count)
        #expect(Set(regrouped) == Set(summaries.map(\.title)))
    }
}
