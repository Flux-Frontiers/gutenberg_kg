"""Unit tests for scripts/check_pins.py.

The script is a build gate, so what matters is that it *fails* on each kind of
drift — a checker that cannot go red is worse than none, because it reads as a
guarantee. Each test points the module's file constants at a fixture tree in
tmp_path, so nothing depends on the repo's current pin values.

Four files name these pins and drift independently: pyproject floors, the lock,
the Dockerfile ARGs and runpod/requirements.txt. All four are compared, and the
floors matter most — docker/Dockerfile runs ``pip install .`` after pinning, so
an ARG below its floor is silently upgraded and names a version no build runs.

That paragraph replaces one asserting the opposite. This file briefly carried
corpus_pepys's policy, which omits the floor and runpod checks because that repo
has no ``pip install .`` step; the tests were written to agree with it and went
green on a contract that was never this repo's.

``--bump`` is the part worth testing hardest. It rewrites four files and then
runs ``poetry lock``, and its rewrite is a two-group regex where group 1 has to
carry extras markers and ``>=`` operators through untouched. A regex that eats
``[synthesis,sqlite-vec]`` would leave a pyproject that still parses and no
longer means the same thing.
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
viz3d = ["kgmodule-utils[viz3d]>={kgmodule}"]
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

_COMPOSE_CLEAN = """\
services:
  worker:
    build:
      context: ..
"""

_RUNPOD = """\
# a comment line that must be ignored
runpod>=1.7.0
kg-rag>={kgrag}
doc-kg>={dockg}
diary-kg>={diarykg}
kgmodule-utils[synthesis,sqlite-vec]>={kgmodule}
"""

_COMPOSE_WITH_ARG = """\
services:
  worker:
    build:
      context: ..
      args:
        KGMODULE_UTILS_VERSION: {kgmodule}
"""

_GOOD = {"kgrag": "0.12.0", "kgmodule": "0.16.0", "dockg": "0.21.2", "diarykg": "0.97.0"}


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Write a consistent fixture tree and point the module at it.

    :returns: a callable taking per-file version overrides and compose content.
    """

    def _build(*, pyproject=None, lock=None, dockerfile=None, compose=None, runpod=None):
        def _vals(overrides):
            merged = dict(_GOOD)
            merged.update(overrides or {})
            return merged

        written = {
            "PYPROJECT": ("pyproject.toml", _PYPROJECT.format(**_vals(pyproject))),
            "LOCK": ("poetry.lock", _LOCK.format(**_vals(lock))),
            "DOCKERFILE": ("Dockerfile", _DOCKERFILE.format(**_vals(dockerfile))),
            "RUNPOD_REQS": ("requirements.txt", _RUNPOD.format(**_vals(runpod))),
            "COMPOSE": (
                "docker-compose.yml",
                _COMPOSE_CLEAN if compose is None else _COMPOSE_WITH_ARG.format(**_vals(compose)),
            ),
        }
        paths = {}
        for attr, (name, content) in written.items():
            path = tmp_path / name
            path.write_text(content)
            monkeypatch.setattr(check_pins, attr, path)
            paths[attr] = path
        return paths

    return _build


@pytest.fixture
def offline(monkeypatch):
    """Run main() with --offline so no test touches the network."""
    monkeypatch.setattr(sys, "argv", ["check_pins.py", "--offline"])


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestParsing:
    def test_reads_locked_versions(self, tree):
        tree()
        assert check_pins.lock_versions()["kgmodule-utils"] == "0.16.0"

    def test_reads_dockerfile_args(self, tree):
        tree()
        assert check_pins.dockerfile_args()["KGMODULE_UTILS_VERSION"] == "0.16.0"

    def test_a_compose_without_build_args_is_empty_not_an_error(self, tree):
        tree()
        assert check_pins.compose_args() == {}

    def test_reads_compose_build_args_when_present(self, tree):
        tree(compose={"kgmodule": "0.9.0"})
        assert check_pins.compose_args()["KGMODULE_UTILS_VERSION"] == "0.9.0"


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


class TestPassing:
    def test_a_consistent_tree_passes(self, tree, offline):
        tree()
        assert check_pins.main() == 0

    def test_compose_agreeing_with_the_dockerfile_passes(self, tree, offline):
        tree(compose={})  # same versions as the Dockerfile
        assert check_pins.main() == 0


