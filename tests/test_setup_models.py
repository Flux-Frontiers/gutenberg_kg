# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""scripts/setup_models.py (`make models`) and the model-default drift check."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


setup_models = _load("setup_models")
check_pins = _load("check_pins")


@pytest.fixture
def table():
    return setup_models.load_tiers()


class TestTierTable:
    def test_default_tier_exists(self, table):
        assert table["default_tier"] in table["tiers"]

    def test_every_tier_names_a_repo_whose_folder_is_its_id(self, table):
        # oMLX serves a model under its folder name, which `hf download
        # --local-dir` takes from the repo's last part.
        for tier in table["tiers"].values():
            assert tier["llm_repo"].rsplit("/", 1)[-1] == tier["llm_id"]

    def test_exactly_one_tier_has_no_ceiling(self, table):
        assert [t for t in table["tiers"].values() if t["max_ram_gb"] is None] == [
            table["tiers"]["xl"]
        ]


class TestPickTier:
    @pytest.mark.parametrize(
        ("ram", "tier"),
        [
            (8, "small"),
            (16, "small"),
            (18, "medium"),
            (24, "medium"),
            (32, "large"),
            (36, "large"),
            (48, "xl"),
            (128, "xl"),
        ],
    )
    def test_by_memory(self, table, ram, tier):
        assert setup_models.pick_tier(table, ram) == tier

    def test_a_mac_reporting_slightly_over_its_size_keeps_its_tier(self, table):
        assert setup_models.pick_tier(table, 24.2) == "medium"

    def test_smaller_tier(self, table):
        assert setup_models.smaller_tier(table, "large") == "medium"
        assert setup_models.smaller_tier(table, "small") is None


class TestEnvKeys:
    def test_replaces_and_appends(self):
        text = "A=1\nVLLM_MODEL=old\n# VLLM_MODEL=comment\n"
        out = setup_models.set_env_keys(text, {"VLLM_MODEL": "new", "MOOT_MODEL": "m"})
        assert out == "A=1\nVLLM_MODEL=new\n# VLLM_MODEL=comment\nMOOT_MODEL=m\n"

    def test_a_value_with_backslashes_is_written_literally(self):
        assert setup_models.set_env_keys("K=1\n", {"K": r"a\1b"}) == "K=a\\1b\n"


class TestServedId:
    def test_exact(self):
        assert (
            setup_models.resolve_served_id(["a", "Qwen3-8B-MLX-4bit"], "Qwen3-8B-MLX-4bit")
            == "Qwen3-8B-MLX-4bit"
        )

    def test_org_prefixed(self):
        served = ["Jundot--Qwen3.6-35B-A3B-oQ4e-mtp"]
        assert setup_models.resolve_served_id(served, "Qwen3.6-35B-A3B-oQ4e-mtp") == served[0]

    def test_a_longer_name_is_not_a_match(self):
        assert setup_models.resolve_served_id(["XQwen3-8B-MLX-4bit"], "Qwen3-8B-MLX-4bit") is None


