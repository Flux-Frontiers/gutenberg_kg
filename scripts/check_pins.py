#!/usr/bin/env python3
# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
Verify the KG pins agree across every place this repo names them.

The four KG packages (kg-rag, kgmodule-utils, doc-kg, diary-kg) are cross-pinned
and named in four files that drift independently:

    pyproject.toml            floors  (>=)  — what the wheel demands
    poetry.lock               exact         — what the local build resolves
    docker/Dockerfile         exact         — what the served image installs
    runpod/requirements.txt   floors  (>=)  — what the serverless worker installs

docker/docker-compose.yml is read too, but holds no version args by design: the
pins live in one place, the Dockerfile, so a compose build and `make build`
produce the same image. Any build arg found there is reported as drift.

The index is built locally against the lock and read by the container against
the Dockerfile ARGs. Those two must match: doc-kg >=0.18.2 changed the vector
store layout, so a builder older than the runtime emits an index the container
cannot open — and the failure is silent, surfacing as empty query results
rather than an error.

Why the floors ARE checked here
-------------------------------
docker/Dockerfile pins the KG stack and *then* runs ``pip install .``. That
second install re-resolves against pyproject's floors, so an ARG below its floor
is silently upgraded: the ARG names a version no build ever runs, and the pinned
layer is fetched twice. The Dockerfile carries the same warning beside its ARGs —
"an ARG below pyproject's floor is fiction ... Keep every ARG == the lock" —
recording the audit that found KGMODULE_UTILS_VERSION at 0.10.0 against a
>=0.12.1 floor.

corpus_pepys carries a sibling of this script that omits the floor and runpod
checks. That repo is ``package-mode = false`` with no ``pip install .`` step and
no serverless worker, so its Dockerfile pins are the last word. Here they are
not, and importing its policy silently deletes two real checks.

PyPI is queried for each pinned distribution. Being behind the latest release
is reported but is NOT a failure — the pins move as a deliberate set, not
whenever a sibling publishes. A pin PyPI has no installable files for IS a
failure: the container build would fail on it.

``--bump`` moves that whole set to the latest PyPI release: it raises the
pyproject and runpod floors, rewrites the Dockerfile ARGs, then runs
``poetry lock`` so the lock agrees. Every place a version is named moves
together — bumping a subset would leave one of them behind, which is the drift
this exists to catch, so it refuses outright if PyPI cannot be read for any one
of them. docker-compose.yml is not rewritten: it is meant to hold no version
args at all.

It raises every declaration of a package to the same version. That is what this
repo wants — pyproject states one floor per package across all declarations —
but it is still a published wheel's floor, so read the diff before committing a
bump.

Usage:
    python scripts/check_pins.py
    python scripts/check_pins.py --offline    # skip the PyPI lookups
    python scripts/check_pins.py --bump       # move every pin to PyPI latest

Exit status:
    0  all pins agree (or the bump succeeded)
    1  a mismatch, an unpublished pin, a failed bump, or an unreadable version
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "poetry.lock"
PYPROJECT = ROOT / "pyproject.toml"
DOCKERFILE = ROOT / "docker" / "Dockerfile"
COMPOSE = ROOT / "docker" / "docker-compose.yml"
RUNPOD_REQS = ROOT / "runpod" / "requirements.txt"

# distribution name -> Dockerfile ARG name.
# kg-rag belongs here, not in a container-only bucket: it is declared in the
# `kgdeps` extra and carries a poetry.lock entry, so its lock-vs-ARG comparison
# is meaningful. (It is container-only in corpus_pepys, which is where the
# opposite claim came from.)
PINNED = {
    "kg-rag": "KG_RAG_VERSION",
    "kgmodule-utils": "KGMODULE_UTILS_VERSION",
    "doc-kg": "DOC_KG_VERSION",
    "diary-kg": "DIARY_KG_VERSION",
}

PYPI_TIMEOUT = 10

# Versions are compared as int tuples padded to this many components, so a
# 2-component pin does not sort below its 3-component equal.
_VERSION_WIDTH = 4


# Matches a PEP 508 requirement's name, optional extras, and its `>=` floor, in
# both the plain (`doc-kg>=0.21.2`) and poetry-parenthesised (`doc-kg (>=0.21.2)`)
# spellings pyproject mixes.
_REQ = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)"
    r"(?:\[[^\]]*\])?"
    r"\s*\(?\s*>=\s*"
    r"(?P<floor>[0-9][^,\s)]*)"
)


