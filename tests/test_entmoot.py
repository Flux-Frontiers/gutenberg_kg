"""Entmoot: the moot loop and its grounding check, with no network and no model."""

from __future__ import annotations

import json
import types

import pytest
from click.testing import CliRunner

from gutenberg_kg.serve import entmoot
from gutenberg_kg.serve.entmoot import (
    MootError,
    Passage,
    check_grounding,
    parse_tags,
    retrieval_query,
    run_moot,
)

A = "philosophy/Thus Spake Zarathustra"
B = "diaries/The Diary of Somebody"


class FakeClient:
    """Records every query; each book returns two passages of its own."""

    def __init__(self):
        self.calls: list[tuple[str, str, int]] = []

    def query(self, query, *, corpus="all", k=8, **_kw):
        self.calls.append((query, corpus, k))
        diary = corpus.startswith("diaries/")
        hits = [
            {
                "node_id": f"{corpus}#{i}",
                "name": f"chunk:{i:04d}",
                "content": f"{corpus} passage {i}: jealousy is a dreadful thing indeed",
                "title": corpus.split("/", 1)[1],
                "author": "Someone",
                "genre": corpus.split("/", 1)[0],
                "timestamp": f"1664-01-1{i}T00:00" if diary else None,
            }
            for i in range(1, 3)
        ]
        return {"hits": hits[:k]}


class FakeSynth:
    """Returns scripted replies in order, then repeats the last one."""

    def __init__(self, replies=None):
        self.replies = list(replies or ["Hear me [s1]."])
        self.calls: list[list[dict]] = []
        self.models: set = set()

    def complete(self, messages, *, model=None, max_tokens=None, temperature=0.7):
        assert max_tokens == entmoot.MAX_TOKENS
        self.calls.append(messages)
        self.models.add(model)
        if self._is_summary(messages):
            return "A neutral summary."
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]

    @staticmethod
    def _is_summary(messages):
        return "neutral narrator" in messages[0]["content"]

    def turn_calls(self):
        return [m for m in self.calls if not self._is_summary(m)]

    def summary_calls(self):
        return [m for m in self.calls if self._is_summary(m)]


def _passages(*contents):
    return [
        Passage(tag=f"s{i}", label="x", node_id=f"n{i}", content=c)
        for i, c in enumerate(contents, 1)
    ]


# ---------------------------------------------------------------------------
# run_moot
# ---------------------------------------------------------------------------


class TestRunMoot:
    def test_speakers_alternate_and_turn_count_is_respected(self):
        t = run_moot(FakeClient(), FakeSynth(), [A, B], "jealousy", 5)
        assert [u.speaker for u in t.utterances] == [A, B, A, B, A]

    def test_retrieval_for_a_tree_only_uses_its_own_key(self):
        client = FakeClient()
        t = run_moot(client, FakeSynth(), [A, B], "jealousy", 6)
        for u in t.utterances:
            assert all(r["node_id"].startswith(u.speaker + "#") for r in u.retrieved)
        assert {c[1] for c in client.calls} == {A, B}

    def test_trees_are_named_from_the_first_hit(self):
        t = run_moot(FakeClient(), FakeSynth(), [A, B], "jealousy", 2)
        assert [tr.title for tr in t.trees] == ["Thus Spake Zarathustra", "The Diary of Somebody"]
        assert t.trees[1].genre == "diaries"

    def test_diary_passages_are_labeled_by_date(self):
        t = run_moot(FakeClient(), FakeSynth(), [A, B], "jealousy", 2)
        assert t.utterances[1].retrieved[0]["label"] == "1664-01-11"
        assert t.utterances[0].retrieved[0]["label"] == "chunk:0001"

    def test_summary_fires_on_schedule(self):
        synth = FakeSynth()
        t = run_moot(FakeClient(), synth, [A, B], "jealousy", 9)
        assert [s["before_turn"] for s in t.summaries] == [5, 9]
        assert len(synth.summary_calls()) == 2
        # The turn after a summary sees it.
        assert "A neutral summary." in synth.turn_calls()[4][1]["content"]

    def test_no_summary_in_a_short_moot(self):
        t = run_moot(FakeClient(), FakeSynth(), [A, B], None, 4)
        assert t.summaries == []

    def test_transcript_is_json_ready_with_stats(self):
        t = run_moot(FakeClient(), FakeSynth(), [A, B], "jealousy", 2, model_name="m")
        data = json.loads(json.dumps(t.to_dict()))
        assert data["model"] == "m"
        assert data["stats"]["turns"] == 2
        assert data["stats"]["tags_valid_rate"] == 1.0
        assert data["stats"]["quote_found_rate"] is None
        assert data["utterances"][0]["cited"] == {"s1": f"{A}#1"}


