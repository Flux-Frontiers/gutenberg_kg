# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""poetry.lock must install at most one version of each package per platform.

Poetry 2.5.0 and 2.5.1 write a lock that drops part of an environment marker:
with torch 2.13 the second nvidia-cublas and nvidia-cuda-nvrtc entries were
marked ``platform_system == "Linux"`` instead of "Linux, but not x86_64 or
aarch64". On a Linux x86_64 runner both versions then installed over each
other and importing torch crashed with a segmentation fault. Poetry 2.4.3
writes the full marker. This test catches such a lock before CI installs it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.markers import Marker

LOCK = Path(__file__).resolve().parent.parent / "poetry.lock"

# The platforms the fleet installs on, as PEP 508 marker environments.
_BASE = {
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
    "python_version": "3.12",
    "python_full_version": "3.12.8",
    "platform_release": "",
    "platform_version": "",
    "extra": "",
}
PLATFORMS = {
    "linux-x86_64": {
        **_BASE,
        "sys_platform": "linux",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
        "os_name": "posix",
    },
    "macos-arm64": {
        **_BASE,
        "sys_platform": "darwin",
        "platform_system": "Darwin",
        "platform_machine": "arm64",
        "os_name": "posix",
    },
    "windows-amd64": {
        **_BASE,
        "sys_platform": "win32",
        "platform_system": "Windows",
        "platform_machine": "AMD64",
        "os_name": "nt",
    },
}


def _locked_packages() -> list[tuple[str, str, str | dict | None]]:
    """Return ``(name, version, markers)`` for every ``[[package]]`` in the lock.

    ``markers`` is a string, or a table of one marker per dependency group.
    """
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    return [(p["name"], p["version"], p.get("markers")) for p in lock["package"]]


def _satisfied(marker: str, env: dict) -> bool:
    if marker == "<empty>":  # Poetry's spelling of a marker nothing satisfies
        return False
    return Marker(marker).evaluate(env)


def _installs(markers: str | dict | None, env: dict) -> bool:
    if markers is None:
        return True
    if isinstance(markers, dict):  # installed if any group's marker holds
        return any(_satisfied(m, env) for m in markers.values())
    return _satisfied(markers, env)


@pytest.mark.parametrize("platform", sorted(PLATFORMS))
def test_one_version_per_package(platform: str) -> None:
    env = PLATFORMS[platform]
    chosen: dict[str, list[str]] = {}
    for name, version, markers in _locked_packages():
        if _installs(markers, env):
            chosen.setdefault(name, []).append(version)
    doubled = {name: vs for name, vs in chosen.items() if len(vs) > 1}
    assert not doubled, (
        f"poetry.lock installs two versions on {platform}: {doubled}. "
        "Relock with Poetry 2.4.3 (Poetry 2.5.x drops part of the marker)."
    )


# ---------------------------------------------------------------------------
# One Poetry everywhere: the lock header, pyproject and the CI pins agree
# ---------------------------------------------------------------------------

ROOT = LOCK.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _required_poetry() -> str:
    """Return the version ``requires-poetry = "==X"`` in pyproject.toml pins."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    spec = pyproject["tool"]["poetry"]["requires-poetry"]
    assert spec.startswith("=="), f"requires-poetry should pin one version, got {spec!r}"
    return spec[2:]


def test_lock_was_written_by_the_pinned_poetry() -> None:
    header = LOCK.read_text(encoding="utf-8").splitlines()[0]
    match = re.search(r"Poetry (\S+) ", header)
    assert match, f"no Poetry version in the lock header: {header!r}"
    assert match.group(1) == _required_poetry(), (
        f"poetry.lock was written by Poetry {match.group(1)}, but pyproject pins "
        f"{_required_poetry()}. Restore it (git checkout poetry.lock) and relock "
        "with the pinned Poetry."
    )


def test_every_ci_poetry_install_pins_the_same_version() -> None:
    want = _required_poetry()
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        lines = workflow.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if "snok/install-poetry" not in line:
                continue
            step = []  # the step's own lines, up to the next step or a blank
            for following in lines[i + 1 :]:
                if not following.strip() or following.lstrip().startswith("- "):
                    break
                step.append(following.strip())
            versions = [s.split(":", 1)[1].strip() for s in step if s.startswith("version:")]
            assert versions == [want], (
                f"{workflow.name}:{i + 1} installs Poetry {versions or 'unpinned'}; "
                f"pin `version: {want}` to match pyproject's requires-poetry."
            )
