#!/usr/bin/env python3
# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
Verify the KG pins agree across every place this repo names them.

The four KG packages (kg-rag, kgmodule-utils, doc-kg, diary-kg) are cross-pinned
and named in four files that drift independently:

    pyproject.toml            floors  (>=)  — what the wheel demands
    poetry.lock               exact         — what the local build resolves
    docker/Dockerfile         exact  (==)   — what the served image installs
    runpod/requirements.txt   floors  (>=)  — what the serverless worker installs

docker/docker-compose.yml deliberately carries no version build args: the pins
live in ONE place, the Dockerfile ARGs, so a compose build and `make build`
produce the same image. Compose is still read here, to catch a stray one coming
back — that duplication is how this repo once drifted to kgmodule-utils 0.4.6
while the Dockerfile said 0.5.0.

Why the floor check matters here specifically
---------------------------------------------
docker/Dockerfile pre-installs the pinned KG stack and *then* runs
``pip install .`` on this package. That second install re-resolves against
pyproject's floors, so an ARG below its floor is silently upgraded: the ARG
becomes a number no build ever runs, the cached layer is fetched twice, and the
``==`` pins stop describing the image they claim to. It is not a build failure,
which is exactly why it survived unnoticed until an audit went looking —
KGMODULE_UTILS_VERSION sat at 0.10.0 against a >=0.11.0 floor.

corpus_pepys carries a sibling of this script that deliberately omits the floor
check: that project is ``package-mode = false`` with no ``pip install .`` step,
so its Dockerfile pins are the last word. Here they are not.

Usage:
    python scripts/check_pins.py

Exit status:
    0  all pins agree
    1  a mismatch, or a version could not be read
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
LOCK = ROOT / "poetry.lock"
DOCKERFILE = ROOT / "docker" / "Dockerfile"
COMPOSE = ROOT / "docker" / "docker-compose.yml"
RUNPOD_REQS = ROOT / "runpod" / "requirements.txt"

# distribution name -> Dockerfile ARG name
PINNED = {
    "kg-rag": "KG_RAG_VERSION",
    "kgmodule-utils": "KGMODULE_UTILS_VERSION",
    "doc-kg": "DOC_KG_VERSION",
    "diary-kg": "DIARY_KG_VERSION",
}

# Matches a PEP 508 requirement's name, optional extras, and its `>=` floor,
# in both the plain (`doc-kg>=0.21.1`) and poetry-parenthesised
# (`doc-kg (>=0.21.1)`) spellings pyproject mixes.
_REQ = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)"
    r"(?:\[[^\]]*\])?"
    r"\s*\(?\s*>=\s*"
    r"(?P<floor>[0-9][^,\s)]*)"
)


def _version_key(version: str) -> tuple[int, ...]:
    """Split a simple ``X.Y.Z`` version into an int tuple for comparison.

    Deliberately not ``packaging.version``: this script is run by
    ``make build`` as a gate and should not depend on anything beyond the
    stdlib. Every version in play here is plain numeric dotted form; a
    non-numeric component sorts as 0 rather than raising, so a pre-release
    tag degrades to a loose comparison instead of a crash.

    :param version: Version string such as ``"0.21.1"``.
    :returns: Tuple of ints suitable for ordering comparisons.
    """
    parts: list[int] = []
    for chunk in version.split("."):
        digits = re.match(r"\d+", chunk)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def lock_versions() -> dict[str, str]:
    """Read exact locked versions from poetry.lock.

    :returns: mapping of distribution name to locked version.
    """
    data = tomllib.loads(LOCK.read_text())
    return {pkg["name"]: pkg["version"] for pkg in data.get("package", [])}


def pyproject_floors() -> dict[str, str]:
    """Read the highest ``>=`` floor declared for each pinned package.

    A package may be declared more than once under different extras —
    ``kgmodule-utils`` appears in ``[project].dependencies`` with
    ``[synthesis,sqlite-vec]`` and again in the ``viz3d`` extra with
    ``[viz3d]``. pip resolves against the most restrictive, so that is what is
    compared here.

    :returns: mapping of distribution name to its highest declared floor.
    """
    data = tomllib.loads(PYPROJECT.read_text())
    project = data.get("project", {})
    requirements = list(project.get("dependencies", []))
    for extra_reqs in (project.get("optional-dependencies") or {}).values():
        requirements.extend(extra_reqs)

    floors: dict[str, str] = {}
    for req in requirements:
        match = _REQ.match(req)
        if not match:
            continue
        name = match.group("name")
        if name not in PINNED:
            continue
        floor = match.group("floor")
        if name not in floors or _version_key(floor) > _version_key(floors[name]):
            floors[name] = floor
    return floors


