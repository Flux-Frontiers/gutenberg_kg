"""Unit tests for scripts/check_pins.py.

The script is a build gate, so what matters is that it *fails* on each kind of
drift — a checker that cannot go red is worse than none, because it reads as a
guarantee. Each test below points the module's file constants at a fixture tree
written to tmp_path, so nothing depends on the repo's current pin values.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_pins.py"

# scripts/ is not a package and the file is not importable by name, so load it
# straight from its path.
_spec = importlib.util.spec_from_file_location("check_pins", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check_pins = importlib.util.module_from_spec(_spec)
sys.modules["check_pins"] = check_pins
_spec.loader.exec_module(check_pins)


_PYPROJECT = """\
[project]
name = "gutenberg-kg"
dependencies = [
    "kgmodule-utils[synthesis,sqlite-vec]>={kgmodule}",
    "doc-kg (>={dockg})",
    "diary-kg (>={diarykg})",
]

[project.optional-dependencies]
kgdeps = ["kg-rag>={kgrag}"]
viz3d = ["kgmodule-utils[viz3d]>={kgmodule_viz3d}"]
"""

_LOCK = """\
[[package]]
name = "kg-rag"
version = "{kgrag}"

[[package]]
name = "kgmodule-utils"
version = "{kgmodule}"

[[package]]
name = "doc-kg"
version = "{dockg}"

[[package]]
name = "diary-kg"
version = "{diarykg}"
"""

_DOCKERFILE = """\
FROM python:3.12-slim
ARG KG_RAG_VERSION={kgrag}
ARG KGMODULE_UTILS_VERSION={kgmodule}
ARG DOC_KG_VERSION={dockg}
ARG DIARY_KG_VERSION={diarykg}
"""

_RUNPOD = """\
# comment line that must be ignored
runpod>=1.7.0
kg-rag>={kgrag}
doc-kg>={dockg}
diary-kg>={diarykg}
kgmodule-utils[synthesis,sqlite-vec]>={kgmodule}
"""

_COMPOSE_CLEAN = """\
services:
  worker:
    build:
      context: ..
"""

_COMPOSE_WITH_ARG = """\
services:
  worker:
    build:
      context: ..
      args:
        KGMODULE_UTILS_VERSION: 0.9.0
"""

_GOOD = {"kgrag": "0.11.0", "kgmodule": "0.11.0", "dockg": "0.21.1", "diarykg": "0.96.0"}


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Write a consistent fixture tree and point the module at it.

    :returns: a callable taking per-file version overrides and compose content.
    """

    def _build(*, pyproject=None, lock=None, dockerfile=None, runpod=None, compose=None):
        def _vals(overrides):
            merged = dict(_GOOD)
            merged.update(overrides or {})
            merged.setdefault("kgmodule_viz3d", merged["kgmodule"])
            return merged

        paths = {
            "PYPROJECT": ("pyproject.toml", _PYPROJECT.format(**_vals(pyproject))),
            "LOCK": ("poetry.lock", _LOCK.format(**_vals(lock))),
            "DOCKERFILE": ("Dockerfile", _DOCKERFILE.format(**_vals(dockerfile))),
            "RUNPOD_REQS": ("requirements.txt", _RUNPOD.format(**_vals(runpod))),
            "COMPOSE": ("docker-compose.yml", compose or _COMPOSE_CLEAN),
        }
        for attr, (name, content) in paths.items():
            path = tmp_path / name
            path.write_text(content)
            monkeypatch.setattr(check_pins, attr, path)

    return _build


class TestVersionKey:
    def test_orders_numerically_not_lexically(self):
        # The reason a plain string compare will not do: "0.9.0" > "0.11.0".
        assert check_pins._version_key("0.11.0") > check_pins._version_key("0.9.0")

    def test_equal_versions_compare_equal(self):
        assert check_pins._version_key("1.2.3") == check_pins._version_key("1.2.3")

    def test_differing_component_counts(self):
        assert check_pins._version_key("1.2") < check_pins._version_key("1.2.1")

    def test_non_numeric_component_does_not_raise(self):
        assert check_pins._version_key("1.0.0rc1") == (1, 0, 0)
        assert check_pins._version_key("1.0.dev") == (1, 0, 0)


