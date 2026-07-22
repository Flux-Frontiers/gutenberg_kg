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
    for cmd in ("authors", "download", "ia", "ingest", "list-genres", "query", "rebuild-indices"):
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


def test_chunk_diaries_help():
    result = CliRunner().invoke(cli, ["chunk-diaries", "--help"])
    assert result.exit_code == 0
    assert "--diary" in result.output
    assert "--force" in result.output


def test_build_diaries_help():
    result = CliRunner().invoke(cli, ["build-diaries", "--help"])
    assert result.exit_code == 0
    assert "--diary" in result.output
    assert "--workers" in result.output


def test_build_corpus_help():
    result = CliRunner().invoke(cli, ["build-corpus", "--help"])
    assert result.exit_code == 0
    assert "--genre" in result.output
    assert "--diaries-only" in result.output


def test_audit_help():
    result = CliRunner().invoke(cli, ["audit", "--help"])
    assert result.exit_code == 0
    assert "--genre" in result.output
    assert "--json" in result.output


def test_reregister_help():
    result = CliRunner().invoke(cli, ["re-register", "--help"])
    assert result.exit_code == 0
    assert "--genre" in result.output


def test_viz3d_help():
    result = CliRunner().invoke(cli, ["viz3d", "--help"])
    assert result.exit_code == 0


def test_viz_timeline_help():
    result = CliRunner().invoke(cli, ["viz-timeline", "--help"])
    assert result.exit_code == 0


def test_imagine_help():
    result = CliRunner().invoke(cli, ["imagine", "--help"])
    assert result.exit_code == 0


def test_query_help():
    result = CliRunner().invoke(cli, ["query", "--help"])
    assert result.exit_code == 0
    for option in ("--corpus", "--k", "--registry", "--json"):
        assert option in result.output


@pytest.mark.parametrize(
    "command",
    [
        "audit",
        "authors",
        "build-corpus",
        "build-diaries",
        "chunk-diaries",
        "download",
        "genres",
        "ia",
        "ingest",
        "query",
        "rebuild-indices",
        "re-register",
        "snapshot",
        "status",
    ],
)
def test_command_is_registered(command):
    """Every expected subcommand resolves and shows help without error."""
    result = CliRunner().invoke(cli, [command, "--help"])
    assert result.exit_code == 0
