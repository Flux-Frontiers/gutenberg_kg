// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The `corpus=all` measurement harness — step 1 of
// analysis/CROSS_PACK_FUSION_PLAN.md.
//
// Skipped unless GUTENBERG_PACKS points at a built corpus, like the golden
// gate, and it reuses the golden gate's own queries so both are describing the
// same twelve questions. The golden gate searches one pack at a time, though,
// so nothing it records says anything about how the two are merged. That is
// what this adds.
//
// It prints a table rather than only asserting, because the number that
// matters here -- whether the merged ranking puts the better passages first --
// is not something a boolean settles. Run it with:
//
//   GUTENBERG_PACKS=bundles/gutenberg-all/swift swift test --filter CrossPackProbe

import Foundation
import Testing

@testable import GutenbergKGKit

private var packsDirectory: URL? {
    guard let path = ProcessInfo.processInfo.environment["GUTENBERG_PACKS"], !path.isEmpty
    else { return nil }
    return URL(fileURLWithPath: (path as NSString).expandingTildeInPath, isDirectory: true)
}

private let corpusInstalled = packsDirectory != nil

private struct GoldenQueries: Decodable {
    struct Entry: Decodable { let query: String }
    let queries: [Entry]
}

@Suite(.enabled(if: corpusInstalled, "set GUTENBERG_PACKS to a built corpus"))
struct CrossPackProbeTests {

    /// The window the on-device budget actually draws from.
    private let window = 10

    private func isDiary(_ hit: Hit) -> Bool { hit.kgKind.lowercased().contains("diary") }

    @Test func reportTheMergedRankingForEveryGoldenQuery() async throws {
        let directory = try #require(packsDirectory)
        let packs = try CorpusPacks(directory: directory)
        let golden = try JSONDecoder().decode(
            GoldenQueries.self,
            from: try Data(contentsOf: directory.appendingPathComponent("golden.json")))
        let retrieval = LocalRetrieval(packs: packs)

        print("")
        print("corpus=all, top \(window) — rrfK \(packs.manifest.rrfK)")
        print("  diary  = diary passages in the window")
        print("  inv    = pairs ranked out of cosine order (0 is a pure score sort,")
        print("           which is not the goal: a rescued hit is meant to outrank its cosine)")
        print("")
        print("  diary  inv   books cos     diary cos     query")

        var totalDiary = 0
        var totalInversions = 0
        for entry in golden.queries {
            let hits = try await retrieval.retrieve(
                RetrievalRequest(
                    query: entry.query, corpus: "all", k: 25,
                    minScore: 0.5, semanticFloor: 0.20)
            ).hits
            let top = Array(hits.prefix(window))
            guard !top.isEmpty else {
                print("     --   --   (no hits)                    \(entry.query)")
                continue
            }

            let bookScores = top.filter { !isDiary($0) }.map(\.score)
            let diaryScores = top.filter { isDiary($0) }.map(\.score)

            // Only these two. An earlier draft also counted books hits that
            // fell outside the window while a lower-scoring diary hit sat
            // inside it, which read well and measured nothing stable: its
            // floor was the weakest diary hit *in the window*, so a fix that
            // left one weak diary hit in place drove the count up while
            // making the ranking better. Composition-dependent metrics cannot
            // compare a before and an after whose compositions differ.
            let inversions = cosineInversions(top)
            totalDiary += diaryScores.count
            totalInversions += inversions
            print(
                String(
                    format: "  %5d %4d   %.3f-%.3f   %@   %@",
                    diaryScores.count, inversions,
                    bookScores.min() ?? 0, bookScores.max() ?? 0,
                    diaryScores.isEmpty
                        ? "    --       "
                        : String(format: "%.3f-%.3f", diaryScores.min()!, diaryScores.max()!),
                    entry.query))
        }
        print("")
        print("  totals: \(totalDiary) diary passages, \(totalInversions) inversions")
        print("")

        // The harness itself is what this test guarantees; the numbers above
        // are the baseline the fix is judged against, and pinning them here
        // would only make this file churn every time the corpus is rebuilt.
        #expect(!golden.queries.isEmpty)
    }
}
