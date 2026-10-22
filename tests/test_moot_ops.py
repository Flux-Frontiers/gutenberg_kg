"""Live moots: the Moot class, the worker's moot sessions and their auth rules."""

from __future__ import annotations

import json

import pytest

from gutenberg_kg.serve import entmoot, moot_ops
from gutenberg_kg.serve.entmoot import Moot, run_moot
from gutenberg_kg.serve.moot_ops import MootSessions, authorized

A = "philosophy/Meditations"
B = "philosophy/The Prince"


class FakeClient:
    """Each book returns two passages of its own."""

    def query(self, query, *, corpus="all", k=8, **_kw):
        hits = [
            {
                "node_id": f"{corpus}#{i}",
                "name": f"chunk:{i:04d}",
                "content": f"{corpus} passage {i}: virtue is its own reward",
                "title": corpus.split("/", 1)[1],
                "author": "Marcus Aurelius" if corpus == A else "Niccolo Machiavelli",
                "genre": corpus.split("/", 1)[0],
            }
            for i in range(1, 3)
        ]
        return {"hits": hits[:k]}


class FakeSynth:
    """Numbers its replies, so turns can be told apart."""

    def __init__(self, fail_first: int = 0):
        self.n = 0
        self.fail_first = fail_first
        self.models: list = []

    def complete(self, messages, *, model=None, max_tokens=None, temperature=0.7):
        self.models.append(model)
        if "neutral narrator" in messages[0]["content"]:
            return "A neutral summary."
        if self.fail_first:
            self.fail_first -= 1
            raise ConnectionError("model server down")
        self.n += 1
        return f"Reply {self.n} [s1]."


VOICES = {"marcus_aurelius": {"gender": "male", "accent": None, "source": "wikidata"}}


def _sessions(synth=None, clock=None, backend="omlx"):
    kw = {"clock": clock} if clock else {}
    return MootSessions(
        FakeClient(), synth or FakeSynth(), backend, lambda key: key in (A, B, "x/C"), VOICES, **kw
    )


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------------------
# Moot, one turn at a time
# ---------------------------------------------------------------------------


class TestMoot:
    def test_turn_by_turn_matches_run_moot(self):
        whole = run_moot(FakeClient(), FakeSynth(), [A, B], "virtue", 9)
        moot = Moot(FakeClient(), FakeSynth(), [A, B], "virtue", 9)
        moot.start()
        while not moot.done:
            moot.next_turn()
        stepped = moot.transcript
        assert [(u.speaker, u.text, u.intent) for u in stepped.utterances] == [
            (u.speaker, u.text, u.intent) for u in whole.utterances
        ]
        assert stepped.summaries == whole.summaries

    def test_next_turn_needs_a_start(self):
        with pytest.raises(RuntimeError, match="start"):
            Moot(FakeClient(), FakeSynth(), [A, B], "virtue", 2).next_turn()

    def test_no_turn_after_the_last(self):
        moot = Moot(FakeClient(), FakeSynth(), [A, B], "virtue", 2)
        moot.start()
        moot.next_turn()
        moot.next_turn()
        assert moot.done
        with pytest.raises(RuntimeError, match="over"):
            moot.next_turn()

    def test_the_same_book_twice_is_refused_before_retrieval(self):
        with pytest.raises(ValueError, match="two different books"):
            Moot(FakeClient(), FakeSynth(), [A, A], "virtue", 2)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuthorized:
    def test_open_worker_needs_nothing(self):
        assert authorized({}, moot_token="", handler_secret="")

    def test_token_passes_and_a_wrong_one_does_not(self):
        assert authorized({"token": "t"}, moot_token="t", handler_secret="")
        assert not authorized({"token": "u"}, moot_token="t", handler_secret="")
        assert not authorized({}, moot_token="t", handler_secret="")

    def test_secret_alone_guards_moots_when_no_token_is_set(self):
        assert not authorized({}, moot_token="", handler_secret="s")
        assert authorized({"secret": "s"}, moot_token="", handler_secret="s")

    def test_token_or_secret_when_both_are_set(self):
        assert authorized({"token": "t"}, moot_token="t", handler_secret="s")
        assert authorized({"secret": "s"}, moot_token="t", handler_secret="s")
        assert not authorized({"token": "s"}, moot_token="t", handler_secret="s")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class TestStart:
    def test_start_names_the_trees_with_voices(self):
        out = _sessions().handle("moot_start", {"books": [A, B], "topic": "virtue", "turns": 4})
        assert out["turns"] == 4 and out["topic"] == "virtue"
        assert out["id"] == "meditations-the-prince-virtue"
        assert [t["key"] for t in out["trees"]] == [A, B]
        assert out["trees"][0]["voice"] == {"gender": "male", "accent": None}
        assert out["trees"][1]["voice"] == {"gender": None, "accent": None}
        assert len(out["moot_id"]) == 32

    def test_default_model_on_omlx_is_the_moot_default(self):
        out = _sessions().handle("moot_start", {"books": [A, B]})
        assert out["model"] == entmoot.DEFAULT_MODEL

    def test_a_named_model_is_used(self):
        synth = FakeSynth()
        s = _sessions(synth)
        out = s.handle("moot_start", {"books": [A, B], "model": "small"})
        s.handle("moot_turn", {"moot_id": out["moot_id"]})
        assert out["model"] == "small" and synth.models == ["small"]

    @pytest.mark.parametrize(
        ("inp", "message"),
        [
            ({}, "two catalog keys"),
            ({"books": [A]}, "two catalog keys"),
            ({"books": [A, A]}, "two different books"),
            ({"books": [A, "fiction/Nope"]}, "unknown book"),
            ({"books": [A, B], "turns": 1}, "turns must be"),
            ({"books": [A, B], "turns": 41}, "turns must be"),
            ({"books": [A, B], "k": 0}, "k must be"),
            ({"books": [A, B], "turns": "many"}, "integers"),
        ],
    )
    def test_bad_requests_are_refused(self, inp, message):
        out = _sessions().handle("moot_start", inp)
        assert message in out["error"]


