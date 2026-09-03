// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Diary browsing — the gap app/RUNBOOK.md used to log as "diaries cannot be
// browsed, only searched": no `file_path` in the catalog, no `section` rows,
// nothing for `LocalBrowser.locate` to resolve. `CorpusStore`'s diary-entry
// methods and `LocalBrowser`'s routing to them are what closes it.
//
// Needs a built corpus, so it is opt-in, same as the golden gate:
//
//     GUTENBERG_PACKS=bundles/gutenberg-all/swift swift test

import Foundation
import Testing

@testable import GutenbergKGKit

private var packsDirectory: URL? {
    guard let path = ProcessInfo.processInfo.environment["GUTENBERG_PACKS"], !path.isEmpty
    else { return nil }
    return URL(fileURLWithPath: (path as NSString).expandingTildeInPath, isDirectory: true)
}

private let corpusInstalled = packsDirectory != nil

@Suite(.enabled(if: corpusInstalled, "set GUTENBERG_PACKS to a built corpus"))
struct DiaryBrowseTests {

    private func openDiaries() throws -> PassagePack {
        let directory = try #require(packsDirectory)
        let packs = try CorpusPacks(directory: directory)
        let diaries = try #require(packs.packs.first { $0.isDiaries })
        return diaries
    }

    private func openBrowser() throws -> LocalBrowser {
        let directory = try #require(packsDirectory)
        return LocalBrowser(packs: try CorpusPacks(directory: directory))
    }

    // MARK: - PassagePack

    @Test func identityMatchesTheCatalogsFourDiaries() throws {
        let diaries = try openDiaries()
        let known: [String: String] = [
            "The Diary of John Evelyn — Volume 1": "evelyn-volume-1",
            "The Diary of John Evelyn — Volume 2": "evelyn-volume-2",
            "The Diary of Samuel Pepys — Complete": "pepys-complete",
            "The Journal of a Tour to the Hebrides with Samuel Johnson": "johnson",
        ]
        for (title, kgName) in known {
            #expect(try diaries.diaryIdentity(title: title) == kgName)
        }
        #expect(try diaries.diaryIdentity(title: "Not A Real Diary") == nil)
    }

    @Test func entryCountsMatchWhatThePipelineChunked() throws {
        let diaries = try openDiaries()
        // Distinct-timestamp counts, verified against the pack directly when
        // this feature was built — a regression here means the entry grouping
        // broke, not that the corpus changed under the test.
        let expected: [String: Int] = [
            "evelyn-volume-1": 874,
            "evelyn-volume-2": 1_426,
            "johnson": 88,
            "pepys-complete": 2_754,
        ]
        for (kgName, count) in expected {
            #expect(try diaries.diaryEntries(kgName: kgName).count == count, "\(kgName)")
        }
    }

    @Test func entriesAreChronologicalAndReadable() throws {
        let diaries = try openDiaries()
        let entries = try diaries.diaryEntries(kgName: "johnson")

        #expect(entries == entries.sorted { $0.id < $1.id })
        // Titles are formatted for reading, not the raw "1773-08-15T00:00".
        for entry in entries {
            #expect(entry.title != entry.id)
            #expect(entry.title?.contains("T00:00") == false)
        }
    }

    @Test func entryTextIsNonEmptyAndChainsToNeighbours() throws {
        let diaries = try openDiaries()
        let entries = try diaries.diaryEntries(kgName: "johnson")
        let middle = entries.count / 2

        let first = try #require(try diaries.diaryEntry(kgName: "johnson", timestamp: entries[0].id))
        #expect(first.prevId == nil)
        #expect(first.nextId == entries[1].id)
        #expect(!first.text.isEmpty)

        let mid = try #require(
            try diaries.diaryEntry(kgName: "johnson", timestamp: entries[middle].id))
        #expect(mid.prevId == entries[middle - 1].id)
        #expect(mid.nextId == entries[middle + 1].id)

        let last = try #require(try diaries.diaryEntry(kgName: "johnson", timestamp: entries.last!.id))
        #expect(last.nextId == nil)
    }

    @Test func unknownTimestampReturnsNil() throws {
        let diaries = try openDiaries()
        #expect(try diaries.diaryEntry(kgName: "johnson", timestamp: "1000-01-01T00:00") == nil)
    }

    // MARK: - LocalBrowser (the public path Browse actually calls)

    @Test func browserListsAndReadsADiaryEndToEnd() async throws {
        let browser = try openBrowser()
        let entries = try await browser.chapters(
            genre: "diaries", book: "The Diary of Samuel Pepys — Complete")
        #expect(entries.count == 2_754)

        let content = try await browser.chapter(
            genre: "diaries", book: "The Diary of Samuel Pepys — Complete", sectionId: entries[0].id)
        #expect(!content.text.isEmpty)
        #expect(content.index == 0)
        #expect(content.total == 2_754)
    }

    @Test func browserRejectsAnUnknownDiary() async throws {
        let browser = try openBrowser()
        await #expect(throws: (any Error).self) {
            _ = try await browser.chapters(genre: "diaries", book: "Not A Real Diary")
        }
    }
}
