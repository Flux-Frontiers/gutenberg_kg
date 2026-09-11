"""Rank-list fusion, kept free of the handler's import-time startup.

``handler`` opens stores and loads the embedder when it is imported, so nothing
in it can be unit-tested cheaply.  The merge arithmetic is pure, so it lives
here instead and the handler calls in.
"""

from __future__ import annotations

from collections.abc import Sequence


def merge_by_rank(
    books: Sequence[dict],
    diaries: Sequence[dict],
    k: int,
    *,
    rrf_k: int,
    lexically_rescued: frozenset[str] | set[str] = frozenset(),
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
    the list a hit came from, ties broken first-seen.  Rescued hits are pinned
    at the positions they hold there; the rest fill what is left in score
    order.  With no rescued IDs this is the old round-robin exactly, which
    keeps a dense-only path unchanged.  Mirrors ``LocalRetrieval.
    mergeByFusedRank`` in the Swift app; see analysis/CROSS_PACK_FUSION_PLAN.md.

    :param books: Gutenberg hits, best-first.
    :param diaries: Diary hits, best-first.
    :param k: How many hits to return.
    :param rrf_k: The rank-damping constant.
    :param lexically_rescued: Node IDs BM25 found outside the dense top ``k``.
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

    pinned: list[str | None] = [i if i in lexically_rescued else None for i in fused]
    contenders = [i for i in fused if i not in lexically_rescued]
    # Stable, so ties keep fused order: this only reorders where cosine
    # actually separates two hits.
    contenders.sort(key=lambda i: -float(hit_by_id[i].get("score") or 0.0))
    fill = iter(contenders)
    merged = [i if i is not None else next(fill) for i in pinned]
    return [hit_by_id[i] for i in merged[:k]]
