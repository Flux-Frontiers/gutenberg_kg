"""Tests for the ``gutenkg query`` command."""

from subprocess import CompletedProcess
from unittest import mock

import click
import pytest
from click.testing import CliRunner

from gutenberg_kg.cli import cmd_query
from gutenberg_kg.cli.main import cli


def test_query_help_lists_key_options():
    result = CliRunner().invoke(cli, ["query", "--help"])
    assert result.exit_code == 0
    for option in ("--corpus", "--k", "--registry", "--json"):
        assert option in result.output


def test_query_delegates_to_local_kgrag():
    with mock.patch.object(
        cmd_query.subprocess, "run", return_value=CompletedProcess([], 0)
    ) as run:
        result = CliRunner().invoke(
            cli,
            [
                "query",
                "justice",
                "--corpus",
                "gutenberg-philosophy",
                "--k",
                "3",
                "--registry",
                "/tmp/registry.sqlite",
                "--json",
            ],
        )

    assert result.exit_code == 0
    run.assert_called_once_with(
        [
            "kgrag",
            "corpus",
            "query",
            "gutenberg-philosophy",
            "justice",
            "-k",
            "3",
            "--registry",
            "/tmp/registry.sqlite",
            "--json",
        ],
        check=False,
    )


def test_query_preserves_kgrag_failure_status():
    with mock.patch.object(cmd_query.subprocess, "run", return_value=CompletedProcess([], 2)):
        result = CliRunner().invoke(cli, ["query", "justice"])

    assert result.exit_code == 2


def test_query_reports_missing_kgrag():
    with mock.patch.object(cmd_query.subprocess, "run", side_effect=FileNotFoundError):
        with pytest.raises(click.ClickException, match="requires KGRAG"):
            cmd_query._run_query("justice", "gutenberg-all", 8, None, False)