class TestDriftIsCaught:
    def test_lock_and_dockerfile_disagree(self, tree, offline, capsys):
        """The drift that matters: a different builder than runtime."""
        tree(dockerfile={"dockg": "0.20.0"})
        assert check_pins.main() == 1
        assert "0.20.0" in capsys.readouterr().out

    def test_compose_overrides_the_dockerfile(self, tree, offline, capsys):
        """A compose arg silently wins at build time, so disagreement is drift."""
        tree(compose={"kgmodule": "0.9.0"})
        assert check_pins.main() == 1
        assert "overriding" in capsys.readouterr().out

    def test_package_missing_from_lock(self, tree, offline, capsys):
        tree()
        check_pins.LOCK.write_text('[[package]]\nname = "doc-kg"\nversion = "0.21.2"\n')
        assert check_pins.main() == 1
        assert "not in poetry.lock" in capsys.readouterr().out

    def test_missing_dockerfile_arg(self, tree, offline, capsys):
        tree()
        check_pins.DOCKERFILE.write_text("FROM python:3.12-slim\n")
        assert check_pins.main() == 1
        assert "no ARG" in capsys.readouterr().out


class TestFloorsAreChecked:
    """The check this repo needs, and the one an imported policy deleted.

    docker/Dockerfile pins the KG stack and *then* runs ``pip install .``, which
    re-resolves against pyproject's floors. An ARG below its floor is silently
    upgraded, so the ARG names a version no build ever runs — the audit that
    found KGMODULE_UTILS_VERSION at 0.10.0 against a >=0.12.1 floor. corpus_pepys
    omits this check because it has no ``pip install .`` step; here it is the
    whole point.
    """

    def test_an_arg_below_the_floor_is_drift(self, tree, offline, capsys):
        tree(
            dockerfile={"kgmodule": "0.15.0"},
            lock={"kgmodule": "0.15.0"},
            pyproject={"kgmodule": "0.16.0"},
        )
        assert check_pins.main() == 1
        assert "silently upgrade" in capsys.readouterr().out

    def test_an_arg_at_the_floor_passes(self, tree, offline):
        tree(pyproject={"kgmodule": "0.16.0"})
        assert check_pins.main() == 0

    def test_the_highest_floor_wins_when_declared_twice(self, tree):
        """kgmodule-utils is declared in the core deps and again in an extra."""
        tree()
        assert check_pins.pyproject_floors()["kgmodule-utils"] == "0.16.0"


class TestRunpodIsChecked:
    """The serverless worker installs from requirements.txt, not the wheel."""

    def test_a_runpod_floor_below_pyproject_is_drift(self, tree, offline, capsys):
        tree(runpod={"dockg": "0.20.0"})
        assert check_pins.main() == 1
        assert "serverless worker" in capsys.readouterr().out

    def test_reads_runpod_floors_ignoring_comments(self, tree):
        tree()
        floors = check_pins.runpod_floors()
        assert floors["doc-kg"] == "0.21.2"
        assert "runpod" not in floors  # the un-pinned line is not a KG package

    def test_a_missing_runpod_file_is_not_an_error(self, tree):
        tree()
        check_pins.RUNPOD_REQS.unlink()
        assert check_pins.runpod_floors() == {}


class TestKgRagIsAFirstClassPin:
    """It has a lock entry here, unlike in corpus_pepys where it is image-only."""

    def test_kg_rag_is_pinned_not_container_only(self):
        assert "kg-rag" in check_pins.PINNED
        assert check_pins.CONTAINER_ONLY == {}

    def test_its_lock_and_arg_are_compared(self, tree, offline, capsys):
        tree(dockerfile={"kgrag": "0.11.0"})
        assert check_pins.main() == 1
        out = capsys.readouterr().out
        assert "kg-rag" in out and "0.11.0" in out


# ---------------------------------------------------------------------------
# PyPI awareness
# ---------------------------------------------------------------------------


def _fake_pypi(monkeypatch, table):
    """Point pypi_releases at a fixed table instead of the network."""
    monkeypatch.setattr(check_pins, "pypi_releases", lambda dist: table.get(dist))


class TestPypiReporting:
    @pytest.fixture
    def online(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["check_pins.py"])

    def test_being_behind_is_advisory_not_a_failure(self, tree, online, monkeypatch, capsys):
        """The KG pins move as a set, not whenever a sibling publishes."""
        tree()
        _fake_pypi(
            monkeypatch,
            {
                d: ("99.0.0", {"99.0.0", v})
                for d, v in (
                    ("kgmodule-utils", "0.16.0"),
                    ("doc-kg", "0.21.2"),
                    ("diary-kg", "0.97.0"),
                    ("kg-rag", "0.12.0"),
                )
            },
        )
        assert check_pins.main() == 0
        assert "behind" in capsys.readouterr().out.lower()

    def test_an_unpublished_pin_is_a_failure(self, tree, online, monkeypatch, capsys):
        """pip cannot install it, so the container build would fail."""
        tree()
        _fake_pypi(monkeypatch, {"doc-kg": ("0.21.2", {"0.21.2"})})
        check_pins.DOCKERFILE.write_text(
            _DOCKERFILE.format(**{**_GOOD, "dockg": "0.99.0"}).replace(
                "ARG DOC_KG_VERSION=0.99.0", "ARG DOC_KG_VERSION=0.99.0"
            )
        )
        check_pins.LOCK.write_text(_LOCK.format(**{**_GOOD, "dockg": "0.99.0"}))
        assert check_pins.main() == 1
        assert "unpublished" in capsys.readouterr().out

    def test_an_unreachable_index_is_not_evidence_of_drift(self, tree, online, monkeypatch):
        tree()
        _fake_pypi(monkeypatch, {})  # every lookup returns None
        assert check_pins.main() == 0