def _version_key(version: str) -> tuple[int, ...]:
    """Split a dotted version into an int tuple for ordering.

    Deliberately not ``packaging.version``: this runs as a ``make build`` gate
    and should not depend on anything beyond the stdlib. A non-numeric component
    sorts as 0 rather than raising, so a pre-release tag degrades to a loose
    comparison instead of a crash.

    Short versions are zero-padded before comparison. Without that, ``(0, 19)``
    sorts below ``(0, 19, 0)`` and a ``>=0.19`` floor reads as *below* a 0.19.0
    ARG, reporting a mismatch that is not one. Padding never truncates, so
    0.19.0.1 still sorts above 0.19.0.

    :param version: version string such as ``"0.21.2"``.
    :returns: tuple of ints suitable for comparison.
    """
    parts: list[int] = []
    for chunk in version.split("."):
        digits = re.match(r"\d+", chunk)
        parts.append(int(digits.group()) if digits else 0)
    parts += [0] * (_VERSION_WIDTH - len(parts))
    return tuple(parts)


def pyproject_floors() -> dict[str, str]:
    """Read the highest ``>=`` floor declared for each pinned package.

    A package may be declared several times under different extras —
    ``kgmodule-utils`` appears in ``[project].dependencies`` and again in the
    ``viz3d`` and ``pov`` extras. They are meant to agree; pip resolves against
    the most restrictive, so the highest is what is compared — which also means
    a stale low floor is invisible here. Only a reader catches that one.

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
        if not match or match.group("name") not in PINNED:
            continue
        name, floor = match.group("name"), match.group("floor")
        if name not in floors or _version_key(floor) > _version_key(floors[name]):
            floors[name] = floor
    return floors


def runpod_floors() -> dict[str, str]:
    """Read ``>=`` floors for the pinned packages from runpod/requirements.txt.

    The serverless worker installs from this file, not from the wheel, so it can
    drift below what the package itself requires.

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


def lock_versions() -> dict[str, str]:
    """Read exact locked versions from poetry.lock.

    :returns: mapping of distribution name to locked version.
    """
    data = tomllib.loads(LOCK.read_text())
    return {pkg["name"]: pkg["version"] for pkg in data.get("package", [])}


def dockerfile_args() -> dict[str, str]:
    """Read ``ARG <NAME>_VERSION=<value>`` defaults from the Dockerfile.

    :returns: mapping of ARG name to its default value.
    """
    pattern = re.compile(r"^ARG\s+(\w+_VERSION)=(\S+)", re.MULTILINE)
    return dict(pattern.findall(DOCKERFILE.read_text()))


def compose_args() -> dict[str, str]:
    """Read version build args from docker-compose.yml.

    There should be none — the pins live only in the Dockerfile ARGs. Any hit is
    reported as a problem rather than merely compared, because a compose-side
    copy silently overrides the Dockerfile default at build time.

    :returns: mapping of build-arg name to value.
    """
    pattern = re.compile(r"^\s+(\w+_VERSION):\s*(\S+)", re.MULTILINE)
    return dict(pattern.findall(COMPOSE.read_text()))


def pypi_releases(dist: str) -> tuple[str, set[str]] | None:
    """Ask PyPI for a distribution's latest version and its installable releases.

    A release with no files (yanked or deleted) is omitted: pip cannot install
    it, so a pin naming one would fail the container build.

    :param dist: distribution name, as it appears on PyPI.
    :returns: ``(latest, released_versions)``, or ``None`` if PyPI could not
        be read — an unreachable index is not evidence of drift.
    """
    try:
        url = f"https://pypi.org/pypi/{dist}/json"
        with urllib.request.urlopen(url, timeout=PYPI_TIMEOUT) as r:
            data = json.load(r)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    latest = data.get("info", {}).get("version")
    if not latest:
        return None
    return latest, {v for v, files in data.get("releases", {}).items() if files}


