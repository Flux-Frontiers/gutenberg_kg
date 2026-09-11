"""Rank-list fusion, kept free of the handler's import-time startup.

``handler`` opens stores and loads the embedder when it is imported, so nothing
in it can be unit-tested cheaply.  The merge arithmetic is pure, so it lives
here instead and the handler calls in.
"""

from __future__ import annotations

from collections.abc import Sequence

#: How far below the field's best dense score a lexical rescue may sit and
#: still be pinned. FTS5 stems "Imperator" and "imperative" to one token, and
#: "moral", "duty" and "categorical" all occur in diaries, so BM25 rescues
#: plenty that is not a literal match. Those sit far below the best dense hit;
#: the real ones sit close. Measured across the golden queries against the best
#: dense score in *any* corpus (a corpus's own best is itself noise for a
#: question it cannot answer):
#:
#:     legitimate                      gap      noise in the window     gap
#:     Audels, wire an electric bell   0.141    Boswell, "moral duty"   0.157
#:     Bible, Moses                    0.122    Evelyn, "Imperator"     0.208
#:     Pepys, Great Fire               0.118    Les Miserables, "Hell"  0.155
#:     Bible, pillar of salt           0.113    Hamlet, "Moses"         0.262
#:
#: The margin is 0.016 wide. Mirrors ``LocalRetrieval.rescueTolerance``.
RESCUE_TOLERANCE = 0.15


def merge_by_rank(
    books: Sequence[dict],
    diaries: Sequence[dict],
    k: int,
    *,
    rrf_k: int,
    lexically_rescued: frozenset[str] | set[str] = frozenset(),
    rescue_tolerance: float = RESCUE_TOLERANCE,
) -> list[dict]:
    """Fold two already-ranked hit lists into one.

    Two rules, because the lists differ in two ways that pull apart.

    A hit the lexical channel **rescued** keeps its fused rank.  Its cosine is
    low by construction -- BM25 found it precisely where the dense channel did
    not -- so ranking it on score buries the hit the hybrid exists to surface.
    "pillar of salt" is the worked case: the Lot's-wife verse sits in the books
    at 0.594 while diary chunks score 0.667-0.704, and a score sort does not
    demote it, it drops it entirely.

    Everything else competes on **cosine**, across lists.  One embedder, one
    normalised space, so the scores are directly comparable.  Merging by fused
    rank alone threw that away: node IDs never repeat across the two corpora,
    so every hit scored from exactly one list, rank 0 tied rank 0, and the
    merge was a strict round-robin.  Four diaries against 241 books took
    exactly half of every window on all twelve golden queries.

    Fused rank is the reciprocal-rank arithmetic: ``1 / (rrf_k + rank)`` from
    the list a hit came from, ties broken first-seen.  A rescued hit's fused
    rank is a **floor**, not a slot: it takes the better of that and the rank
    its cosine would earn.  Pinning it to the slot alone stopped it rising,
    and once the two lists interleave a fused rank past ``k`` sat outside the
    window while weaker unpinned hits filled it -- measured on the worker,
    2026-09-11: two *Groundwork* passages at 0.766 held at merged ranks 10 and
    14 while Boswell at 0.688 took ranks 9 and 10.  The rest fill what is
    left in score order.  With no rescued IDs this is the old round-robin
    exactly, which keeps a dense-only path unchanged.  Mirrors
    ``LocalRetrieval.mergeByFusedRank`` in the Swift app; see
    analysis/CROSS_PACK_FUSION_PLAN.md.

    :param books: Gutenberg hits, best-first.
    :param diaries: Diary hits, best-first.
    :param k: How many hits to return.
    :param rrf_k: The rank-damping constant.
    :param lexically_rescued: Node IDs BM25 found outside the dense top ``k``.
    :param rescue_tolerance: How far below the field's best a rescue may score
        and still be pinned; see :data:`RESCUE_TOLERANCE`.
    :returns: The merged ranking, best-first.
    """
    scores: dict[str, float] = {}
    hit_by_id: dict[str, dict] = {}
    for ranked in (books, diaries):
        for rank, hit in enumerate(ranked):
            node_id = hit.get("node_id") or ""
            if node_id not in hit_by_id:
                hit_by_id[node_id] = hit
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (rrf_k + rank)
    # `sorted` is stable, so equal scores keep insertion order.
    fused = sorted(scores, key=lambda i: -scores[i])

    if not lexically_rescued:
        return [hit_by_id[i] for i in fused[:k]]

    def score(node_id: str) -> float:
        return float(hit_by_id[node_id].get("score") or 0.0)

    # The best hit anywhere is a dense one -- a rescue is, by definition,
    # lower -- so this is the field's best dense score without plumbing.
    best = max((score(i) for i in fused), default=0.0)
    protected = {i for i in lexically_rescued if score(i) >= best - rescue_tolerance}

    # Stable, so ties keep fused order: this only reorders where cosine
    # actually separates two hits.
    by_cosine = sorted(fused, key=lambda i: -score(i))
    cosine_rank = {node_id: rank for rank, node_id in enumerate(by_cosine)}
    fused_rank = {node_id: rank for rank, node_id in enumerate(fused)}
    # Place the protected hits first, best floor first, sliding down on a
    # collision; then the rest fill the gaps in cosine order.
    placed: list[str | None] = [None] * len(fused)
    for node_id in sorted(
        protected, key=lambda i: (min(fused_rank[i], cosine_rank[i]), fused_rank[i])
    ):
        slot = min(fused_rank[node_id], cosine_rank[node_id])
        while placed[slot] is not None:
            slot += 1
        placed[slot] = node_id
    fill = iter(i for i in by_cosine if i not in protected)
    merged = [i if i is not None else next(fill) for i in placed]
    return [hit_by_id[i] for i in merged[:k]]
