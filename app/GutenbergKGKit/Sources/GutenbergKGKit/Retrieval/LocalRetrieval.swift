// © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
//
// Retrieval with no network: embed on the Neural Engine, scan the mapped
// vectors, run BM25 over FTS5, fuse the two with RRF.
//
// A translation of `handler._semantic_search`, and held to it by the packs'
// golden.json — same `k * 3` oversampling in both channels, same RRF constant,
// same `1 - distance` score, same hydrate-missing-cosine step so every fused
// hit carries an honest number.

import Foundation

/// The on-device query path.
public struct LocalRetrieval: RetrievalEngine {

    public let label = "On-device corpus"
    public let requiresNetwork = false

    private let packs: CorpusPacks

    /// :param packs: An opened, validated corpus.
    public init(packs: CorpusPacks) {
        self.packs = packs
    }

    /// Reciprocal-rank-fusion constant. Read from the manifest so the packs
    /// and the app cannot disagree about it.
    private var rrfK: Int { packs.manifest.rrfK }

    public func retrieve(_ request: RetrievalRequest) async throws -> RetrievalResult {
        let started = Date()
        let query = try packs.embedder.embed(request.query)
        let scope = Self.genreScope(for: request.corpus)
        let oversample = max(request.k * 3, request.k)

        var perPack: [[Hit]] = []

        for pack in packs.packs {
            guard Self.pack(pack, matches: request.corpus) else { continue }
            perPack.append(
                try search(
                    pack: pack,
                    query: query,
                    text: request.query,
                    k: request.k,
                    oversample: oversample,
                    genre: scope,
                    minScore: request.minScore,
                    semanticFloor: request.semanticFloor))
        }
        let packsSearched = perPack.count

        // Each list is already in RRF order, and cosine is not what RRF ranked
        // by, so neither the one-pack case nor the merge may re-sort on score.
        //
        // The merge is where this bites hardest. A literal match owes its place
        // to BM25 precisely *because* the dense channel buried it, so its
        // cosine is low by construction: "pillar of salt" fuses the Lot's-wife
        // verse to rank 1 of the books at 0.59, where every diary chunk scores
        // ~0.70. Sorting the combined list by score therefore does not just
        // reorder it, it drops the verse off the end of the top k -- it buries
        // exactly the hit the lexical channel exists to rescue, and the deeper
        // the fusion reached, the more certainly it is lost.
        //
        // So the packs are folded together by fused *rank* instead, with the
        // same RRF constant. Disjoint ids at equal rank tie and fall back to
        // first-seen order, which interleaves the packs and keeps each one's
        // internal order intact. Note this is deliberately *not* what
        // `handler.query` does in its `corpus == "all"` branch, which sorts by
        // score and has the same defect.
        var hits =
            packsSearched > 1
            ? Self.mergeByFusedRank(perPack, k: request.k, rrfK: rrfK)
            : (perPack.first ?? [])
        if hits.count > request.k { hits = Array(hits.prefix(request.k)) }

        return RetrievalResult(
            hits: hits,
            kgsQueried: packsSearched,
            searchMs: Int(Date().timeIntervalSince(started) * 1000))
    }

    // MARK: - One pack

    private func search(
        pack: PassagePack,
        query: [Float],
        text: String,
        k: Int,
        oversample: Int,
        genre: String?,
        minScore: Double,
        semanticFloor: Double
    ) throws -> [Hit] {
        var similarityByID: [String: Float] = [:]
        var denseIDs: [String] = []
        var bestDense: Float = 0

        if let index = pack.vectors {
            let eligible = try pack.eligibleVectorRows(genre: genre)
            let ranked = index.search(query: query, k: oversample, eligible: eligible)
            let names = try pack.ids(forVectorRows: ranked.map(\.row))
            for entry in ranked {
                guard let id = names[entry.row] else { continue }
                denseIDs.append(id)
                similarityByID[id] = entry.similarity
            }
            bestDense = ranked.first?.similarity ?? 0
        }

        let lexicalIDs = try pack.lexicalSearch(text, limit: oversample, genre: genre)

        // Hydrate cosine for lexical-only hits so a BM25 rescue still shows a
        // real score rather than a placeholder.
        if let index = pack.vectors, !lexicalIDs.isEmpty {
            let missing = lexicalIDs.filter { similarityByID[$0] == nil }
            if !missing.isEmpty {
                let rows = try pack.passages(ids: missing)
                for id in missing {
                    guard let row = rows[id]?.vectorRow,
                        let similarity = index.similarity(query: query, row: row)
                    else { continue }
                    similarityByID[id] = similarity
                }
            }
        }
        let scoredLexical = lexicalIDs.filter { similarityByID[$0] != nil }

        // The floor asks whether this corpus is relevant at all, so it is
        // tested against the best *dense* score: a literal match with modest
        // cosine should not keep a stale set alive on its own.
        if semanticFloor > 0, Double(bestDense) < semanticFloor { return [] }

        let ordered =
            scoredLexical.isEmpty
            ? Array(denseIDs.prefix(k))
            : Self.fuse(dense: denseIDs, lexical: scoredLexical, k: k, rrfK: rrfK)
        guard !ordered.isEmpty else { return [] }

        let rows = try pack.passages(ids: ordered)
        return ordered.compactMap { id in
            guard let row = rows[id] else { return nil }
            let score = ((Double(similarityByID[id] ?? 0) * 10_000).rounded()) / 10_000
            guard score >= minScore else { return nil }
            return row.hit(score: score)
        }
    }

