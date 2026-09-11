// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// The cross-pack merge: what happens when the books and the diaries are
// folded into one ranking.
//
// Step 1 of analysis/CROSS_PACK_FUSION_PLAN.md. Until this file the merge had
// no test of any kind -- golden.json records one pack at a time, so the whole
// `corpus=all` path shipped ungated, which is how a strict round-robin between
// two lists of very different quality went unnoticed.
//
// These tests characterise what the merge does *today*, deliberately including
// the behaviour the plan intends to change. They are the before half of that
// comparison, not an endorsement: `strictlyAlternates` is the defect, written
// down so the fix has to come here and say so.

import Foundation
import Testing

@testable import GutenbergKGKit

private func packHit(_ id: String, score: Double, kind: String) -> Hit {
    let json = """
        {"kg_name": "gutenberg-all", "kg_kind": "\(kind)", "node_id": "\(id)",
         "name": "chunk", "kind": "chunk", "score": \(score),
         "summary": null, "source_path": null, "content": "text",
         "timestamp": null, "genre": null, "title": null, "author": null}
        """
    return try! JSONDecoder().decode(Hit.self, from: Data(json.utf8))
}

private func books(_ scores: [Double]) -> [Hit] {
    scores.enumerated().map { packHit("b\($0.offset)", score: $0.element, kind: "KGKind.doc") }
}

private func diaries(_ scores: [Double]) -> [Hit] {
    scores.enumerated().map { packHit("d\($0.offset)", score: $0.element, kind: "KGKind.diary") }
}

/// Pairs ranked out of cosine order — the defect, as a number.
///
/// Counts `(earlier, later)` pairs where the earlier hit scores *lower*. A
/// perfect score sort is 0; it is not the goal, because a lexically-rescued
/// hit is supposed to outrank its cosine. It is the measure of how far the
/// ranking departs from score, so the fix should move it a long way down
/// without driving it to zero.
func cosineInversions(_ hits: [Hit]) -> Int {
    var count = 0
    for i in hits.indices {
        for j in hits.indices where j > i && hits[i].score < hits[j].score {
            count += 1
        }
    }
    return count
}

@Suite("Cross-pack merge")
struct CrossPackMergeTests {

    private let rrfK = 60

