# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Runtime pieces for small Macs: empty-synthesis errors and MOOT_MODEL.

FLUX idle unload is imagewright's now, and tested there.
"""

from __future__ import annotations

from gutenberg_kg.serve import entmoot
from gutenberg_kg.serve.synth_status import empty_synthesis_error


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
