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


def _merge(books, diaries, k, rescued=()):
    merged = merge_by_rank(books, diaries, k, rrf_k=RRF_K, lexically_rescued=frozenset(rescued))
    return [h["node_id"] for h in merged]


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


class TestLexicalProvenance:
    """The merge with rescue provenance -- `CrossPackMergeTests` in the app."""

    # "categorical imperative", measured on the built corpus 2026-09-10.
    # Every books hit beats every diary hit on cosine.
    BOOKS = [0.7698, 0.7777, 0.7692, 0.7829, 0.7344, 0.7424]
    DIARIES = [0.6351, 0.6548, 0.5747, 0.6540, 0.6537, 0.6415]

    def _lists(self):
        return (
            [_hit(f"b{i}", s) for i, s in enumerate(self.BOOKS)],
            [_hit(f"d{i}", s) for i, s in enumerate(self.DIARIES)],
        )

    def test_without_provenance_the_merge_is_the_old_round_robin(self):
        books, diaries = self._lists()
        assert _merge(books, diaries, k=12) == _merge(books, diaries, k=12, rescued=())
        assert _merge(books, diaries, k=6) == ["b0", "d0", "b1", "d1", "b2", "d2"]

    def test_an_unrescued_pack_no_longer_takes_half_the_window(self):
        """Nothing here was rescued: the diaries are ordinary dense hits that
        rank high only within a much weaker list.  b0 holds rank 0; the rest
        sort by cosine, and the whole window is books."""
        books, diaries = self._lists()
        assert _merge(books, diaries, k=6, rescued={"b0"}) == ["b0", "b3", "b1", "b2", "b5", "b4"]

    def test_the_rescued_hit_keeps_its_place_above_better_scoring_rivals(self):
        """The pillar-of-salt shape: b0 is the verse at 0.594, under every diary
        chunk.  Rescued, so it stays at rank 0, which a cosine sort never does."""
        books = [_hit("b0", 0.594), _hit("b1", 0.55), _hit("b2", 0.54)]
        diaries = [_hit("d0", 0.704), _hit("d1", 0.69), _hit("d2", 0.667)]

        merged = merge_by_rank(books, diaries, 6, rrf_k=RRF_K, lexically_rescued={"b0"})

        assert merged[0]["node_id"] == "b0"
        assert [h["score"] for h in merged[1:]] == [0.704, 0.69, 0.667, 0.55, 0.54]

    def test_a_pack_that_is_genuinely_better_still_wins_on_merit(self):
        """The Great Fire: Pepys and Evelyn were there and outscore most of
        the books.  Nothing demotes them."""
        books = [_hit("b0", 0.786), _hit("b1", 0.515), _hit("b2", 0.52)]
        diaries = [_hit("d0", 0.773), _hit("d1", 0.765), _hit("d2", 0.757)]
        assert _merge(books, diaries, k=4, rescued={"b0"}) == ["b0", "d0", "d1", "d2"]

    def test_every_rescued_hit_holds_a_fused_position(self):
        books = [_hit("b0", 0.80), _hit("b1", 0.90)]
        diaries = [_hit("d0", 0.82), _hit("d1", 0.85)]
        merged = merge_by_rank(books, diaries, 4, rrf_k=RRF_K, lexically_rescued={"b0", "d0"})
        # Fused order is b0, d0, b1, d1; the two rescues are pinned at 0 and
        # 1, and the remaining two fill positions 2 and 3 by score.
        assert [h["node_id"] for h in merged] == ["b0", "d0", "b1", "d1"]
        assert [h["score"] for h in merged] == [0.80, 0.82, 0.90, 0.85]


class TestRescueTolerance:
    """A rescue is only pinned near the top of the field -- mirrors the Swift."""

    def test_a_rescue_far_below_the_field_loses_its_pin(self):
        """Boswell on "moral duty": 0.658 against a field best of 0.815, gap
        0.157. Past the tolerance, so it competes on cosine."""
        books = [_hit("b0", 0.815), _hit("b1", 0.804), _hit("b2", 0.796), _hit("b3", 0.789)]
        diaries = [_hit("d0", 0.689), _hit("d1", 0.658)]
        assert _merge(books, diaries, k=6, rescued={"d1"}) == ["b0", "b1", "b2", "b3", "d0", "d1"]

    def test_the_verse_is_inside_the_tolerance(self):
        """pillar of salt: 0.594 against 0.707, gap 0.113. Still pinned third."""
        books = [_hit("b0", 0.707), _hit("b1", 0.594)]
        diaries = [_hit("d0", 0.704), _hit("d1", 0.694)]
        assert _merge(books, diaries, k=4, rescued={"b1"})[2] == "b1"

    def test_the_widest_legitimate_rescue_survives(self):
        """Audels for "wire an electric bell": 0.650 against 0.791, gap 0.141.
        This sets the floor on the tolerance."""
        books = [_hit("b0", 0.791), _hit("b1", 0.650)]
        diaries = [_hit("d0", 0.658), _hit("d1", 0.587)]
        assert _merge(books, diaries, k=4, rescued={"b1"})[2] == "b1"

    def test_nothing_inside_the_tolerance_is_a_plain_score_sort(self):
        books = [_hit("b0", 0.90), _hit("b1", 0.40)]
        diaries = [_hit("d0", 0.85), _hit("d1", 0.30)]
        merged = merge_by_rank(books, diaries, 4, rrf_k=RRF_K, lexically_rescued={"b1", "d1"})
        assert [h["score"] for h in merged] == [0.90, 0.85, 0.40, 0.30]
