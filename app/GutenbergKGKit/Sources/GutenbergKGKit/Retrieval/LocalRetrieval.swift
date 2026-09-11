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
        var rescued: Set<String> = []

        for pack in packs.packs {
            guard Self.pack(pack, matches: request.corpus) else { continue }
            let found = try search(
                pack: pack,
                query: query,
                text: request.query,
                k: request.k,
                oversample: oversample,
                genre: scope,
                minScore: request.minScore,
                semanticFloor: request.semanticFloor)
            perPack.append(found.hits)
            rescued.formUnion(found.lexicallyRescued)
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
        // So the packs were folded together by fused *rank* instead. That
        // protected the verse, but it protected everything else too: ids are
        // disjoint across packs, so rank 0 ties rank 0 and the merge became a
        // strict round-robin in which quality played no part. Four diaries
        // against 241 books took half of every window -- measured at exactly
        // 5 of the top 10 on all twelve golden queries.
        //
        // The distinction the merge needs is the one above: whether a hit owes
        // its rank to the lexical channel. `search` now reports that, so a
        // rescued hit keeps its fused rank and everything else competes on
        // cosine, which is directly comparable across packs (one embedder, one
        // normalised space). See analysis/CROSS_PACK_FUSION_PLAN.md.
        var hits =
            packsSearched > 1
            ? Self.mergeByFusedRank(
                perPack, k: request.k, rrfK: rrfK, lexicallyRescued: rescued)
            : (perPack.first ?? [])
        if hits.count > request.k { hits = Array(hits.prefix(request.k)) }

        return RetrievalResult(
            hits: hits,
            kgsQueried: packsSearched,
            searchMs: Int(Date().timeIntervalSince(started) * 1000))
    }

    // MARK: - One pack

    /// One pack's hits, and which of them the lexical channel rescued.
    ///
    /// "Rescued" means BM25 found it where cosine did not: it is absent from
    /// the dense top `k`. Such a hit has a low score *by construction* -- that
    /// is why it needed rescuing -- so the cross-pack merge must not judge it
    /// on cosine. Everything else may be.
    struct PackResults {
        let hits: [Hit]
        let lexicallyRescued: Set<String>
    }

    private func search(
        pack: PassagePack,
        query: [Float],
        text: String,
        k: Int,
        oversample: Int,
        genre: String?,
        minScore: Double,
        semanticFloor: Double
    ) throws -> PackResults {
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
        if semanticFloor > 0, Double(bestDense) < semanticFloor { return PackResults(hits: [], lexicallyRescued: []) }

        // What the dense channel would have returned on its own. A lexical hit
        // outside this is one cosine did not find, which is the whole reason
        // the hybrid exists -- and the reason its score cannot be trusted to
        // rank it later.
        let denseTop = Set(denseIDs.prefix(k))
        let rescued = Set(scoredLexical.filter { !denseTop.contains($0) })

        let ordered =
            scoredLexical.isEmpty
            ? Array(denseIDs.prefix(k))
            : Self.fuse(dense: denseIDs, lexical: scoredLexical, k: k, rrfK: rrfK)
        guard !ordered.isEmpty else { return PackResults(hits: [], lexicallyRescued: []) }

        let rows = try pack.passages(ids: ordered)
        let hits = ordered.compactMap { id -> Hit? in
            guard let row = rows[id] else { return nil }
            let score = ((Double(similarityByID[id] ?? 0) * 10_000).rounded()) / 10_000
            guard score >= minScore else { return nil }
            return row.hit(score: score)
        }
        return PackResults(
            hits: hits,
            lexicallyRescued: rescued.intersection(hits.map(\.nodeId)))
    }

    // MARK: - Fusion and scope

    /// Fold per-pack results, each already RRF-ordered, into one ranking.
    ///
    /// Two rules, because the packs differ in two ways that pull apart.
    ///
    /// A hit the lexical channel **rescued** keeps its fused rank. Its cosine
    /// is low by construction -- BM25 found it precisely where the dense
    /// channel did not -- so ranking it on score buries the hit the hybrid
    /// exists to surface. "pillar of salt" is the worked case: the Lot's-wife
    /// verse tops the books at 0.594 while diary chunks sit at 0.667-0.704,
    /// and a score sort does not demote it, it drops it entirely.
    ///
    /// Everything else competes on **cosine**, across packs. One embedder, one
    /// normalised space, so the scores are directly comparable, and ranking by
    /// fused rank instead threw that away: ids are disjoint across packs, so
    /// rank 0 tied rank 0 and the merge was a strict round-robin. Four diaries
    /// against 241 books took exactly half of every window on all twelve
    /// golden queries, displacing 74 better-scoring book passages.
    ///
    /// A rescue is only credible near the top of the field. FTS5 stems
    /// "Imperator" and "imperative" to one token, and "moral", "duty" and
    /// "categorical" all occur in diaries, so BM25 rescues plenty that is not
    /// a literal match at all. Those sit far below the best dense hit; the
    /// real ones sit close. Measured across the golden queries, against the
    /// best dense score in *any* pack (a pack's own best is itself noise for
    /// a question it has no answer to):
    ///
    ///     legitimate                      gap      noise in the window     gap
    ///     Audels, wire an electric bell   0.141    Boswell, "moral duty"   0.157
    ///     Bible, Moses                    0.122    Evelyn, "Imperator"     0.208
    ///     Pepys, Great Fire               0.118    Les Miserables, "Hell"  0.155
    ///     Bible, pillar of salt           0.113    Hamlet, "Moses"         0.262
    ///
    /// The margin is 0.016 wide. A rescue beyond `rescueTolerance` keeps its
    /// hit but loses its pin, and competes on cosine like everything else.
    static let rescueTolerance = 0.15

    /// Rescued hits are placed first, at the fused positions they held, and
    /// the rest fill what is left in score order. See
    /// analysis/CROSS_PACK_FUSION_PLAN.md and `CrossPackMergeTests`.
    ///
    /// :param lists: One best-first list per pack.
    /// :param k: How many hits to return.
    /// :param rrfK: The rank-damping constant, from the manifest.
    /// :param lexicallyRescued: Node ids BM25 found outside the dense top k.
    /// :param rescueTolerance: How far below the field's best a rescue may
    ///     score and still be pinned. See the constant.
    /// :returns: The merged ranking, best-first.
    static func mergeByFusedRank(
        _ lists: [[Hit]], k: Int, rrfK: Int, lexicallyRescued: Set<String> = [],
        rescueTolerance: Double = LocalRetrieval.rescueTolerance
    ) -> [Hit] {
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
        let fused =
            order
            .enumerated()
            .sorted {
                let left = scores[$0.element] ?? 0
                let right = scores[$1.element] ?? 0
                return left == right ? $0.offset < $1.offset : left > right
            }
            .map(\.element)

        // No provenance means no basis for the exception, so the whole list is
        // treated as rescued and this is the old round-robin exactly. That is
        // what keeps the one-pack and no-lexical-channel paths unchanged.
        guard !lexicallyRescued.isEmpty else {
            return fused.prefix(k).compactMap { hitByID[$0] }
        }

        // The best hit anywhere is a dense one -- a rescue is, by definition,
        // lower -- so this is the field's best dense score without plumbing.
        let best = hitByID.values.map(\.score).max() ?? 0
        let pinned = lexicallyRescued.filter { (hitByID[$0]?.score ?? 0) >= best - rescueTolerance }

        var result: [String?] = Array(repeating: nil, count: fused.count)
        var contenders: [String] = []
        for (position, id) in fused.enumerated() {
            if pinned.contains(id) {
                result[position] = id
            } else {
                contenders.append(id)
            }
        }
        // Ties keep fused order, so this only reorders where cosine actually
        // separates two hits.
        contenders.sort { (hitByID[$0]?.score ?? 0) > (hitByID[$1]?.score ?? 0) }

        var next = contenders.makeIterator()
        let merged = result.map { $0 ?? next.next() }
        return merged.prefix(k).compactMap { $0.flatMap { hitByID[$0] } }
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