class TestParsing:
    def test_reads_both_plain_and_parenthesised_floors(self, tree):
        tree()
        floors = check_pins.pyproject_floors()
        assert floors["kgmodule-utils"] == "0.11.0"  # plain, with extras
        assert floors["doc-kg"] == "0.21.1"  # poetry-parenthesised
        assert floors["kg-rag"] == "0.11.0"  # declared only in an extra

    def test_highest_floor_wins_when_declared_twice(self, tree):
        # kgmodule-utils appears in [project].dependencies and again in viz3d.
        tree(pyproject={"kgmodule": "0.10.0", "kgmodule_viz3d": "0.11.0"})
        assert check_pins.pyproject_floors()["kgmodule-utils"] == "0.11.0"

    def test_runpod_comments_and_blank_lines_ignored(self, tree):
        tree()
        assert check_pins.runpod_floors() == {
            "kg-rag": "0.11.0",
            "doc-kg": "0.21.1",
            "diary-kg": "0.96.0",
            "kgmodule-utils": "0.11.0",
        }

    def test_missing_runpod_file_is_not_an_error(self, tree, tmp_path, monkeypatch):
        tree()
        monkeypatch.setattr(check_pins, "RUNPOD_REQS", tmp_path / "absent.txt")
        assert check_pins.runpod_floors() == {}
        assert check_pins.main() == 0


class TestPassing:
    def test_consistent_tree_passes(self, tree, capsys):
        tree()
        assert check_pins.main() == 0
        assert "Pins agree" in capsys.readouterr().out


class TestDriftIsCaught:
    def test_dockerfile_below_pyproject_floor(self, tree, capsys):
        # The real defect: ARG 0.10.0 against a >=0.11.0 floor. `pip install .`
        # upgrades past it, so the ARG names a version no build runs.
        tree(dockerfile={"kgmodule": "0.10.0"}, lock={"kgmodule": "0.10.0"})
        assert check_pins.main() == 1
        assert "below pyproject's" in capsys.readouterr().out

    def test_runpod_below_pyproject_floor(self, tree, capsys):
        # The second instance of the same drift, in the serverless worker.
        tree(runpod={"kgmodule": "0.10.0"})
        assert check_pins.main() == 1
        out = capsys.readouterr().out
        assert "runpod/requirements.txt" in out

    def test_lock_and_dockerfile_disagree(self, tree, capsys):
        tree(
            lock={"dockg": "0.21.1"}, dockerfile={"dockg": "0.22.0"}, pyproject={"dockg": "0.21.1"}
        )
        assert check_pins.main() == 1
        assert "different versions" in capsys.readouterr().out

    def test_stray_compose_build_arg(self, tree, capsys):
        # A compose-side copy overrides the Dockerfile default at build time.
        tree(compose=_COMPOSE_WITH_ARG)
        assert check_pins.main() == 1
        assert "docker-compose.yml sets" in capsys.readouterr().out

    def test_package_missing_from_lock(self, tree, capsys, tmp_path, monkeypatch):
        tree()
        # A distinct filename: `tree` owns tmp_path/poetry.lock and would
        # overwrite a partial one written under that name.
        lock = tmp_path / "partial.lock"
        lock.write_text('[[package]]\nname = "kg-rag"\nversion = "0.11.0"\n')
        monkeypatch.setattr(check_pins, "LOCK", lock)
        assert check_pins.main() == 1
        assert "not in poetry.lock" in capsys.readouterr().out

    def test_missing_dockerfile_arg(self, tree, capsys, tmp_path, monkeypatch):
        tree()
        dockerfile = tmp_path / "Dockerfile.partial"
        dockerfile.write_text("FROM python:3.12-slim\nARG KG_RAG_VERSION=0.11.0\n")
        monkeypatch.setattr(check_pins, "DOCKERFILE", dockerfile)
        assert check_pins.main() == 1
        assert "no ARG" in capsys.readouterr().out


class TestRealRepo:
    def test_this_repo_passes_its_own_check(self):
        """The gate must be green on the tree it ships with."""
        assert check_pins.main() == 0
