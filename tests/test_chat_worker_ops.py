"""Unit tests for the chat UI's worker-facing helpers (``serve/Chat.py``).

Covers the bare-op calls (``_worker_op`` / ``_fetch_stats`` / ``_corpus_options``)
and the synthesis-model filtering that ``_fetch_models`` applies.

These cover the regression that made the sidebar crash: the worker rejects a
bad or absent secret with a **200 carrying** ``{"error": "unauthorized"}``, so
``raise_for_status()`` does not fire and the error dict used to be returned
verbatim — truthy, which sent ``_render_sidebar`` down its success path and into
``stats['books']``.

Only ``streamlit`` is stubbed. It is the one import that cannot survive a
headless test run (``Chat.py`` builds its whole page at module import), and
nothing else in the suite imports it. ``st.cache_data`` needs to be an identity
decorator rather than part of the mock: left as a ``MagicMock`` attribute it
replaces every decorated function with a mock, so the memoised helpers could not
be called at all — and as a bonus there is no cache bleed between tests.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# Overridden unconditionally, not via setdefault. CI installs `--extras dev`, so
# streamlit is absent there and the stub is what makes this module importable at
# all — but a developer running `--all-extras` would otherwise get the real
# `st.cache_data`, which memoises `_fetch_stats`/`_corpus_options` across tests
# and makes results depend on execution order. Nothing else in the suite imports
# streamlit, so replacing it here is contained.
_streamlit = MagicMock()
_streamlit.cache_data = lambda *a, **kw: lambda fn: fn
sys.modules["streamlit"] = _streamlit

import httpx  # noqa: E402

from gutenberg_kg.serve import Chat  # noqa: E402


def _post(payload=None, exc=None):
    """Build a fake ``httpx.post`` that records what it was sent."""

    def _fake(url, json=None, timeout=None):
        _fake.sent_url = url
        _fake.sent = json
        if exc is not None:
            raise exc
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=payload)
        return resp

    return _fake


class TestWorkerOp:
    def test_unwraps_the_runpod_output_envelope(self):
        post = _post({"output": {"books": 241, "genres": 20}})
        with patch.object(httpx, "post", post):
            assert Chat._worker_op("http://w:8000", "stats", "") == {"books": 241, "genres": 20}

    def test_accepts_a_bare_payload_without_the_envelope(self):
        post = _post({"books": 3})
        with patch.object(httpx, "post", post):
            assert Chat._worker_op("http://w:8000", "stats", "") == {"books": 3}

    def test_secret_sent_only_when_configured(self):
        post = _post({"output": {}})
        with patch.object(httpx, "post", post):
            Chat._worker_op("http://w:8000", "stats", "s3cret")
        assert post.sent["input"]["secret"] == "s3cret"

        post = _post({"output": {}})
        with patch.object(httpx, "post", post):
            Chat._worker_op("http://w:8000", "stats", "")
        assert "secret" not in post.sent["input"]

    def test_op_name_is_forwarded(self):
        post = _post({"output": {}})
        with patch.object(httpx, "post", post):
            Chat._worker_op("http://w:8000", "list_genres", "")
        assert post.sent["input"]["op"] == "list_genres"

    def test_trailing_slash_does_not_double_up(self):
        post = _post({"output": {}})
        with patch.object(httpx, "post", post):
            Chat._worker_op("http://w:8000/", "stats", "")
        assert post.sent_url == "http://w:8000/runsync"

    @pytest.mark.parametrize(
        "exc",
        [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
    )
    def test_transport_failure_returns_empty(self, exc):
        with patch.object(httpx, "post", _post(exc=exc)):
            assert Chat._worker_op("http://w:8000", "stats", "") == {}

    def test_error_payload_returns_empty_not_the_error_dict(self):
        # The regression. A 200 carrying an error body must not come back
        # truthy — that is what put a KeyError traceback in the sidebar.
        post = _post({"output": {"error": "unauthorized"}})
        with patch.object(httpx, "post", post):
            assert Chat._worker_op("http://w:8000", "stats", "") == {}

    def test_non_dict_output_returns_empty(self):
        post = _post({"output": ["not", "a", "dict"]})
        with patch.object(httpx, "post", post):
            assert Chat._worker_op("http://w:8000", "stats", "") == {}


class TestFetchStats:
    def test_unauthorized_is_falsy_so_the_sidebar_takes_the_offline_branch(self):
        post = _post({"output": {"error": "unauthorized"}})
        with patch.object(httpx, "post", post):
            stats = Chat._fetch_stats("http://w:8000", "")
        assert stats == {}
        assert not stats  # the condition `_render_sidebar` actually branches on

    def test_totals_pass_through(self):
        post = _post({"output": {"books": 241, "genres": 20, "diaries": 4}})
        with patch.object(httpx, "post", post):
            stats = Chat._fetch_stats("http://w:8000", "")
        assert stats["books"] == 241
        assert stats["diaries"] == 4


class TestCorpusOptions:
    def test_genres_bookended_by_all_and_diary(self):
        post = _post({"output": {"genres": [{"genre": "philosophy"}, {"genre": "poetry"}]}})
        with patch.object(httpx, "post", post):
            assert Chat._corpus_options("http://w:8000", "") == [
                "all",
                "philosophy",
                "poetry",
                "diary",
            ]

    def test_diaries_genre_folded_into_the_diary_scope(self):
        post = _post({"output": {"genres": [{"genre": "diaries"}, {"genre": "philosophy"}]}})
        with patch.object(httpx, "post", post):
            assert Chat._corpus_options("http://w:8000", "") == ["all", "philosophy", "diary"]

    def test_error_payload_degrades_to_the_two_base_scopes(self):
        post = _post({"output": {"error": "unauthorized"}})
        with patch.object(httpx, "post", post):
            assert Chat._corpus_options("http://w:8000", "") == ["all", "diary"]

    def test_offline_worker_degrades_to_the_two_base_scopes(self):
        with patch.object(httpx, "post", _post(exc=httpx.ConnectError("refused"))):
            assert Chat._corpus_options("http://w:8000", "") == ["all", "diary"]

    def test_blank_genre_names_dropped(self):
        post = _post({"output": {"genres": [{"genre": ""}, {"genre": "philosophy"}, {}]}})
        with patch.object(httpx, "post", post):
            assert Chat._corpus_options("http://w:8000", "") == ["all", "philosophy", "diary"]


# ---------------------------------------------------------------------------
# _is_synth_model / _MODEL_BLOCKLIST
# ---------------------------------------------------------------------------


class TestIsSynthModel:
    """The blocklist keeps unusable models out of the sidebar's Model picker.

    It originated here and was ported to corpus_pepys, which covered it first;
    this backfills the gap so both copies are pinned. A model that slips through
    does not error visibly — a reasoning model emits its chain-of-thought as
    prose into the answer pane, which reads as a bad answer rather than a bad
    model choice.
    """

    @pytest.mark.parametrize(
        "model_id",
        [
            "Qwen3-4B-Instruct-2507-MLX-8bit",
            "Qwen3-30B-A3B-Instruct-2507-MLX-4bit",
            "llama3.1:8b",
            "gpt-4o-mini",
            "mistral-small",
        ],
    )
    def test_ordinary_chat_models_allowed(self, model_id):
        assert Chat._is_synth_model(model_id)

    @pytest.mark.parametrize(
        "model_id",
        [
            "Agents-A1-32B",  # unstrippable "Thinking Process:" prose
            "deepseek-r1:14b",  # R1 reasoning model
            "gpt-oss-20b",  # harmony channels leak into content
            "markitdown-1b",  # document converter, not a chat model
            "nomic-embed-text",  # embedding models fail the request outright
            "mxbai-embed-large",
            "Qwen3-Embedding-0.6B",
        ],
    )
    def test_reasoning_and_non_chat_models_blocked(self, model_id):
        assert not Chat._is_synth_model(model_id)

    def test_matching_is_case_insensitive(self):
        assert not Chat._is_synth_model("DEEPSEEK-R1")
        assert not Chat._is_synth_model("DeepSeek-R1:70b")

    def test_blocklist_matches_as_substring_anywhere(self):
        # Backends namespace their ids differently; the pattern has to hit
        # wherever it appears, not just at the start.
        assert not Chat._is_synth_model("hosted/team/nomic-embed-text-v1.5")

    def test_blocklist_contents_are_pinned(self):
        # Spelled out so a silent edit here shows up as a test change, and so
        # the corpus_pepys copy can be diffed against it by eye.
        assert set(Chat._MODEL_BLOCKLIST) == {
            "agents-a1",
            "deepseek-r1",
            "gpt-oss",
            "markitdown",
            "embed",
        }

    def test_every_pattern_is_lowercase(self):
        # _is_synth_model lowercases the id but not the patterns, so an
        # upper-case entry would silently never match.
        assert all(p == p.lower() for p in Chat._MODEL_BLOCKLIST)


# ---------------------------------------------------------------------------
# _fetch_models — where the blocklist is actually applied
# ---------------------------------------------------------------------------


class TestFetchModels:
    @staticmethod
    def _client(models, default):
        client = MagicMock()
        client.list_models = MagicMock(return_value=(models, default))
        return MagicMock(return_value=client)

    def test_blocklisted_models_dropped_from_the_dropdown(self):
        factory = self._client(["qwen3-4b", "deepseek-r1:8b", "nomic-embed-text"], "qwen3-4b")
        with patch.object(Chat, "WorkerClient", factory):
            models, default = Chat._fetch_models("http://w:8000", "")
        assert models == ["qwen3-4b"]
        assert default == "qwen3-4b"

    def test_blocklisted_default_replaced_with_first_allowed_model(self):
        # The case that needs no user interaction at all: the backend reports a
        # reasoning model as its default, so it is what runs unless replaced.
        factory = self._client(["gpt-oss-20b", "qwen3-4b", "llama3.1"], "gpt-oss-20b")
        with patch.object(Chat, "WorkerClient", factory):
            models, default = Chat._fetch_models("http://w:8000", "")
        assert "gpt-oss-20b" not in models
        assert default == "qwen3-4b"

    def test_all_models_blocked_yields_empty_list_and_default(self):
        factory = self._client(["deepseek-r1", "nomic-embed-text"], "deepseek-r1")
        with patch.object(Chat, "WorkerClient", factory):
            models, default = Chat._fetch_models("http://w:8000", "")
        assert models == []
        assert default == ""

    def test_allowed_default_preserved(self):
        factory = self._client(["a-model", "b-model"], "b-model")
        with patch.object(Chat, "WorkerClient", factory):
            _, default = Chat._fetch_models("http://w:8000", "")
        assert default == "b-model"

    def test_backend_is_forwarded_to_the_worker(self):
        client = MagicMock()
        client.list_models = MagicMock(return_value=(["m"], "m"))
        with patch.object(Chat, "WorkerClient", MagicMock(return_value=client)):
            Chat._fetch_models("http://w:8000", "s3cret", "ollama")
        client.list_models.assert_called_once_with(backend="ollama")