class TestTopicSeeding:
    def test_opening_retrieval_uses_the_topic_alone(self):
        client = FakeClient()
        run_moot(client, FakeSynth(), [A, B], "jealousy", 2)
        assert client.calls[0] == ("jealousy", A, 6)
        assert client.calls[1] == ("jealousy", B, 6)

    def test_later_queries_carry_topic_and_incoming_line(self):
        client = FakeClient()
        synth = FakeSynth(["Opening line [s1].", "Second line [s2]."])
        t = run_moot(client, synth, [A, B], "jealousy", 3)
        assert client.calls[2] == ("jealousy Opening line [s1].", B, 6)
        assert client.calls[3] == ("jealousy Second line [s2].", A, 6)
        assert t.utterances[0].query == "jealousy"

    def test_without_topic_later_queries_use_the_incoming_line_only(self):
        client = FakeClient()
        synth = FakeSynth(["Opening line [s1].", "Second line [s2]."])
        run_moot(client, synth, [A, B], None, 3)
        assert client.calls[2][0] == "Opening line [s1]."
        assert client.calls[3][0] == "Second line [s2]."

    def test_persona_names_the_topic(self):
        synth = FakeSynth()
        run_moot(FakeClient(), synth, [A, B], "a good death", 2)
        assert "The moot has gathered to discuss: a good death" in synth.calls[0][0]["content"]

    def test_retrieval_query_rule(self):
        assert retrieval_query("London", "the fire") == "London the fire"
        assert retrieval_query(None, "the fire") == "the fire"


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------


class TestCheckGrounding:
    P = _passages("God forgive me for my  jealousy! but I cannot forbear.", "Second passage text.")

    @pytest.mark.parametrize(
        "text,tags",
        [
            ("A claim [s1].", ["s1"]),
            ("Two claims [s1, s2].", ["s1", "s2"]),
            ("Two claims [s1][s2].", ["s1", "s2"]),
            ("A claim (s2).", ["s2"]),
            ("Upper case [S1].", ["s1"]),
        ],
    )
    def test_accepted_tag_forms(self, text, tags):
        assert parse_tags(text) == tags
        assert check_grounding(text, self.P)["tags_valid"]

    def test_invented_tag(self):
        g = check_grounding("A claim [s1] and another [s9].", self.P)
        assert not g["tags_valid"]
        assert g["tags_cited"] == 2

    def test_no_tags_is_vacuously_valid_but_counted(self):
        g = check_grounding("No citation at all.", self.P)
        assert g["tags_valid"] and g["tags_cited"] == 0

    def test_quote_found(self):
        g = check_grounding('He wrote "God forgive me for my jealousy" [s1].', self.P)
        assert (g["quotes_found"], g["quotes_total"]) == (1, 1)

    def test_quote_not_found(self):
        g = check_grounding('He wrote "God bless my envy entirely" [s1].', self.P)
        assert (g["quotes_found"], g["quotes_total"]) == (0, 1)

    def test_quote_may_come_from_any_passage_given_this_turn(self):
        g = check_grounding('"Second passage text" [s1].', self.P)
        assert g["quotes_found"] == 1

    def test_curly_quotes_and_apostrophes(self):
        p = _passages("I can't forbear, said he.")
        g = check_grounding("\u201cI can\u2019t forbear\u201d [s1].", p)
        assert (g["quotes_found"], g["quotes_total"]) == (1, 1)

    def test_whitespace_and_case_are_normalized(self):
        g = check_grounding('"GOD FORGIVE   me\nfor my jealousy" [s1]', self.P)
        assert g["quotes_found"] == 1

    def test_short_quotes_are_ignored(self):
        assert check_grounding('the "two words" [s1]', self.P)["quotes_total"] == 0


