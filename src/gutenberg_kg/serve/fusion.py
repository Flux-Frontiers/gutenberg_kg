"""Rank-list fusion, kept free of the handler's import-time startup.

``handler`` opens stores and loads the embedder when it is imported, so nothing
in it can be unit-tested cheaply.  The merge arithmetic is pure, so it lives
here instead and the handler calls in.
"""

from __future__ import annotations

from collections.abc import Sequence


def merge_by_rank(
    books: Sequence[dict], diaries: Sequence[dict], k: int, *, rrf_k: int
) -> list[dict]:
    """Fold two already-ranked hit lists into one, by rank rather than score.

    Each list is best-first in its own right, so this reuses the reciprocal-rank
    arithmetic: a hit contributes ``1 / (rrf_k + rank)`` from the list it came
    from.  Node IDs do not repeat across the two corpora, so every hit scores
    from exactly one list and equal ranks tie; the tie breaks on first-seen
    order, which interleaves the two and leaves each list's internal order
    intact.

    Sorting the union by cosine instead buries the hits the lexical channel
    exists to surface: a literal BM25 match owes its rank to that channel
    precisely because the dense one buried it, so its score is low by
    construction and a score sort drops it out of the top ``k`` entirely.

    :param books: Gutenberg hits, best-first.
    :param diaries: Diary hits, best-first.
    :param k: How many hits to return.
    :param rrf_k: The rank-damping constant.
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
    return [hit_by_id[i] for i in sorted(scores, key=lambda i: -scores[i])[:k]]