def test_plist_idle_unload():
    text = "<key>IMAGE_IDLE_UNLOAD_S</key>\n\t\t<string>300</string>"
    assert setup_models.plist_idle_unload(text) == "300"
    assert setup_models.plist_idle_unload("<key>X</key><string>300</string>") is None


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """A 24 GB Apple Silicon Mac with its own docker/.env and oMLX settings."""
    env = tmp_path / ".env"
    env.write_text("VLLM_MODEL=old\n")
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"server": {"port": 1}}))
    monkeypatch.setattr(setup_models, "ENV_FILE", env)
    monkeypatch.setattr(setup_models, "OMLX_SETTINGS", settings)
    monkeypatch.setattr(setup_models, "OMLX_HOME", tmp_path)
    monkeypatch.setattr(setup_models, "OMLX_MODELS", tmp_path / "models")
    monkeypatch.setattr(setup_models, "IMAGE_AGENT_PLIST", tmp_path / "none.plist")
    monkeypatch.setattr(setup_models, "find_hf", lambda: "/bin/false")
    monkeypatch.setattr(setup_models, "ram_gb", lambda: 24.0)
    monkeypatch.setattr(setup_models, "docker_vm_gb", lambda: None)
    monkeypatch.setattr(setup_models.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(setup_models.platform, "machine", lambda: "arm64")
    return env


class FakeOMLX:
    """oMLX that lists the 8B and answers the smoke test with ``error``."""

    error: str | None = None
    base = "http://fake"
    guard_tier = "balanced"

    def reachable(self):
        return True

    def reload(self):
        return True

    def models(self):
        return ["Qwen3-8B-MLX-4bit"]

    def smoke_test(self, model):
        return self.error


def _no_download(monkeypatch):
    class Done:
        returncode = 0

    monkeypatch.setattr(setup_models.subprocess, "run", lambda *a, **k: Done())


def test_dry_run_changes_nothing(sandbox, capsys):
    assert setup_models.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Tier: medium" in out and "VLLM_MODEL=Qwen3-8B-MLX-4bit" in out
    assert sandbox.read_text() == "VLLM_MODEL=old\n"


def test_a_working_model_is_written(sandbox, monkeypatch):
    _no_download(monkeypatch)
    monkeypatch.setattr(setup_models, "OMLX", FakeOMLX)
    assert setup_models.main([]) == 0
    text = sandbox.read_text()
    assert "VLLM_MODEL=Qwen3-8B-MLX-4bit" in text
    assert "MOOT_MODEL=Qwen3-8B-MLX-4bit" in text and "IMAGE_IDLE_UNLOAD_S=300" in text
    backups = list(sandbox.parent.glob(".env.bak-*"))
    assert backups
    # docker/.env holds API keys: owner-only, and so is its backup.
    for path in [sandbox, *backups]:
        assert path.stat().st_mode & 0o777 == 0o600, path


class ServingWithPrefix(FakeOMLX):
    """oMLX that already serves the 8B under an org-prefixed id."""

    def models(self):
        return ["Qwen--Qwen3-8B-MLX-4bit"]


def test_a_served_model_is_not_downloaded(sandbox, monkeypatch):
    calls = []
    monkeypatch.setattr(setup_models.subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(setup_models, "OMLX", ServingWithPrefix)
    assert setup_models.main([]) == 0
    assert calls == []
    assert "VLLM_MODEL=Qwen--Qwen3-8B-MLX-4bit" in sandbox.read_text()


def test_dry_run_reports_the_served_id(sandbox, monkeypatch, capsys):
    monkeypatch.setattr(setup_models, "OMLX", ServingWithPrefix)
    assert setup_models.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "already served by oMLX" in out and "VLLM_MODEL=Qwen--Qwen3-8B-MLX-4bit" in out
    assert sandbox.read_text() == "VLLM_MODEL=old\n"


def test_a_refused_model_leaves_env_alone(sandbox, monkeypatch, capsys):
    _no_download(monkeypatch)

    class Refusing(FakeOMLX):
        error = "Model does not fit under the dynamic memory ceiling"

    monkeypatch.setattr(setup_models, "OMLX", Refusing)
    assert setup_models.main([]) == 1
    err = capsys.readouterr().err
    assert "dynamic memory ceiling" in err and "TIER=small" in err
    assert sandbox.read_text() == "VLLM_MODEL=old\n"


class TestModelDefaultDrift:
    def test_the_repo_agrees(self):
        assert check_pins.model_default_problems() == []

    def test_a_drifted_compose_default_is_reported(self, monkeypatch, tmp_path):
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("      VLLM_MODEL: ${VLLM_MODEL:-Some-Other-Model}\n")
        monkeypatch.setattr(check_pins, "COMPOSE", compose)
        problems = check_pins.model_default_problems()
        assert len(problems) == 1 and "Some-Other-Model" in problems[0]

    def test_a_tier_missing_from_the_docs_is_reported(self, monkeypatch, tmp_path):
        doc = tmp_path / "INSTALLATION.md"
        doc.write_text("Qwen3-4B-Instruct-2507-MLX-8bit only\n")
        monkeypatch.setattr(check_pins, "INSTALL_DOC", doc)
        assert any("medium" in p for p in check_pins.model_default_problems())