class TestRetry:
    def test_one_retry_then_success(self):
        synth = FakeSynth(["Bad [s9].", "Good [s1]."])
        t = run_moot(FakeClient(), synth, [A, B], "jealousy", 2)
        first = t.utterances[0]
        assert first.attempts == 2 and first.grounded and first.text == "Good [s1]."
        assert "did not hold to your passages" in synth.turn_calls()[1][-1]["content"]

    def test_two_failures_keep_the_reply_marked_ungrounded(self):
        synth = FakeSynth(["Bad [s9].", "Still bad [s7].", "Fine [s1]."])
        t = run_moot(FakeClient(), synth, [A, B], "jealousy", 2)
        first = t.utterances[0]
        assert first.attempts == 2 and not first.grounded
        assert first.text == "Still bad [s7]."
        assert len(t.utterances) == 2  # never dropped
        assert t.stats()["grounded_turns"] == 1

    def test_no_text_from_the_model_raises(self):
        class Dead:
            def complete(self, *_a, **_kw):
                return None

        with pytest.raises(MootError):
            run_moot(FakeClient(), Dead(), [A, B], "jealousy", 2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_shell_backend(monkeypatch):
    """Keep the developer's SYNTH_BACKEND out of the CLI's default backend."""
    monkeypatch.delenv("SYNTH_BACKEND", raising=False)


@pytest.fixture
def cli():
    pytest.importorskip("kg_rag", reason="kg_rag not installed")
    from gutenberg_kg.cli.main import cli as root

    return root


def test_converse_help(cli):
    result = CliRunner().invoke(cli, ["converse", "--help"])
    assert result.exit_code == 0
    assert "SYNTH_ENDPOINT" in result.output
    assert "--topic" in result.output


def test_converse_rejects_a_malformed_key(cli):
    result = CliRunner().invoke(cli, ["converse", "Meditations", A])
    assert result.exit_code == 2
    assert "not a <genre>/<book> key" in result.output


def test_converse_unknown_book_is_a_clean_error(cli, monkeypatch):
    from kg_utils.worker import WorkerError

    from gutenberg_kg.cli import cmd_converse

    class Rejecting:
        def query(self, *_a, **_kw):
            raise WorkerError("unknown corpus 'philosophy/Nope'")

    monkeypatch.setattr(cmd_converse, "_make_client", lambda url: Rejecting())
    monkeypatch.setattr(cmd_converse, "_make_synth", lambda backend: FakeSynth())
    result = CliRunner().invoke(cli, ["converse", "philosophy/Nope", A])
    assert result.exit_code == 1
    assert "worker error: unknown corpus" in result.output
    assert "Traceback" not in result.output


def test_converse_writes_a_transcript(cli, monkeypatch, tmp_path):
    from gutenberg_kg.cli import cmd_converse

    monkeypatch.setattr(cmd_converse, "_make_client", lambda url: FakeClient())
    synth = FakeSynth()
    monkeypatch.setattr(cmd_converse, "_make_synth", lambda backend: synth)
    out = tmp_path / "moot.json"
    result = CliRunner().invoke(
        cli, ["converse", A, B, "--topic", "jealousy", "--turns", "2", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "[1] Thus Spake Zarathustra: Hear me [s1]." in result.output
    data = json.loads(out.read_text())
    assert data["model"] == entmoot.DEFAULT_MODEL
    assert synth.models == {entmoot.DEFAULT_MODEL}
    assert data["stats"]["turns"] == 2
    assert data["stats"]["other_quotes_total"] == 0


def test_converse_model_overrides_the_default(cli, monkeypatch):
    from gutenberg_kg.cli import cmd_converse

    synth = FakeSynth()
    monkeypatch.setattr(cmd_converse, "_make_client", lambda url: FakeClient())
    monkeypatch.setattr(cmd_converse, "_make_synth", lambda backend: synth)
    result = CliRunner().invoke(cli, ["converse", A, B, "--turns", "2", "--model", "small"])
    assert result.exit_code == 0, result.output
    assert synth.models == {"small"}


def test_converse_help_names_the_default_model(cli):
    result = CliRunner().invoke(cli, ["converse", "--help"])
    assert entmoot.DEFAULT_MODEL in result.output
    assert "SYNTH_MODEL" in result.output  # documented as not applying on omlx
    for backend in ("omlx", "ollama", "openai"):
        assert backend in result.output


class ConfiguredSynth(FakeSynth):
    """A FakeSynth that carries a TextConfig, as TextSynthesizer does."""

    def __init__(self, default_model):
        super().__init__()
        self._cfg = types.SimpleNamespace(resolved_model=lambda: default_model)


def test_converse_off_omlx_uses_the_backend_default_model(cli, monkeypatch, tmp_path):
    from gutenberg_kg.cli import cmd_converse

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    seen = []
    synth = ConfiguredSynth("gpt-4o-mini")
    monkeypatch.setattr(cmd_converse, "_make_client", lambda url: FakeClient())
    monkeypatch.setattr(cmd_converse, "_make_synth", lambda backend: seen.append(backend) or synth)
    out = tmp_path / "moot.json"
    result = CliRunner().invoke(
        cli, ["converse", A, B, "--turns", "2", "--backend", "openai", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert seen == ["openai"]
    assert synth.models == {None}  # the synthesizer's own default applies
    assert json.loads(out.read_text())["model"] == "gpt-4o-mini"
    assert "Speaking through openai: gpt-4o-mini" in result.output


def test_converse_model_overrides_any_backend(cli, monkeypatch):
    from gutenberg_kg.cli import cmd_converse

    synth = ConfiguredSynth("llama-default")
    monkeypatch.setattr(cmd_converse, "_make_client", lambda url: FakeClient())
    monkeypatch.setattr(cmd_converse, "_make_synth", lambda backend: synth)
    result = CliRunner().invoke(
        cli, ["converse", A, B, "--turns", "2", "--backend", "ollama", "--model", "mine"]
    )
    assert result.exit_code == 0, result.output
    assert synth.models == {"mine"}


def test_converse_backend_defaults_to_synth_backend(cli, monkeypatch):
    from gutenberg_kg.cli import cmd_converse

    seen = []
    monkeypatch.setenv("SYNTH_BACKEND", "ollama")
    monkeypatch.setattr(cmd_converse, "_make_client", lambda url: FakeClient())
    monkeypatch.setattr(
        cmd_converse, "_make_synth", lambda backend: seen.append(backend) or FakeSynth()
    )
    result = CliRunner().invoke(cli, ["converse", A, B, "--turns", "2"])
    assert result.exit_code == 0, result.output
    assert seen == ["ollama"]


def test_converse_unknown_synth_backend_falls_back_to_omlx(cli, monkeypatch):
    from gutenberg_kg.cli import cmd_converse

    seen = []
    monkeypatch.setenv("SYNTH_BACKEND", "nonsense")
    monkeypatch.setattr(cmd_converse, "_make_client", lambda url: FakeClient())
    monkeypatch.setattr(
        cmd_converse, "_make_synth", lambda backend: seen.append(backend) or FakeSynth()
    )
    result = CliRunner().invoke(cli, ["converse", A, B, "--turns", "2"])
    assert result.exit_code == 0, result.output
    assert seen == ["omlx"]


def test_converse_rejects_an_unknown_backend(cli):
    result = CliRunner().invoke(cli, ["converse", A, B, "--backend", "nonsense"])
    assert result.exit_code == 2
    assert "nonsense" in result.output


def test_converse_openai_without_a_key_is_a_clean_error(cli, monkeypatch):
    from gutenberg_kg.cli import cmd_converse

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SYNTH_API_KEY", raising=False)
    monkeypatch.setattr(cmd_converse, "_make_client", lambda url: FakeClient())
    monkeypatch.setattr(cmd_converse, "_make_synth", lambda backend: FakeSynth())
    result = CliRunner().invoke(cli, ["converse", A, B, "--backend", "openai"])
    assert result.exit_code == 2
    assert "needs OPENAI_API_KEY or SYNTH_API_KEY" in result.output


def test_make_synth_routes_by_backend(monkeypatch):
    from gutenberg_kg.cli import cmd_converse

    monkeypatch.setenv("SYNTH_BACKEND", "omlx")
    monkeypatch.setenv("SYNTH_ENDPOINT", "http://example.invalid:9999/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    same = cmd_converse._make_synth("omlx")
    other = cmd_converse._make_synth("openai")
    assert same._cfg.backend.value == "omlx"
    assert same._cfg.endpoint == "http://example.invalid:9999/v1"  # full env config
    assert other._cfg.backend.value == "openai"
    assert other._cfg.api_key == "test-key"  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Revised grounding: the per-tree pool and [oN] quotes of the other tree
# ---------------------------------------------------------------------------


class KeyedSynth(FakeSynth):
    """Replies per speaker: picks the reply list by the persona's book title."""

    def __init__(self, by_title):
        super().__init__()
        self.by_title = {t: list(r) for t, r in by_title.items()}

    def complete(self, messages, *, model=None, max_tokens=None, temperature=0.7):
        self.calls.append(messages)
        if self._is_summary(messages):
            return "A neutral summary."
        for title, replies in self.by_title.items():
            if messages[0]["content"].startswith(f"You are the book {title}"):
                return replies.pop(0) if len(replies) > 1 else replies[0]
        raise AssertionError("unknown speaker")


class TurnClient(FakeClient):
    """Each query returns new passages, so earlier passages leave the turn."""

    def query(self, query, *, corpus="all", k=8, **_kw):
        self.calls.append((query, corpus, k))
        n = len(self.calls)
        return {
            "hits": [
                {
                    "node_id": f"{corpus}#q{n}",
                    "name": f"chunk:{n:04d}",
                    "content": f"{corpus} only says: unique words number {n} here",
                    "title": corpus.split("/", 1)[1],
                    "genre": corpus.split("/", 1)[0],
                }
            ]
        }


ZARA = "Thus Spake Zarathustra"
SOMEBODY = "The Diary of Somebody"


class TestRevisedGrounding:
    def test_own_quote_from_an_earlier_turn_is_found(self):
        # A's opening passage (query 1) is not in A's turn-3 passages (query 3),
        # but it came from A's own book during this moot.
        synth = KeyedSynth(
            {
                ZARA: ["Opening [s1].", f'As I said, "{A} only says: unique words number 1" [s1].'],
                SOMEBODY: ["Reply [s1]."],
            }
        )
        t = run_moot(TurnClient(), synth, [A, B], "jealousy", 3)
        third = t.utterances[2]
        assert third.grounding["quotes_total"] == 1
        assert third.grounding["quotes_found"] == 1
        assert third.attempts == 1 and third.grounded

    def test_valid_other_quote(self):
        synth = KeyedSynth(
            {
                ZARA: ["I speak of the scorpion and its sting [s1]."],
                SOMEBODY: ['You said "the scorpion and its sting" [o1], and I agree [s1].'],
            }
        )
        t = run_moot(TurnClient(), synth, [A, B], "jealousy", 2)
        g = t.utterances[1].grounding
        assert (g["other_quotes_found"], g["other_quotes_total"]) == (1, 1)
        assert (g["quotes_found"], g["quotes_total"]) == (0, 0)  # never counts as own
        assert t.utterances[1].grounded
        assert t.stats()["other_quote_valid_rate"] == 1.0

    def test_invalid_other_quote_does_not_affect_grounding(self):
        synth = KeyedSynth(
            {
                ZARA: ["I speak of the scorpion and its sting [s1]."],
                SOMEBODY: ['You said "the eagle and the serpent" [o1] [s1].'],
            }
        )
        t = run_moot(TurnClient(), synth, [A, B], "jealousy", 2)
        u = t.utterances[1]
        assert (u.grounding["other_quotes_found"], u.grounding["other_quotes_total"]) == (0, 1)
        assert u.grounded and u.attempts == 1
        assert u.quotes == [
            {"text": "the eagle and the serpent", "found": False, "source": "other"}
        ]

    def test_other_quote_pointing_at_own_turn_is_invalid(self):
        synth = KeyedSynth(
            {
                ZARA: [
                    "I speak of the scorpion and its sting [s1].",
                    'I said "the scorpion and its sting" [o1].',
                ],
                SOMEBODY: ["Reply [s1]."],
            }
        )
        t = run_moot(TurnClient(), synth, [A, B], "jealousy", 3)
        assert t.utterances[2].grounding["other_quotes_found"] == 0

    def test_other_tree_quoted_under_an_s_tag_is_still_a_miss(self):
        synth = KeyedSynth(
            {
                ZARA: ["I speak of the scorpion and its sting [s1]."],
                SOMEBODY: [
                    'Indeed "the scorpion and its sting" [s1].',
                    'Indeed "the scorpion and its sting" [s1].',
                ],
            }
        )
        t = run_moot(TurnClient(), synth, [A, B], "jealousy", 2)
        u = t.utterances[1]
        assert (u.grounding["quotes_found"], u.grounding["quotes_total"]) == (0, 1)
        assert u.grounding["other_quotes_total"] == 0
        assert not u.grounded and u.attempts == 2

    def test_the_pool_never_mixes_books(self):
        # B quotes A's opening passage: A's book, so outside B's pool.
        synth = KeyedSynth(
            {
                ZARA: ["Opening [s1]."],
                SOMEBODY: [f'"{A} only says: unique words number 1" [s1].'],
            }
        )
        t = run_moot(TurnClient(), synth, [A, B], "jealousy", 2)
        assert t.utterances[1].grounding["quotes_found"] == 0
        for u in t.utterances:
            assert all(r["node_id"].startswith(u.speaker + "#") for r in u.retrieved)

    def test_tag_before_the_other_quote_attaches(self):
        p = _passages("own text here only")
        g = check_grounding(
            '[o1] "the scorpion and its sting"', p, others={1: "the scorpion and its sting"}
        )
        assert g["other_quotes_found"] == 1

    def test_utterances_are_numbered_from_one_and_shown_to_the_model(self):
        synth = FakeSynth(["First [s1].", "Second [s1].", "Third [s1]."])
        t = run_moot(FakeClient(), synth, [A, B], "jealousy", 3)
        assert [u.turn for u in t.utterances] == [1, 2, 3]
        assert (
            "Turn 2, Thus Spake Zarathustra has just said"
            not in synth.turn_calls()[2][1]["content"]
        )
        assert (
            "Turn 2, The Diary of Somebody has just said: Second [s1]."
            in synth.turn_calls()[2][1]["content"]
        )
        assert "[oN]" in synth.turn_calls()[0][0]["content"]


def test_a_quote_takes_the_tag_after_it_not_the_previous_quotes_tag():
    """From a live run: an own quote right after an [oN] quote was read as the other tree's."""
    p = _passages("How I distrust all of you, insidious beauty!")
    text = 'You say "jealous of my kindnesse" [o1]. I "distrust all of you" for your "insidious beauty" [s1].'
    g = check_grounding(text, p, others={1: "she is jealous of my kindnesse to her"})
    assert (g["quotes_found"], g["quotes_total"]) == (1, 1)
    assert (g["other_quotes_found"], g["other_quotes_total"]) == (1, 1)


# ---------------------------------------------------------------------------
# Ellipsis fragments, the quote cap and the same-book guard
# ---------------------------------------------------------------------------


class TestEllipsisQuotes:
    P = _passages("I see great cause every day to curse the time that ever I did give way.")

    def test_all_fragments_found(self):
        g = check_grounding('"I see great cause... to curse the time" [s1]', self.P)
        assert (g["quotes_found"], g["quotes_total"]) == (1, 1)

    def test_one_fragment_missing(self):
        g = check_grounding('"I see great cause... to bless the day" [s1]', self.P)
        assert (g["quotes_found"], g["quotes_total"]) == (0, 1)

    def test_short_fragments_are_ignored(self):
        # "great cause" is under 3 words; only "to curse the time" is checked.
        g = check_grounding('"great cause... to curse the time" [s1]', self.P)
        assert g["quotes_found"] == 1

    def test_all_fragments_short_checks_the_quote_whole(self):
        g = check_grounding('"great cause... curse it" [s1]', self.P)
        assert (g["quotes_found"], g["quotes_total"]) == (0, 1)

    def test_unicode_ellipsis(self):
        g = check_grounding('"I see great cause… to curse the time" [s1]', self.P)
        assert g["quotes_found"] == 1

    def test_rewording_stays_a_miss(self):
        g = check_grounding('"I see great cause... to cursed the time" [s1]', self.P)
        assert g["quotes_found"] == 0

    def test_fragments_of_an_other_quote_are_checked_in_that_turn(self):
        p = _passages("own text")
        others = {1: "the scorpion turneth at last the poisoned sting against himself"}
        g = check_grounding(
            '"the scorpion turneth... poisoned sting against himself" [o1]', p, others=others
        )
        assert (g["other_quotes_found"], g["other_quotes_total"]) == (1, 1)
        g = check_grounding(
            '"the scorpion turneth... honey against himself" [o1]', p, others=others
        )
        assert g["other_quotes_found"] == 0


def test_quote_cap_is_in_the_persona_and_reminder():
    synth = FakeSynth(["Bad [s9].", "Good [s1]."])
    run_moot(FakeClient(), synth, [A, B], "jealousy", 2)
    calls = synth.turn_calls()
    assert f"at most {entmoot.MAX_QUOTES} quoted phrases" in calls[0][0]["content"]
    assert f"at most {entmoot.MAX_QUOTES} quoted phrases" in calls[1][-1]["content"]


def test_quotes_per_turn_counts_own_and_other_quotes():
    synth = KeyedSynth(
        {
            ZARA: ["I speak of the scorpion and its sting [s1]."],
            SOMEBODY: ['"the scorpion and its sting" [o1] and "one two three four" [s1].'],
        }
    )
    t = run_moot(TurnClient(), synth, [A, B], "jealousy", 2)
    assert t.stats()["quotes_per_turn"] == 1.0  # 0 + 2 quotes over 2 turns


def test_run_moot_rejects_the_same_book_twice():
    with pytest.raises(ValueError, match="two different books"):
        run_moot(FakeClient(), FakeSynth(), [A, A], "jealousy", 2)


def test_converse_rejects_the_same_book_twice(cli, monkeypatch):
    from gutenberg_kg.cli import cmd_converse

    monkeypatch.setattr(cmd_converse, "_make_client", lambda url: FakeClient())
    monkeypatch.setattr(cmd_converse, "_make_synth", lambda backend: FakeSynth())
    result = CliRunner().invoke(cli, ["converse", A, A])
    assert result.exit_code == 2
    assert "the two books must differ" in result.output