def rewrite(path: Path, pattern: re.Pattern[str], version: str, label: str) -> list[str]:
    """Rewrite every ``pattern`` match in ``path`` to pin ``version``.

    The pattern must capture the text leading up to the version in group 1 and
    the version itself in group 2; group 1 is preserved so extras markers and
    ``>=`` operators survive the edit.

    :param path: file to rewrite in place; left untouched if nothing changes.
    :param pattern: two-group pattern locating the version to replace.
    :param version: version to pin.
    :param label: description of what is being pinned, for the change log.
    :returns: one entry per version actually changed.
    """
    changes: list[str] = []
    text = path.read_text()

    def replace(match: re.Match[str]) -> str:
        if match.group(2) == version:
            return match.group(0)
        changes.append(f"{path.name:<18} {label} {match.group(2)} -> {version}")
        return f"{match.group(1)}{version}"

    updated = pattern.sub(replace, text)
    if updated != text:
        path.write_text(updated)
    return changes


def bump_files(targets: dict[str, str]) -> list[str]:
    """Pin every declaration of ``targets`` in pyproject, the Dockerfile and runpod.

    The pyproject and runpod floors are ``>=`` constraints and stay that way —
    only the floor moves. The Dockerfile ARGs are exact pins.

    docker-compose.yml is deliberately NOT rewritten. The checker reports any
    version build arg there as drift whether it agrees or not, because the pins
    belong in one place; rewriting a compose copy would keep alive exactly what
    that check exists to reject, and a bump would leave the repo failing its own
    gate.

    **This raises every declaration of a package to the same version**, which is
    what pyproject's one-floor-per-package rule asks for. It is still a published
    wheel's floor, so check the diff before committing a bump.

    :param targets: mapping of distribution name to the version to pin.
    :returns: one entry per edit made, in file order.
    """
    changes: list[str] = []
    for dist, version in targets.items():
        arg = PINNED[dist]
        changes += rewrite(
            PYPROJECT,
            # Two shapes appear, and both must move or the bump is half-applied:
            #   "kgmodule-utils[synthesis]>=0.14.0"   extras marker, bare operator
            #   "doc-kg (>=0.21.2)"                   poetry's parenthesised PEP 508
            # The optional space and paren are part of group 1 so they survive;
            # group 2 stops before the closing paren so it is not eaten.
            re.compile(rf'("{re.escape(dist)}(?:\[[^\]]*\])?\s*\(?>=)([^",\s)]+)'),
            version,
            f"{dist} >=",
        )
        changes += rewrite(
            DOCKERFILE, re.compile(rf"^(ARG\s+{arg}=)(\S+)", re.MULTILINE), version, arg
        )
        # The serverless worker installs from this file rather than the wheel,
        # so leaving it behind is the same half-applied bump in another place.
        changes += rewrite(
            RUNPOD_REQS,
            re.compile(rf"^({re.escape(dist)}(?:\[[^\]]*\])?>=)(\S+)", re.MULTILINE),
            version,
            f"{dist} >=",
        )
    return changes


def bump(targets: dict[str, str], locked: dict[str, str], unreachable: list[str]) -> int:
    """Move every pin to its latest PyPI release and re-lock.

    Refuses to move anything unless PyPI answered for *every* pinned package.
    The set moves together or not at all: bumping the reachable subset would
    leave the rest behind, which is the drift this script exists to catch.

    :param targets: mapping of distribution name to the version to pin.
    :param locked: currently locked versions, to decide whether the lock is stale.
    :param unreachable: pinned packages PyPI could not be read for.
    :returns: process exit status.
    """
    if unreachable:
        print(
            f"BUMP FAILED: PyPI could not be read for {', '.join(unreachable)}.\n"
            "  The pins move as a set, so bumping the reachable ones would leave "
            "these behind —\n  which is the drift this script exists to catch. "
            "Nothing was changed."
        )
        return 1
    if not targets:
        print("BUMP FAILED: PyPI could not be read, so there is nothing to bump to.")
        return 1

    changes = bump_files(targets)
    for change in changes:
        print(f"  {change}")

    stale = [d for d, v in targets.items() if locked.get(d) != v]
    if not changes and not stale:
        print("  (nothing to do — every pin is already at the latest PyPI release)")
        return 0

    print(f"\nRunning 'poetry lock' so poetry.lock agrees ({', '.join(stale) or 'no-op'}) ...")
    if subprocess.run(["poetry", "lock"], cwd=ROOT, check=False).returncode != 0:
        print("\nBUMP FAILED: 'poetry lock' could not resolve the new floors.")
        return 1

    print(f"\nBumped {len(changes)} declaration(s). Re-run without --bump to verify.")
    return 0


