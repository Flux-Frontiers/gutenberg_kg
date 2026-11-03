"""bootstrap.py: what it reports, and that a dry run changes nothing."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bootstrap.py"

# scripts/ is not a package, so load the file straight from its path.
_spec = importlib.util.spec_from_file_location("bootstrap", _SCRIPT)
assert _spec is not None and _spec.loader is not None
bootstrap = importlib.util.module_from_spec(_spec)
sys.modules["bootstrap"] = bootstrap
_spec.loader.exec_module(bootstrap)


def _run(**kw):
    args = {"dry_run": True, "assume_yes": False, "dev": False, "cli_only": True, "extras": "mcp"}
    args.update(kw)
    return bootstrap.Bootstrap(**args)


@pytest.mark.parametrize(
    ("version", "ok"),
    [((3, 11, 9), False), ((3, 12, 0), True), ((3, 13, 5), True), ((3, 14, 0), False)],
)
def test_python_range_matches_pyproject(version, ok):
    assert bootstrap.python_ok(version) is ok


def test_python_range_tracks_requires_python():
    text = (_SCRIPT.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.12,<3.14"' in text


@pytest.mark.parametrize(
    ("text", "parsed"),
    [("Poetry (version 2.3.2)", (2, 3, 2)), ("Poetry (version 1.8.3)", (1, 8, 3)), ("nope", None)],
)
def test_parse_version(text, parsed):
    assert bootstrap.parse_version(text) == parsed


def test_dry_run_runs_no_command(monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError(f"dry run executed {a}")

    monkeypatch.setattr(bootstrap.subprocess, "run", boom)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    b = _run()
    # As if Python and Poetry were found; the install step must still only print.
    b.python_ready = b.poetry_ready = True
    b.install_deps()
    assert "would run" in capsys.readouterr().out
    assert b.blocked == []


def test_dry_run_with_no_poetry_offers_the_install_without_asking(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)
    monkeypatch.setattr(bootstrap.sys.stdin, "isatty", lambda: False)
    b = _run()
    b.check_poetry()
    out = capsys.readouterr().out
    assert "would run" in out and bootstrap.POETRY_INSTALLER_URL in out
    assert b.blocked == []


def test_real_run_without_consent_blocks_instead_of_installing(monkeypatch):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)
    monkeypatch.setattr(bootstrap.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(
        bootstrap.subprocess, "run", lambda *a, **k: pytest.fail("installed without consent")
    )
    b = _run(dry_run=False)
    b.check_poetry()
    assert b.blocked == ["Poetry"]


def test_old_poetry_blocks(monkeypatch):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: "/bin/poetry")
    done = subprocess.CompletedProcess([], 0, stdout="Poetry (version 1.8.3)")
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: done)
    b = _run()
    b.check_poetry()
    assert b.blocked and not b.poetry_ready


def test_existing_env_file_is_not_overwritten(monkeypatch, tmp_path):
    env, example = tmp_path / ".env", tmp_path / ".env.example"
    env.write_text("OPENAI_API_KEY=mine\n")
    example.write_text("OPENAI_API_KEY=\n")
    monkeypatch.setattr(bootstrap, "ENV_FILE", env)
    monkeypatch.setattr(bootstrap, "ENV_EXAMPLE", example)
    _run(dry_run=False).make_env_file()
    assert env.read_text() == "OPENAI_API_KEY=mine\n"


def test_missing_env_file_is_seeded_only_outside_dry_run(monkeypatch, tmp_path):
    env, example = tmp_path / ".env", tmp_path / ".env.example"
    example.write_text("X=1\n")
    monkeypatch.setattr(bootstrap, "ENV_FILE", env)
    monkeypatch.setattr(bootstrap, "ENV_EXAMPLE", example)
    _run(dry_run=True).make_env_file()
    assert not env.exists()
    _run(dry_run=False).make_env_file()
    assert env.read_text() == "X=1\n"


def test_openai_key_in_env_file_is_reported_without_leaking(monkeypatch, tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("# comment\nOPENAI_API_KEY='sk-secret-value'\n")  # pragma: allowlist secret
    monkeypatch.setattr(bootstrap, "ENV_FILE", env)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("IMAGE_API_KEY", raising=False)
    monkeypatch.setattr(bootstrap, "port_open", lambda port, **k: False)
    _run().probe_backends()
    out = capsys.readouterr().out
    assert "OpenAI key set" in out
    assert "sk-secret-value" not in out


def test_no_key_and_no_backend_says_querying_still_works(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(bootstrap, "ENV_FILE", tmp_path / "absent")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("IMAGE_API_KEY", raising=False)
    monkeypatch.setattr(bootstrap, "port_open", lambda port, **k: False)
    _run().probe_backends()
    assert "querying the corpus works without one" in capsys.readouterr().out


def _no_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap, "ENV_FILE", tmp_path / "absent")
    for var in ("OPENAI_API_KEY", "IMAGE_API_KEY", "SYNTH_API_KEY", "VLLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(bootstrap, "port_open", lambda port, **k: False)


def test_image_key_alone_does_not_claim_synthesis(monkeypatch, tmp_path, capsys):
    _no_keys(monkeypatch, tmp_path)
    monkeypatch.setenv("IMAGE_API_KEY", "x")
    _run().probe_backends()
    out = capsys.readouterr().out
    assert "images only" in out
    assert "get synthesis" not in out
    assert "no synthesis backend" in out


def test_placeholder_omlx_key_is_flagged(monkeypatch, tmp_path, capsys):
    _no_keys(monkeypatch, tmp_path)
    env = tmp_path / ".env"
    env.write_text("VLLM_API_KEY=sk-placeholder\n")  # pragma: allowlist secret
    example = tmp_path / ".env.example"
    example.write_text("VLLM_API_KEY=sk-placeholder\n")  # pragma: allowlist secret
    monkeypatch.setattr(bootstrap, "ENV_FILE", env)
    monkeypatch.setattr(bootstrap, "ENV_EXAMPLE", example)
    _run().probe_backends()
    assert "still the example placeholder" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("code", "up", "words"),
    [(200, True, "answering"), (401, True, "wants an API key"), (404, False, "does not answer")],
)
def test_llm_probe_reads_the_http_answer(monkeypatch, capsys, code, up, words):
    monkeypatch.setattr(bootstrap, "port_open", lambda port, **k: True)
    monkeypatch.setattr(bootstrap, "http_status", lambda url, **k: code)
    assert _run()._probe_llm("oMLX", 8080, "/v1/models", "hint") is up
    assert words in capsys.readouterr().out


def test_wedged_docker_warns_instead_of_crashing(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: f"/bin/{name}")

    def hang(cmd, **k):
        raise subprocess.TimeoutExpired(cmd, 20)

    monkeypatch.setattr(bootstrap.subprocess, "run", hang)
    _run().check_containers()
    assert "no answer in 20 s" in capsys.readouterr().out


def test_installer_download_failure_blocks_instead_of_crashing(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)

    def offline(*a, **k):
        raise bootstrap.urllib.error.URLError("CERTIFICATE_VERIFY_FAILED")

    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", offline)
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Darwin")
    b = _run(dry_run=False, assume_yes=True)
    b.check_poetry()
    out = capsys.readouterr().out
    assert b.blocked == ["Poetry"]
    assert "Install Certificates.command" in out


def test_missing_binary_fails_cleanly(monkeypatch, capsys):
    def missing(*a, **k):
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(bootstrap.subprocess, "run", missing)
    assert _run(dry_run=False).act(["make", "setup"]) is False
    assert "[fail] make" in capsys.readouterr().out


def test_unparseable_poetry_version_says_so(monkeypatch):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: "/bin/poetry")
    done = subprocess.CompletedProcess([], 0, stdout="garbage")
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: done)
    b = _run()
    b.check_poetry()
    assert b.blocked == ["Poetry at /bin/poetry did not report its version"]


def test_no_python_skips_install_and_models(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: pytest.fail("ran"))
    monkeypatch.setattr(bootstrap, "VENV", Path("/nonexistent/.venv"))
    b = _run(dry_run=False)
    b.poetry_ready = True
    b.install_deps()
    b.fetch_models()
    assert capsys.readouterr().out.count("no supported Python") == 2
    assert b.blocked == []


def test_foreign_virtualenv_blocks_install(monkeypatch, tmp_path):
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "other"))
    b = _run()
    b.python_ready = b.poetry_ready = True
    b.install_deps()
    assert b.blocked and "another virtualenv" in b.blocked[0]


def test_repo_venv_active_is_fine(monkeypatch, capsys):
    monkeypatch.setenv("VIRTUAL_ENV", str(bootstrap.VENV))
    b = _run()
    b.python_ready = b.poetry_ready = True
    b.install_deps()
    assert b.blocked == []


def test_dev_keeps_chosen_extras():
    assert bootstrap.dev_extras("mcp viz") == "mcp viz image pov"
    assert bootstrap.dev_extras("pov mcp") == "pov mcp image"


@pytest.mark.parametrize(("macos", "offered"), [("26.1", True), ("15.6", False)])
def test_apple_container_offered_only_on_macos_26(monkeypatch, capsys, macos, offered):
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(bootstrap.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(bootstrap.platform, "mac_ver", lambda: (macos, ("", "", ""), ""))
    _run().check_containers()
    assert ("make setup RUNTIME=apple" in capsys.readouterr().out) is offered


@pytest.mark.parametrize(
    ("line", "value"),
    [
        ("export KEY=abc", "abc"),
        ("KEY=  # just a note", ""),
        ("KEY=abc # note", "abc"),
        ("KEY='a # b'", "a # b"),
        ('KEY="quoted"', "quoted"),
        ("KEY=", ""),
    ],
)
def test_read_dotenv(tmp_path, line, value):
    env = tmp_path / ".env"
    env.write_text(f"# header\n{line}\n")
    assert bootstrap.read_dotenv(env) == {"KEY": value}


def test_header_carries_provenance_and_machine_info():
    from datetime import UTC, datetime

    started = datetime(2026, 11, 2, 19, 4, 12, tzinfo=UTC)
    lines = bootstrap.header_lines(dry_run=True, started=started)
    text = "\n".join(lines)
    assert "DRY RUN" in text
    assert "2026-11-02T19:04:12Z" in text
    assert f"v{bootstrap.project_version()}" in text
    for key in ("git", "host", "os", "cpu", "memory", "disk", "python", "command"):
        assert any(line.strip().startswith(key) for line in lines), key
    # Color is off outside a terminal, and the banner fits its frame.
    assert "\033[" not in text
    assert len(lines[1]) == len(lines[0]) == bootstrap.HEADER_WIDTH


def test_project_version_matches_pyproject():
    text = (_SCRIPT.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{bootstrap.project_version()}"' in text


def test_paint_is_plain_without_color(monkeypatch):
    monkeypatch.setattr(bootstrap, "_USE_COLOR", False)
    assert bootstrap.paint("ok", "32") == "ok"
    monkeypatch.setattr(bootstrap, "_USE_COLOR", True)
    assert bootstrap.paint("ok", "32") == "\033[32mok\033[0m"
