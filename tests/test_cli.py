"""CLI smoke tests — command registration and help output.

Requires kg_rag (not available in CI) — skipped automatically when absent.
"""

import pytest

pytest.importorskip("kg_rag", reason="kg_rag not installed — integration test skipped")

from click.testing import CliRunner

from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES


def test_help_exits_zero():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0


def test_help_shows_top_level_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("authors", "download", "ia", "ingest", "list-genres", "rebuild-indices"):
        assert cmd in result.output, f"expected '{cmd}' in help output"


def test_version_exits_zero():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0


def test_version_output_contains_version_string():
    result = CliRunner().invoke(cli, ["--version"])
    import re

    assert "gutenberg-kg" in result.output or re.search(r"\d+\.\d+", result.output)


def test_authors_help():
    result = CliRunner().invoke(cli, ["authors", "--help"])
    assert result.exit_code == 0
    assert "--refresh" in result.output
    assert "--dry-run" in result.output


def test_download_help():
    result = CliRunner().invoke(cli, ["download", "--help"])
    assert result.exit_code == 0


def test_download_shows_subcommands():
    result = CliRunner().invoke(cli, ["download", "--help"])
    for sub in ("book", "catalog", "search", "fetch-genre", "survey"):
        assert sub in result.output, f"expected download subcommand '{sub}'"


def test_download_book_help():
    result = CliRunner().invoke(cli, ["download", "book", "--help"])
    assert result.exit_code == 0
    assert "--genre" in result.output
    assert "--force" in result.output
    assert "--dry-run" in result.output


def test_ia_help():
    result = CliRunner().invoke(cli, ["ia", "--help"])
    assert result.exit_code == 0


def test_ia_shows_subcommands():
    result = CliRunner().invoke(cli, ["ia", "--help"])
    for sub in ("search", "download", "catalog", "survey"):
        assert sub in result.output, f"expected ia subcommand '{sub}'"


def test_ia_download_help():
    result = CliRunner().invoke(cli, ["ia", "download", "--help"])
    assert result.exit_code == 0
    assert "--genre" in result.output
    assert "--force" in result.output
    assert "--dry-run" in result.output


def test_ingest_help():
    result = CliRunner().invoke(cli, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "--genre" in result.output
    assert "--dry-run" in result.output


def test_list_genres_exits_zero():
    result = CliRunner().invoke(cli, ["list-genres"])
    assert result.exit_code == 0


def test_list_genres_shows_all_genres():
    result = CliRunner().invoke(cli, ["list-genres"])
    for genre in ALL_GENRES:
        assert genre in result.output, f"expected genre '{genre}' in list-genres output"


def test_rebuild_indices_help():
    result = CliRunner().invoke(cli, ["rebuild-indices", "--help"])
    assert result.exit_code == 0
    assert "--genre" in result.output