# ---------------------------------------------------------------------------
# --bump, which writes to disk
# ---------------------------------------------------------------------------


class TestBumpFiles:
    """The rewrite has to preserve everything left of the version."""

    def test_extras_markers_survive_the_rewrite(self, tree):
        paths = tree()
        check_pins.bump_files({"kgmodule-utils": "0.99.0"})
        text = paths["PYPROJECT"].read_text()
        assert '"kgmodule-utils[synthesis,sqlite-vec]>=0.99.0"' in text
        assert '"kgmodule-utils[viz3d]>=0.99.0"' in text

    def test_the_parenthesised_form_moves_too(self, tree):
        """`"doc-kg (>=0.21.2)"` is poetry's PEP 508 shape, and it is used here.

        The first regex only matched a bare `name>=version`, so `--bump` moved
        kgmodule-utils and kg-rag while silently leaving doc-kg and diary-kg
        behind — reporting success on a half-applied bump.
        """
        paths = tree()
        check_pins.bump_files({"doc-kg": "0.99.0", "diary-kg": "0.99.0"})
        text = paths["PYPROJECT"].read_text()
        assert "doc-kg (>=0.99.0)" in text
        assert "diary-kg (>=0.99.0)" in text
        assert "0.21.2" not in text and "0.97.0" not in text

    def test_the_floor_stays_a_floor(self, tree):
        paths = tree()
        check_pins.bump_files({"doc-kg": "0.99.0"})
        assert ">=0.99.0" in paths["PYPROJECT"].read_text()
        assert "==0.99.0" not in paths["PYPROJECT"].read_text()

    def test_every_declaration_is_moved_not_just_the_first(self, tree):
        """kgmodule-utils is declared twice; a lone floor left behind is drift."""
        paths = tree()
        check_pins.bump_files({"kgmodule-utils": "0.99.0"})
        assert paths["PYPROJECT"].read_text().count(">=0.99.0") == 2

    def test_dockerfile_args_are_exact_pins(self, tree):
        paths = tree()
        check_pins.bump_files({"doc-kg": "0.99.0"})
        assert "ARG DOC_KG_VERSION=0.99.0" in paths["DOCKERFILE"].read_text()

    def test_compose_args_move_too(self, tree):
        paths = tree(compose={})
        check_pins.bump_files({"kgmodule-utils": "0.99.0"})
        assert "KGMODULE_UTILS_VERSION: 0.99.0" in paths["COMPOSE"].read_text()

    def test_an_unrelated_package_is_untouched(self, tree):
        paths = tree()
        before = paths["PYPROJECT"].read_text()
        check_pins.bump_files({"doc-kg": "0.99.0"})
        after = paths["PYPROJECT"].read_text()
        assert "diary-kg (>=0.97.0)" in after
        assert before.count("kgmodule-utils") == after.count("kgmodule-utils")

    def test_runpod_floors_move_too(self, tree):
        """Leaving the worker behind is the same half-applied bump elsewhere."""
        paths = tree()
        check_pins.bump_files({"doc-kg": "0.99.0"})
        assert "doc-kg>=0.99.0" in paths["RUNPOD_REQS"].read_text()

    def test_a_noop_bump_reports_no_changes(self, tree):
        tree()
        assert check_pins.bump_files({"doc-kg": "0.21.2"}) == []

    def test_it_reports_what_it_changed(self, tree):
        tree()
        changes = check_pins.bump_files({"doc-kg": "0.99.0"})
        assert changes and all("0.21.2 -> 0.99.0" in c for c in changes)


class TestBumpGuards:
    def test_bump_without_pypi_fails_rather_than_writing(self, tree, capsys):
        """Nothing to bump *to* must not be read as nothing to bump."""
        paths = tree()
        before = paths["PYPROJECT"].read_text()
        assert check_pins.bump({}, {}) == 1
        assert "BUMP FAILED" in capsys.readouterr().out
        assert paths["PYPROJECT"].read_text() == before

    def test_bump_and_offline_are_rejected_together(self, tree, monkeypatch):
        tree()
        monkeypatch.setattr(sys, "argv", ["check_pins.py", "--bump", "--offline"])
        with pytest.raises(SystemExit):
            check_pins.main()


# ---------------------------------------------------------------------------
# This repo
# ---------------------------------------------------------------------------


class TestRealRepo:
    def test_this_repo_passes_its_own_check(self, monkeypatch):
        """The gate has to be green on the tree that ships."""
        monkeypatch.setattr(sys, "argv", ["check_pins.py", "--offline"])
        assert check_pins.main() == 0
