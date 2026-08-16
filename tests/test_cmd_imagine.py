"""Tests for cli/cmd_imagine.py — the `gutenkg imagine` command.

The image endpoint, VLM, and corpus retrieval are all mocked, so these tests
run without any network access, GPU, doc-kg, or openai package installed.
"""

from unittest import mock

import click
import pytest
from click.testing import CliRunner

from gutenberg_kg.cli import cmd_imagine
from gutenberg_kg.cli.cmd_imagine import _resolve_prompt
from gutenberg_kg.cli.main import cli

# ---------------------------------------------------------------------------
# Help / registration
# ---------------------------------------------------------------------------


def test_imagine_registered():
    result = CliRunner().invoke(cli, ["imagine", "--help"])
    assert result.exit_code == 0


def test_imagine_help_lists_key_options():
    result = CliRunner().invoke(cli, ["imagine", "--help"])
    for opt in ("--query", "--book", "--size", "--seed", "--steps", "--corpus-only", "--no-vlm"):
        assert opt in result.output, f"expected '{opt}' in imagine help"


# ---------------------------------------------------------------------------
# _resolve_prompt — the prompt-building seam (no I/O)
# ---------------------------------------------------------------------------


def test_resolve_prompt_returns_bare_prompt():
    assert _resolve_prompt("a castle at dusk", None, None, corpus_only=False) == "a castle at dusk"


def test_resolve_prompt_requires_prompt_or_query():
    with pytest.raises(click.UsageError):
        _resolve_prompt(None, None, None, corpus_only=False)


def test_resolve_prompt_corpus_only_prints_and_exits():
    with mock.patch.object(cmd_imagine, "_query_corpus", return_value="the great fire raged"):
        with pytest.raises(SystemExit) as exc:
            _resolve_prompt(None, "great fire", "pepys", corpus_only=True)
    assert exc.value.code == 0


def test_resolve_prompt_uses_vlm_when_enabled():
    with (
        mock.patch.object(cmd_imagine, "_query_corpus", return_value="raw corpus text"),
        mock.patch.object(cmd_imagine, "_vlm_rewrite", return_value="visual scene") as vlm,
    ):
        out = _resolve_prompt(None, "great fire", None, corpus_only=False, use_vlm=True)
    assert out == "visual scene"
    vlm.assert_called_once_with("raw corpus text")


def test_resolve_prompt_vlm_appends_style_notes():
    with (
        mock.patch.object(cmd_imagine, "_query_corpus", return_value="corpus"),
        mock.patch.object(cmd_imagine, "_vlm_rewrite", side_effect=lambda t: t) as vlm,
    ):
        _resolve_prompt("oil painting", "fire", None, corpus_only=False, use_vlm=True)
    passed = vlm.call_args.args[0]
    assert "corpus" in passed and "oil painting" in passed


def test_resolve_prompt_no_vlm_with_prompt_prepends_context():
    with mock.patch.object(cmd_imagine, "_query_corpus", return_value="historical prose"):
        out = _resolve_prompt("dramatic", "fire", None, corpus_only=False, use_vlm=False)
    assert out.startswith("dramatic")
    assert "historical prose" in out


def test_resolve_prompt_no_vlm_no_prompt_returns_corpus():
    with mock.patch.object(cmd_imagine, "_query_corpus", return_value="just the corpus"):
        out = _resolve_prompt(None, "fire", None, corpus_only=False, use_vlm=False)
    assert out == "just the corpus"


# ---------------------------------------------------------------------------
# _vlm_rewrite — falls back to raw text on VLM error
# ---------------------------------------------------------------------------


def test_vlm_rewrite_success_returns_result():
    with mock.patch("gutenberg_kg.image_gen.vlm_rewrite", return_value=("rewritten scene", None)):
        assert cmd_imagine._vlm_rewrite("prose") == "rewritten scene"


def test_vlm_rewrite_error_falls_back_to_raw_text():
    with mock.patch("gutenberg_kg.image_gen.vlm_rewrite", return_value=("prose", "endpoint down")):
        assert cmd_imagine._vlm_rewrite("prose") == "prose"


# ---------------------------------------------------------------------------
# End-to-end command flow (endpoint + generation mocked)
# ---------------------------------------------------------------------------


def _fake_image():
    """A stand-in PIL image whose .save() just records the path."""
    return mock.Mock(name="PILImage")


def test_no_endpoint_and_nothing_running_is_a_usage_error(monkeypatch):
    # Discovery is patched rather than left to the machine: without this the
    # test passes or fails depending on whether a dev happens to have an image
    # server up on 8090, which is exactly the coupling `imagine` now exploits.
    monkeypatch.delenv("GUTENKG_IMAGE_ENDPOINT", raising=False)
    with mock.patch("gutenberg_kg.image_gen.discover_image_endpoint", return_value=None):
        result = CliRunner().invoke(cli, ["imagine", "a ship"])
    assert result.exit_code == 2  # click.UsageError
    assert "endpoint" in result.output.lower()
    assert "make image-server" in result.output


