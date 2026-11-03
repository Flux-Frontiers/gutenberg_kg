"""rotate_omlx_key.py: one key in both files, a backup per run, never printed."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "rotate_omlx_key.py"

# scripts/ is not a package, so load the file straight from its path.
_spec = importlib.util.spec_from_file_location("rotate_omlx_key", _SCRIPT)
assert _spec is not None and _spec.loader is not None
rotate = importlib.util.module_from_spec(_spec)
sys.modules["rotate_omlx_key"] = rotate
_spec.loader.exec_module(rotate)

_OLD_KEY = "sk-old-key"  # pragma: allowlist secret
_NEW_KEY = "sk-new-key"  # pragma: allowlist secret


@pytest.fixture
def files(tmp_path, monkeypatch):
    settings = tmp_path / ".omlx" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"server": {"port": 8080}, "auth": {"api_key": _OLD_KEY}}))
    env = tmp_path / ".env"
    env.write_text(f"VLLM_MODEL=m\nVLLM_API_KEY={_OLD_KEY}\nOTHER=1\n")
    monkeypatch.setattr(rotate, "OMLX_SETTINGS", settings)
    monkeypatch.setattr(rotate, "ENV_FILE", env)
    monkeypatch.setattr(rotate, "omlx_running", lambda: False)
    return settings, env


def _main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["rotate_omlx_key.py", *argv])
    return rotate.main()


def test_writes_one_key_to_both_files(files, monkeypatch, capsys):
    settings, env = files
    assert _main(monkeypatch, "--key", _NEW_KEY) == 0
    data = json.loads(settings.read_text())
    assert data["auth"]["api_key"] == _NEW_KEY
    assert data["server"] == {"port": 8080}
    assert env.read_text() == f"VLLM_MODEL=m\nVLLM_API_KEY={_NEW_KEY}\nOTHER=1\n"
    out = capsys.readouterr().out
    assert _NEW_KEY not in out
    assert "make down && make up" in out


def test_random_key_matches_in_both_files(files, monkeypatch, capsys):
    settings, env = files
    assert _main(monkeypatch) == 0
    key = json.loads(settings.read_text())["auth"]["api_key"]
    assert key.startswith("sk-") and key != _OLD_KEY
    assert f"VLLM_API_KEY={key}\n" in env.read_text()
    assert key not in capsys.readouterr().out


def test_appends_key_when_env_has_none(files, monkeypatch):
    _, env = files
    env.write_text("VLLM_MODEL=m")
    assert _main(monkeypatch, "--key", _NEW_KEY) == 0
    assert env.read_text() == f"VLLM_MODEL=m\nVLLM_API_KEY={_NEW_KEY}\n"


def test_each_run_keeps_its_own_backup(files, monkeypatch):
    settings, _ = files
    assert _main(monkeypatch, "--key", _NEW_KEY) == 0
    assert _main(monkeypatch, "--key", "sk-third") == 0  # pragma: allowlist secret
    backups = sorted(settings.parent.glob("settings.json.bak-*"))
    keys = [json.loads(b.read_text())["auth"]["api_key"] for b in backups]
    assert sorted(keys) == sorted([_OLD_KEY, _NEW_KEY])


def test_refuses_while_omlx_runs(files, monkeypatch):
    settings, env = files
    before = (settings.read_text(), env.read_text())
    monkeypatch.setattr(rotate, "omlx_running", lambda: True)
    assert _main(monkeypatch, "--key", _NEW_KEY) == 1
    assert (settings.read_text(), env.read_text()) == before
    assert _main(monkeypatch, "--key", _NEW_KEY, "--force") == 0
    assert json.loads(settings.read_text())["auth"]["api_key"] == _NEW_KEY


def test_missing_env_file_fails(files, monkeypatch):
    _, env = files
    env.unlink()
    assert _main(monkeypatch, "--key", _NEW_KEY) == 1
