"""Tests for the ``gutenkg quilt`` command's option handling."""

import pytest
from click.testing import CliRunner

pytest.importorskip("pyvista")
pytest.importorskip("quiltwright")

from gutenberg_kg.cli.main import cli  # noqa: E402


@pytest.mark.parametrize("extra", [["--orbit", "5"], ["--cast"]])
def test_still_refuses_quilt_only_options(tmp_path, extra):
    result = CliRunner().invoke(
        cli, ["quilt", "--corpus", str(tmp_path), "--book", "x", "--still", *extra]
    )
    assert result.exit_code != 0
    assert "--still renders one PNG" in result.output