    // MARK: - Fusion and scope

    /// Fold per-pack results, each already RRF-ordered, into one ranking.
    ///
    /// Same arithmetic as :func:`fuse`, applied to whole packs rather than to
    /// the two channels inside one: a hit contributes `1 / (rrfK + rank)` from
    /// the list it came from. Ids do not repeat across packs, so every hit
    /// scores from exactly one list and equal ranks tie; the tie breaks on
    /// first-seen order, which interleaves the packs fairly while preserving
    /// the order each one fused for itself.
    ///
    /// :param lists: One best-first list per pack.
    /// :param k: How many hits to return.
    /// :param rrfK: The rank-damping constant, from the manifest.
    /// :returns: The merged ranking, best-first.
    static func mergeByFusedRank(_ lists: [[Hit]], k: Int, rrfK: Int) -> [Hit] {
        var scores: [String: Double] = [:]
        var hitByID: [String: Hit] = [:]
        var order: [String] = []
        for list in lists {
            for (rank, hit) in list.enumerated() {
                if hitByID[hit.nodeId] == nil {
                    order.append(hit.nodeId)
                    hitByID[hit.nodeId] = hit
                }
                scores[hit.nodeId, default: 0] += 1.0 / Double(rrfK + rank)
            }
        }
        return
            order
            .enumerated()
            .sorted {
                let left = scores[$0.element] ?? 0
                let right = scores[$1.element] ?? 0
                return left == right ? $0.offset < $1.offset : left > right
            }
            .prefix(k)
            .compactMap { hitByID[$0.element] }
    }

    /// Reciprocal rank fusion — `handler._rrf_fuse`, arithmetic for arithmetic.
    ///
    /// :param dense: Ids best-first by cosine.
    /// :param lexical: Ids best-first by BM25.
    /// :param k: Fused ids to return.
    /// :param rrfK: The rank-damping constant, from the manifest.
    /// :returns: Fused ids, best-first.
    static func fuse(dense: [String], lexical: [String], k: Int, rrfK: Int) -> [String] {
        var scores: [String: Double] = [:]
        var order: [String] = []
        for (rank, id) in dense.enumerated() {
            if scores[id] == nil { order.append(id) }
            scores[id, default: 0] += 1.0 / Double(rrfK + rank)
        }
        for (rank, id) in lexical.enumerated() {
            if scores[id] == nil { order.append(id) }
            scores[id, default: 0] += 1.0 / Double(rrfK + rank)
        }
        // Ties keep first-seen order, which is what Python's `sorted` does with
        // a stable sort over an insertion-ordered dict.
        return
            order
            .enumerated()
            .sorted {
                let left = scores[$0.element] ?? 0
                let right = scores[$1.element] ?? 0
                return left == right ? $0.offset < $1.offset : left > right
            }
            .prefix(k)
            .map(\.element)
    }

    /// The genre filter a corpus scope implies, or nil for no filter.
    ///
    /// `all`, `gutenberg` and `diary` select *packs*, not genres; anything else
    /// is a genre slug. Same vocabulary as the worker's `corpus` parameter.
    static func genreScope(for corpus: String) -> String? {
        switch corpus {
        case "all", "gutenberg", "diary", "": return nil
        default: return corpus
        }
    }

    /// Whether a pack takes part in a given scope.
    static func pack(_ pack: PassagePack, matches corpus: String) -> Bool {
        switch corpus {
        case "gutenberg": return !pack.isDiaries
        case "diary": return pack.isDiaries
        default: return true
        }
    }
}