def runpod_floors() -> dict[str, str]:
    """Read ``>=`` floors for the pinned packages from runpod/requirements.txt.

    :returns: mapping of distribution name to its declared floor.
    """
    if not RUNPOD_REQS.exists():
        return {}
    floors: dict[str, str] = {}
    for line in RUNPOD_REQS.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _REQ.match(line)
        if match and match.group("name") in PINNED:
            floors[match.group("name")] = match.group("floor")
    return floors


def dockerfile_args() -> dict[str, str]:
    """Read ``ARG <NAME>_VERSION=<value>`` defaults from docker/Dockerfile.

    :returns: mapping of ARG name to its default value.
    """
    pattern = re.compile(r"^ARG\s+(\w+_VERSION)=(\S+)", re.MULTILINE)
    return dict(pattern.findall(DOCKERFILE.read_text()))


def compose_args() -> dict[str, str]:
    """Read version build args from docker-compose.yml.

    There should be none — see the module docstring. Any hit is reported as a
    problem rather than merely compared, because a compose-side copy silently
    overrides the Dockerfile default at build time.

    :returns: mapping of build-arg name to value.
    """
    pattern = re.compile(r"^\s+(\w+_VERSION):\s*(\S+)", re.MULTILINE)
    return dict(pattern.findall(COMPOSE.read_text()))


def main() -> int:
    """Compare the pins across all four files and report.

    :returns: process exit status.
    """
    locked = lock_versions()
    floors = pyproject_floors()
    runpod = runpod_floors()
    dockerfile = dockerfile_args()
    compose = compose_args()
    problems: list[str] = []

    print(f"{'package':<18} {'lock':<10} {'Dockerfile':<12} {'floor':<10} runpod")
    print("-" * 62)

    for dist, arg in PINNED.items():
        lock_v = locked.get(dist)
        docker_v = dockerfile.get(arg)
        floor_v = floors.get(dist)
        runpod_v = runpod.get(dist)

        print(
            f"{dist:<18} {lock_v or '—':<10} {docker_v or '—':<12} "
            f"{'>=' + floor_v if floor_v else '—':<10} {'>=' + runpod_v if runpod_v else '—'}"
        )

        if lock_v is None:
            problems.append(f"{dist}: not in poetry.lock (run 'poetry lock')")
        if docker_v is None:
            problems.append(f"{dist}: no ARG {arg} in docker/Dockerfile")

        if lock_v and docker_v and lock_v != docker_v:
            problems.append(
                f"{dist}: poetry.lock has {lock_v} but Dockerfile ARG {arg}={docker_v} "
                f"— the local build and the image would run different versions"
            )

        # The check that matters most here: `pip install .` re-resolves against
        # the floor, so an ARG below it is a pin that cannot hold.
        if docker_v and floor_v and _version_key(docker_v) < _version_key(floor_v):
            problems.append(
                f"{dist}: Dockerfile ARG {arg}={docker_v} is below pyproject's "
                f">={floor_v} floor — `pip install .` will silently upgrade it, so "
                f"the ARG names a version no build actually runs"
            )

        if runpod_v and floor_v and _version_key(runpod_v) < _version_key(floor_v):
            problems.append(
                f"{dist}: runpod/requirements.txt has >={runpod_v} but pyproject "
                f"floors >={floor_v} — the serverless worker may install a version "
                f"the package itself rejects"
            )

        if arg in compose:
            problems.append(
                f"{dist}: docker-compose.yml sets {arg}={compose[arg]}, overriding the "
                f"Dockerfile default at build time — the pins belong only in the Dockerfile"
            )

    print()
    if problems:
        print("PIN MISMATCH:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("Pins agree: lock, Dockerfile ARGs, pyproject floors and runpod all match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