    @Test("the merge alternates the packs regardless of score")
    func strictlyAlternates() {
        // Real numbers: "categorical imperative" measured on the built corpus
        // 2026-09-10. Every books hit beats every diary hit on cosine.
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.7698, 0.7777, 0.7692, 0.7829, 0.7344, 0.7424]),
             diaries([0.6351, 0.6548, 0.5747, 0.6540, 0.6537, 0.6415])],
            k: 12, rrfK: rrfK)

        // Ids never repeat across packs, so each hit scores from exactly one
        // list: rank 0 ties rank 0, rank 1 ties rank 1, and the tie breaks on
        // first-seen order. Quality never enters.
        #expect(merged.map(\.nodeId) == [
            "b0", "d0", "b1", "d1", "b2", "d2", "b3", "d3", "b4", "d4", "b5", "d5",
        ])
        // Half the window to the weaker list.
        #expect(merged.prefix(10).filter { $0.kgKind.contains("diary") }.count == 5)
    }

    @Test("a whole pack of better hits still gets only half the window")
    func betterPackDoesNotWinMoreSlots() {
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.90, 0.89, 0.88, 0.87]), diaries([0.40, 0.39, 0.38, 0.37])],
            k: 4, rrfK: rrfK)

        #expect(merged.map(\.nodeId) == ["b0", "d0", "b1", "d1"])
        // b2 (0.88) and b3 (0.87) lost their places to d0 (0.40) and d1
        // (0.39) outright -- they are not in the result at all. Within what
        // survives, d0 sitting above b1 is the one inversion left to count.
        #expect(cosineInversions(merged) == 1)
        #expect(merged.map(\.score) == [0.90, 0.40, 0.89, 0.39])
    }

    @Test("the rescue case the merge exists for")
    func aLowCosineRescueKeepsItsPlace() {
        // "pillar of salt": the Lot's-wife verse fuses to the top of the books
        // on the lexical channel at 0.59, under every diary chunk at ~0.70.
        // Sorting the union by cosine would drop it out of the top k entirely,
        // which is what fusion.py's docstring is about.
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.59, 0.55, 0.54]), diaries([0.70, 0.69, 0.68])],
            k: 3, rrfK: rrfK)

        #expect(merged.first?.nodeId == "b0")
        // Whatever replaces this merge has to keep that first line true.
    }

    @Test("one empty pack leaves the other untouched")
    func emptyPackIsANoOp() {
        let ranked = books([0.9, 0.8, 0.7])
        let merged = LocalRetrieval.mergeByFusedRank([ranked, []], k: 3, rrfK: rrfK)
        #expect(merged.map(\.nodeId) == ranked.map(\.nodeId))
        #expect(cosineInversions(merged) == 0)
    }

    // MARK: - With lexical provenance

    @Test("without provenance the merge is exactly the old round-robin")
    func noProvenanceIsTheOldBehaviour() {
        let lists = [books([0.90, 0.89, 0.88]), diaries([0.40, 0.39, 0.38])]
        #expect(
            LocalRetrieval.mergeByFusedRank(lists, k: 6, rrfK: rrfK, lexicallyRescued: []).map(
                \.nodeId)
                == LocalRetrieval.mergeByFusedRank(lists, k: 6, rrfK: rrfK).map(\.nodeId))
    }

    @Test("an unrescued pack no longer takes half the window")
    func unrescuedHitsCompeteOnCosine() {
        // The same "categorical imperative" numbers as `strictlyAlternates`.
        // Nothing here was rescued -- the diaries are ordinary dense hits that
        // rank high only within a much weaker list.
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.7698, 0.7777, 0.7692, 0.7829, 0.7344, 0.7424]),
             diaries([0.6351, 0.6548, 0.5747, 0.6540, 0.6537, 0.6415])],
            k: 6, rrfK: rrfK, lexicallyRescued: ["b0"])

        // b0 is rescued, so it holds rank 0. The rest sort by cosine, and the
        // whole window is now books.
        #expect(merged.map(\.nodeId) == ["b0", "b3", "b1", "b2", "b5", "b4"])
        #expect(merged.allSatisfy { !$0.kgKind.contains("diary") })
    }

    @Test("the rescued hit keeps its place above better-scoring rivals")
    func rescuedHitOutranksItsCosine() {
        // "pillar of salt": b0 is the Lot's-wife verse at 0.594, under every
        // diary chunk. Rescued, so it stays at rank 0 -- which a cosine sort
        // would never do.
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.594, 0.55, 0.54]), diaries([0.704, 0.69, 0.667])],
            k: 6, rrfK: rrfK, lexicallyRescued: ["b0"])

        #expect(merged.first?.nodeId == "b0")
        // Everything else, having earned nothing, is in score order.
        #expect(merged.dropFirst().map(\.score) == [0.704, 0.69, 0.667, 0.55, 0.54])
    }

    @Test("a pack that is genuinely better still wins on merit")
    func theDiariesKeepTheWindowWhenTheyDeserveIt() {
        // "descriptions of the Great Fire of London": Pepys and Evelyn were
        // there, and outscore most of the books. Nothing demotes them.
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.786, 0.515, 0.52]), diaries([0.773, 0.765, 0.757])],
            k: 4, rrfK: rrfK, lexicallyRescued: ["b0"])

        #expect(merged.map(\.nodeId) == ["b0", "d0", "d1", "d2"])
    }

    @Test("every rescued hit holds a fused position, even several")
    func severalRescuesAllHoldTheirRanks() {
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.80, 0.90]), diaries([0.82, 0.85])],
            k: 4, rrfK: rrfK, lexicallyRescued: ["b0", "d0"])

        // Fused order is b0, d0, b1, d1; b0 and d0 are pinned at 0 and 1, and
        // the remaining two fill positions 2 and 3 by score.
        #expect(merged.map(\.nodeId) == ["b0", "d0", "b1", "d1"])
        #expect(merged.map(\.score) == [0.80, 0.82, 0.90, 0.85])
    }

    // MARK: - The rescue tolerance

    @Test("a rescue far below the field is not protected")
    func aDistantRescueLosesItsPin() {
        // "the categorical imperative and moral duty": Boswell was rescued on
        // "moral" and pinned at rank 4 above Kant at 0.789. Gap from the
        // field's best is 0.157 -- past the tolerance, so it competes on
        // cosine and lands where it belongs.
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.815, 0.804, 0.796, 0.789]), diaries([0.689, 0.658])],
            k: 6, rrfK: rrfK, lexicallyRescued: ["d1"])
        #expect(merged.map(\.nodeId) == ["b0", "b1", "b2", "b3", "d0", "d1"])
    }

    @Test("a rescue near the field keeps its pin -- the verse")
    func aNearRescueIsStillPinned() {
        // "pillar of salt": the verse at 0.594 against a field best of 0.707,
        // gap 0.113. Pinned at its fused position, which is third.
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.707, 0.594]), diaries([0.704, 0.694])],
            k: 4, rrfK: rrfK, lexicallyRescued: ["b1"])
        #expect(merged[2].nodeId == "b1")
    }

    @Test("the widest legitimate rescue measured is inside the tolerance")
    func theWidestLegitimateRescueSurvives() {
        // Audels Electric Library for "how to wire an electric bell": 0.650
        // against 0.791, gap 0.141. This is the case that sets the floor on
        // the tolerance; if it ever fails, lowering the constant is wrong.
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.791, 0.650]), diaries([0.658, 0.587])],
            k: 4, rrfK: rrfK, lexicallyRescued: ["b1"])
        #expect(merged[2].nodeId == "b1")
    }

    @Test("provenance with nothing inside the tolerance is a plain score sort")
    func nothingProtectedMeansScoreOrder() {
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.90, 0.40]), diaries([0.85, 0.30])],
            k: 4, rrfK: rrfK, lexicallyRescued: ["b1", "d1"])
        #expect(merged.map(\.score) == [0.90, 0.85, 0.40, 0.30])
    }

    @Test("k truncates after merging, not before")
    func kTruncatesTheMergedRanking() {
        let merged = LocalRetrieval.mergeByFusedRank(
            [books([0.9, 0.8]), diaries([0.7, 0.6])], k: 3, rrfK: rrfK)
        #expect(merged.map(\.nodeId) == ["b0", "d0", "b1"])
    }
}