class TestTurns:
    def test_turns_arrive_in_order_and_the_last_is_done(self):
        s = _sessions()
        mid = s.handle("moot_start", {"books": [A, B], "topic": "virtue", "turns": 3})["moot_id"]
        outs = [s.handle("moot_turn", {"moot_id": mid}) for _ in range(3)]
        assert [o["turn"]["turn"] for o in outs] == [1, 2, 3]
        assert [o["turn"]["speaker"] for o in outs] == [0, 1, 0]
        assert [o["done"] for o in outs] == [False, False, True]
        assert outs[-1]["stats"]["turns"] == 3
        assert mid not in s.sessions

    def test_a_turn_is_what_the_reader_sees(self):
        s = _sessions()
        mid = s.handle("moot_start", {"books": [A, B], "turns": 2})["moot_id"]
        turn = s.handle("moot_turn", {"moot_id": mid})["turn"]
        assert set(turn) == {"turn", "speaker", "text", "cites", "grounded", "snaps"}
        assert turn["cites"] == [{"tag": "s1", "label": "chunk:0001", "node_id": f"{A}#1"}]
        json.dumps(turn)

    def test_unknown_moot(self):
        assert "no such moot" in _sessions().handle("moot_turn", {"moot_id": "nope"})["error"]

    def test_a_backend_failure_keeps_the_moot_for_a_retry(self):
        s = _sessions(FakeSynth(fail_first=1))
        mid = s.handle("moot_start", {"books": [A, B], "turns": 2})["moot_id"]
        assert "ConnectionError" in s.handle("moot_turn", {"moot_id": mid})["error"]
        assert s.handle("moot_turn", {"moot_id": mid})["turn"]["turn"] == 1

    def test_stop_drops_the_moot(self):
        s = _sessions()
        mid = s.handle("moot_start", {"books": [A, B]})["moot_id"]
        assert s.handle("moot_stop", {"moot_id": mid}) == {"stopped": True}
        assert s.handle("moot_stop", {"moot_id": mid}) == {"stopped": False}


class TestLimits:
    def test_an_idle_moot_expires(self):
        clock = Clock()
        s = _sessions(clock=clock)
        mid = s.handle("moot_start", {"books": [A, B]})["moot_id"]
        clock.t += moot_ops.IDLE_SECONDS + 1
        assert "no such moot" in s.handle("moot_turn", {"moot_id": mid})["error"]

    def test_a_full_table_drops_the_least_recently_used(self):
        clock = Clock()
        s = _sessions(clock=clock)
        ids = []
        for _ in range(moot_ops.MAX_SESSIONS):
            ids.append(s.handle("moot_start", {"books": [A, B]})["moot_id"])
            clock.t += 1
        s.handle("moot_turn", {"moot_id": ids[0]})  # the oldest is used again
        clock.t += 1
        newest = s.handle("moot_start", {"books": [A, "x/C"]})["moot_id"]
        assert len(s.sessions) == moot_ops.MAX_SESSIONS
        assert ids[1] not in s.sessions
        assert {ids[0], newest} <= set(s.sessions)