def main() -> int:
    """Compare the pins and report.

    :returns: process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--offline", action="store_true", help="skip the PyPI lookups and compare files only"
    )
    parser.add_argument(
        "--bump",
        action="store_true",
        help="rewrite the pyproject floors, Dockerfile ARGs and runpod floors to "
        "the latest PyPI release, then run 'poetry lock'",
    )
    args = parser.parse_args()
    if args.bump and args.offline:
        parser.error("--bump needs PyPI; it cannot be combined with --offline")

    locked, dockerfile, compose = lock_versions(), dockerfile_args(), compose_args()
    floors, runpod = pyproject_floors(), runpod_floors()
    pypi: dict[str, tuple[str, set[str]] | None] = (
        {} if args.offline else {dist: pypi_releases(dist) for dist in PINNED}
    )
    problems: list[str] = []
    behind: list[str] = []

    def pypi_cell(dist: str, pinned: str | None) -> str:
        """Render the PyPI column, flagging a pin that is behind or unpublished."""
        info = pypi.get(dist)
        if info is None:
            return "(offline)" if args.offline else "(unreachable)"
        latest, released = info
        if pinned and pinned not in released:
            problems.append(
                f"{dist}: {pinned} is pinned but PyPI has no installable files for it "
                f"(latest is {latest}) — the container build would fail"
            )
            return f"{latest}  ← {pinned} unpublished"
        if pinned and pinned != latest:
            behind.append(f"{dist}: pinned {pinned}, PyPI latest {latest}")
            return f"{latest}  ← behind"
        return latest

    print(
        f"{'package':<18} {'poetry.lock':<12} {'Dockerfile':<12} "
        f"{'floor':<10} {'runpod':<10} PyPI latest"
    )
    print("-" * 96)

    for dist, arg in PINNED.items():
        lock_v = locked.get(dist)
        docker_v = dockerfile.get(arg)
        compose_v = compose.get(arg)
        floor_v = floors.get(dist)
        runpod_v = runpod.get(dist)

        if lock_v is None:
            problems.append(f"{dist}: not in poetry.lock (run 'poetry lock')")
        if docker_v is None:
            problems.append(f"{dist}: no ARG {arg} in docker/Dockerfile")
        if lock_v and docker_v and lock_v != docker_v:
            problems.append(
                f"{dist}: poetry.lock has {lock_v} but Dockerfile ARG {arg}={docker_v} "
                f"— the index would be built by {lock_v} and read by {docker_v}"
            )
        # Any version arg in compose is drift here, matching or not. The pins
        # live in one place so a compose build and `make build` cannot diverge;
        # a duplicate that agrees today is the one that drifts tomorrow, which
        # is how this repo reached kgmodule-utils 0.4.6 against a Dockerfile
        # saying 0.5.0. corpus_pepys only compares them, and that is the check
        # this repo had before its policy was imported.
        if compose_v is not None:
            problems.append(
                f"{dist}: docker-compose.yml sets {arg}={compose_v}, overriding the "
                f"Dockerfile default at build time — the pins belong only in the Dockerfile"
            )
        # The check this repo needs most: `pip install .` re-resolves against the
        # floor, so an ARG below it is a pin that cannot hold.
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

        print(
            f"{dist:<18} {lock_v or '—':<12} {docker_v or '—':<12} "
            f"{('>=' + floor_v) if floor_v else '—':<10} "
            f"{('>=' + runpod_v) if runpod_v else '—':<10} "
            f"{pypi_cell(dist, docker_v or lock_v)}"
        )

    print()
    if args.bump:
        # The table above is the pre-bump state; every problem it found is
        # about to be overwritten by the latest release, so it is not reported.
        print("Bumping every pin to the latest PyPI release:")
        return bump(
            {d: info[0] for d, info in pypi.items() if info},
            locked,
            sorted(d for d, info in pypi.items() if not info),
        )

    if behind:
        print("Behind PyPI (advisory — the KG pins move as a set, not per release):")
        for b in behind:
            print(f"  - {b}")
        print()

    if problems:
        print("PIN MISMATCH:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("Pins agree: lock, Dockerfile ARGs, pyproject floors and runpod all match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
