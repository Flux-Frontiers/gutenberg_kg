# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Runtime pieces for small Macs: FLUX idle unload, empty-synthesis errors, MOOT_MODEL."""

from __future__ import annotations

import pytest

from gutenberg_kg import image_gen
from gutenberg_kg.serve import entmoot, image_server
from gutenberg_kg.serve.synth_status import empty_synthesis_error


class TestIdleUnload:
    @pytest.fixture
    def loaded(self, monkeypatch):
        monkeypatch.setattr(image_gen, "_cached_model", object())
        monkeypatch.setattr(image_gen, "_cached_model_name", "flux")
        monkeypatch.setattr(image_server, "_IDLE_UNLOAD_S", 300)
        monkeypatch.setattr(image_server, "_last_used", 1000.0)

    def test_unloads_after_the_idle_time(self, loaded):
        assert image_server.maybe_unload(now=1300.0) is True
        assert not image_gen.model_loaded()

    def test_keeps_a_recently_used_model(self, loaded):
        assert image_server.maybe_unload(now=1299.0) is False
        assert image_gen.model_loaded()

    def test_off_by_default(self, loaded, monkeypatch):
        monkeypatch.setattr(image_server, "_IDLE_UNLOAD_S", 0)
        assert image_server.maybe_unload(now=10**9) is False
        assert image_gen.model_loaded()

    def test_never_unloads_during_a_render(self, loaded):
        with image_server._gen_lock:
            assert image_server.maybe_unload(now=10**9) is False
        assert image_gen.model_loaded()

    def test_nothing_to_unload(self, monkeypatch):
        monkeypatch.setattr(image_gen, "_cached_model", None)
        monkeypatch.setattr(image_server, "_IDLE_UNLOAD_S", 300)
        assert image_server.maybe_unload(now=10**9) is False
        assert image_gen.unload_model() is False

    def test_a_render_marks_the_model_used(self, monkeypatch):
        monkeypatch.setattr(image_gen, "generate", lambda **kw: "img")
        monkeypatch.setattr(image_server, "_last_used", 0.0)
        assert image_server._render(prompt="p") == "img"
        assert image_server._last_used > 0.0


class TestEmptySynthesis:
    def test_hits_with_text_and_no_answer_is_an_error(self):
        msg = empty_synthesis_error([{"content": "passage"}], "Qwen3.8-27B-4bit", 12)
        assert msg and "Qwen3.8-27B-4bit" in msg and "make models" in msg

    def test_no_text_to_synthesize_from_is_not_an_error(self):
        assert empty_synthesis_error([{"content": "  "}, {}], "m", 12) is None

    def test_only_the_hits_synthesis_reads_count(self):
        hits = [{"content": ""}, {"content": "late passage"}]
        assert empty_synthesis_error(hits, "m", 1) is None


class TestMootModel:
    def test_omlx_uses_moot_model(self, monkeypatch):
        monkeypatch.setenv("MOOT_MODEL", "Qwen3-8B-MLX-4bit")
        assert entmoot.resolve_model("omlx", None, None) == (
            "Qwen3-8B-MLX-4bit",
            "Qwen3-8B-MLX-4bit",
        )

    def test_empty_moot_model_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setenv("MOOT_MODEL", "")
        assert entmoot.resolve_model("omlx", None, None) == (
            entmoot.DEFAULT_MODEL,
            entmoot.DEFAULT_MODEL,
        )

    def test_an_explicit_model_wins(self, monkeypatch):
        monkeypatch.setenv("MOOT_MODEL", "Qwen3-8B-MLX-4bit")
        assert entmoot.resolve_model("omlx", "X", None) == ("X", "X")
