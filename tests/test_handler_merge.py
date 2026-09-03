"""The worker's ``corpus="all"`` merge.

Books and diaries are searched separately and folded together.  Doing that by
cosine drops literal matches, which is the whole failure the lexical channel
exists to prevent -- see :func:`gutenberg_kg.serve.fusion.merge_by_rank`.
"""

from __future__ import annotations

from gutenberg_kg.serve.fusion import merge_by_rank

RRF_K = 60


def _hit(node_id: str, score: float) -> dict:
    return {"node_id": node_id, "score": score}


def _merge(books, diaries, k):
    return [h["node_id"] for h in merge_by_rank(books, diaries, k, rrf_k=RRF_K)]


class TestMergeByRank:
    def test_a_literal_match_survives_a_higher_scoring_diary(self):
        """The "pillar of salt" shape, in miniature.

        The verse is rank 1 of the books because BM25 found it where cosine
        could not, so its score is the lowest of the four.  Sorting the union by
        score drops it outside ``k``; merging by rank keeps it, which is the
        point of having fused at all.
        """
        books = [_hit("crown:2332", 0.7071), _hit("bible:0102", 0.5939)]
        diaries = [_hit("evelyn:0144", 0.7040), _hit("evelyn:0141", 0.6945)]

        assert "bible:0102" in _merge(books, diaries, k=3)

        by_score = [h["node_id"] for h in sorted(books + diaries, key=lambda h: -h["score"])[:3]]
        assert "bible:0102" not in by_score  # what the old merge did

    def test_each_list_keeps_its_own_order(self):
        books = [_hit("b0", 0.9), _hit("b1", 0.1)]
        diaries = [_hit("d0", 0.8), _hit("d1", 0.2)]

        ids = _merge(books, diaries, k=4)

        assert ids.index("b0") < ids.index("b1")
        assert ids.index("d0") < ids.index("d1")

    def test_equal_ranks_interleave_books_first(self):
        """Disjoint ids at the same rank tie, and the tie breaks first-seen."""
        books = [_hit("b0", 0.1), _hit("b1", 0.1)]
        diaries = [_hit("d0", 0.9), _hit("d1", 0.9)]

        assert _merge(books, diaries, k=4) == ["b0", "d0", "b1", "d1"]

    def test_k_truncates(self):
        books = [_hit(f"b{i}", 0.5) for i in range(5)]
        assert len(_merge(books, [], k=2)) == 2

    def test_an_empty_side_is_a_passthrough(self):
        books = [_hit("b0", 0.5), _hit("b1", 0.4)]
        assert _merge(books, [], k=10) == ["b0", "b1"]
        assert _merge([], books, k=10) == ["b0", "b1"]
