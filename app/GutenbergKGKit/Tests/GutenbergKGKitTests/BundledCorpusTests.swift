// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: LicenseRef-Flux-Frontiers-Proprietary
// The Knowledge Press. Not redistributable; see app/LICENSE.
//
// App Store builds ship the corpus inside the app; development builds get it
// pushed to Application Support. The rule that keeps both working is that an
// installed corpus beats a bundled one, and that a staged-but-empty folder
// counts as no corpus rather than a broken one.

import Foundation
import Testing

@testable import GutenbergKGKit

@Suite struct BundledCorpusTests {

    /// A folder with no `manifest.json` is the CI and development case: the
    /// committed-empty `app/ios/Corpus` exists so XcodeGen has a path to
    /// reference, and must not be mistaken for a corpus that failed to open.
    @Test func anEmptyStagedFolderIsNotACorpus() throws {
        let empty = FileManager.default.temporaryDirectory
            .appendingPathComponent("empty-corpus-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: empty, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: empty) }

        #expect(throws: CorpusPacks.PacksError.self) { try CorpusPacks(directory: empty) }
        do {
            _ = try CorpusPacks(directory: empty)
        } catch let error as CorpusPacks.PacksError {
            // Specifically `notInstalled`, which `installed()` treats as
            // "keep looking" rather than as a failure worth reporting.
            guard case .notInstalled = error else {
                Issue.record("expected .notInstalled, got \(error)")
                return
            }
        }
    }

    /// `installed()` reports nothing rather than crashing when neither
    /// Application Support nor the bundle holds a corpus -- the ordinary
    /// state of a fresh install before anything is downloaded.
    @Test func noCorpusAnywhereIsSilent() {
        var reported: String?
        // In the test bundle there is no Corpus resource, and Application
        // Support is empty, so this is the both-absent path.
        _ = CorpusPacks.installed { reported = $0 }
        #expect(reported == nil, "absence of a corpus is not an error to report")
    }

    /// The test bundle carries no corpus, so the bundled lookup finds none.
    /// Asserted so that a build which accidentally starts shipping one --
    /// or a `bundledDirectory()` that stops checking for `manifest.json` --
    /// shows up here.
    @Test func testBundleShipsNoCorpus() {
        #expect(CorpusPacks.bundledDirectory() == nil)
    }
}