def test_a_running_server_is_discovered_when_nothing_is_configured(tmp_path, monkeypatch):
    # The bug this fixes: `make up` binds a backend without exporting anything,
    # so the CLI refused to work against a server that was right there.
    monkeypatch.delenv("GUTENKG_IMAGE_ENDPOINT", raising=False)
    out = tmp_path / "ship.png"
    with (
        mock.patch(
            "gutenberg_kg.image_gen.discover_image_endpoint",
            return_value="http://localhost:8090",
        ),
        mock.patch("gutenberg_kg.image_gen.generate_via_server", return_value=_fake_image()) as gen,
    ):
        result = CliRunner().invoke(
            cli, ["imagine", "a ship", "-o", str(out), "--no-open", "--no-vlm"]
        )
    assert result.exit_code == 0, result.output
    assert "discovered" in result.output
    assert gen.call_args.kwargs["server_url"] == "http://localhost:8090"


def test_happy_path_saves_image(tmp_path, monkeypatch):
    monkeypatch.delenv("GUTENKG_IMAGE_ENDPOINT", raising=False)
    out = tmp_path / "ship.png"
    pil = _fake_image()
    with mock.patch("gutenberg_kg.image_gen.generate_via_server", return_value=pil) as gen:
        result = CliRunner().invoke(
            cli,
            [
                "imagine",
                "a ship at sea",
                "--endpoint",
                "http://localhost:9000",
                "--no-open",
                "-o",
                str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    gen.assert_called_once()
    assert gen.call_args.args[0] == "a ship at sea"
    pil.save.assert_called_once_with(str(out))
    assert str(out) in result.output


def test_generation_params_passed_through(tmp_path, monkeypatch):
    monkeypatch.delenv("GUTENKG_IMAGE_ENDPOINT", raising=False)
    out = tmp_path / "x.png"
    with mock.patch(
        "gutenberg_kg.image_gen.generate_via_server", return_value=_fake_image()
    ) as gen:
        result = CliRunner().invoke(
            cli,
            [
                "imagine",
                "a ship",
                "--endpoint",
                "http://localhost:9000",
                "--size",
                "768x512",
                "--seed",
                "42",
                "--steps",
                "25",
                "--no-open",
                "-o",
                str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    kwargs = gen.call_args.kwargs
    assert kwargs["server_url"] == "http://localhost:9000"
    assert kwargs["size"] == "768x512"
    assert kwargs["seed"] == 42
    assert kwargs["steps"] == 25


def test_endpoint_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GUTENKG_IMAGE_ENDPOINT", "http://env-host:1234")
    out = tmp_path / "x.png"
    with mock.patch(
        "gutenberg_kg.image_gen.generate_via_server", return_value=_fake_image()
    ) as gen:
        result = CliRunner().invoke(cli, ["imagine", "a ship", "--no-open", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert gen.call_args.kwargs["server_url"] == "http://env-host:1234"


def test_endpoint_request_failure_is_click_exception(tmp_path, monkeypatch):
    monkeypatch.delenv("GUTENKG_IMAGE_ENDPOINT", raising=False)
    with mock.patch(
        "gutenberg_kg.image_gen.generate_via_server",
        side_effect=RuntimeError("connection refused"),
    ):
        result = CliRunner().invoke(
            cli,
            ["imagine", "a ship", "--endpoint", "http://localhost:9000", "--no-open"],
        )
    assert result.exit_code == 1  # click.ClickException
    assert "connection refused" in result.output


def test_open_invokes_subprocess(tmp_path, monkeypatch):
    monkeypatch.delenv("GUTENKG_IMAGE_ENDPOINT", raising=False)
    out = tmp_path / "x.png"
    with (
        mock.patch("gutenberg_kg.image_gen.generate_via_server", return_value=_fake_image()),
        mock.patch("subprocess.Popen") as popen,
    ):
        result = CliRunner().invoke(
            cli,
            ["imagine", "a ship", "--endpoint", "http://x", "--open", "-o", str(out)],
        )
    assert result.exit_code == 0, result.output
    popen.assert_called_once_with(["open", str(out)])


def test_corpus_only_prints_and_skips_generation(monkeypatch):
    monkeypatch.delenv("GUTENKG_IMAGE_ENDPOINT", raising=False)
    with (
        mock.patch.object(cmd_imagine, "_query_corpus", return_value="the plague spread quietly"),
        mock.patch("gutenberg_kg.image_gen.generate_via_server") as gen,
    ):
        result = CliRunner().invoke(
            cli,
            [
                "imagine",
                "--query",
                "plague",
                "--endpoint",
                "http://x",
                "--corpus-only",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "the plague spread quietly" in result.output
    gen.assert_not_called()
