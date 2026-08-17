#!/usr/bin/env python3
# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
Verify the KG pins agree across poetry.lock, the Dockerfile and docker-compose.

The index is built locally by the [build] extra (whose versions poetry.lock
pins exactly) and read by the container (whose versions the Dockerfile ARGs
pin exactly). Those two must match: doc-kg >=0.18.2 changed the vector store
layout, so a builder older than the runtime emits an index the container
cannot open — and the failure is silent, surfacing as empty query results
rather than an error.

The pyproject floors are deliberately NOT checked. They express intent; the
lock is what `make install` actually installs, so the lock is the truth about
what built the index. `poetry update` moves the lock without touching the
Dockerfile — that is the drift this catches.

PyPI is queried for each pinned distribution. Being behind the latest release
is reported but is NOT a failure — the pins move as a deliberate set, not
whenever a sibling publishes. A pin PyPI has no installable files for IS a
failure: the container build would fail on it.

``--bump`` moves that whole set to the latest PyPI release: it raises the
pyproject floors, rewrites the Dockerfile ARGs and any compose build args,
then runs ``poetry lock`` so the lock agrees. Bumping only the Dockerfile
would leave the builder behind the runtime — the exact drift this catches.

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

# distribution name -> Dockerfile ARG name
PINNED = {
    "diary-kg": "DIARY_KG_VERSION",
    "doc-kg": "DOC_KG_VERSION",
    "kgmodule-utils": "KGMODULE_UTILS_VERSION",
}

# Installed in the container but not a project dependency, so it has no lock
# entry to compare against. Reported for visibility, not checked.
CONTAINER_ONLY = {"kg-rag": "KG_RAG_VERSION"}

PYPI_TIMEOUT = 10


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
    """Read build args from docker-compose.yml.

    Compose carries its own copy of some version args, which override the
    Dockerfile defaults at build time — so they must agree too.

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
    """Pin every declaration of ``targets`` in pyproject, Dockerfile and compose.

    The pyproject floors are ``>=`` constraints and stay that way — only the
    floor moves. The Dockerfile ARGs and compose build args are exact pins.

    :param targets: mapping of distribution name to the version to pin.
    :returns: one entry per edit made, in file order.
    """
    changes: list[str] = []
    for dist, version in targets.items():
        arg = {**PINNED, **CONTAINER_ONLY}[dist]
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
        changes += rewrite(
            COMPOSE, re.compile(rf"^(\s+{arg}:\s*)(\S+)", re.MULTILINE), version, arg
        )
    return changes


def bump(targets: dict[str, str], locked: dict[str, str]) -> int:
    """Move every pin to its latest PyPI release and re-lock.

    :param targets: mapping of distribution name to the version to pin.
    :param locked: currently locked versions, to decide whether the lock is stale.
    :returns: process exit status.
    """
    if not targets:
        print("BUMP FAILED: PyPI could not be read, so there is nothing to bump to.")
        return 1

    changes = bump_files(targets)
    for change in changes:
        print(f"  {change}")

    stale = [d for d, v in targets.items() if d in PINNED and locked.get(d) != v]
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
        help="rewrite the pyproject floors, Dockerfile ARGs and compose args to the "
        "latest PyPI release, then run 'poetry lock'",
    )
    args = parser.parse_args()
    if args.bump and args.offline:
        parser.error("--bump needs PyPI; it cannot be combined with --offline")

    locked, dockerfile, compose = lock_versions(), dockerfile_args(), compose_args()
    pypi: dict[str, tuple[str, set[str]] | None] = (
        {} if args.offline else {dist: pypi_releases(dist) for dist in (*PINNED, *CONTAINER_ONLY)}
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

    print(f"{'package':<18} {'poetry.lock':<14} {'Dockerfile':<14} {'compose':<14} PyPI latest")
    print("-" * 90)

    for dist, arg in PINNED.items():
        lock_v = locked.get(dist)
        docker_v = dockerfile.get(arg)
        compose_v = compose.get(arg)

        if lock_v is None:
            problems.append(f"{dist}: not in poetry.lock (run 'poetry lock')")
        if docker_v is None:
            problems.append(f"{dist}: no ARG {arg} in docker/Dockerfile")
        if lock_v and docker_v and lock_v != docker_v:
            problems.append(
                f"{dist}: poetry.lock has {lock_v} but Dockerfile ARG {arg}={docker_v} "
                f"— the index would be built by {lock_v} and read by {docker_v}"
            )
        if compose_v and docker_v and compose_v != docker_v:
            problems.append(
                f"{dist}: docker-compose.yml sets {arg}={compose_v}, overriding "
                f"the Dockerfile default {docker_v} at build time"
            )

        print(
            f"{dist:<18} {lock_v or '—':<14} {docker_v or '—':<14} "
            f"{compose_v or '—':<14} {pypi_cell(dist, docker_v or lock_v)}"
        )

    for dist, arg in CONTAINER_ONLY.items():
        docker_v = dockerfile.get(arg)
        print(
            f"{dist:<18} {'(none)':<14} {docker_v or '—':<14} "
            f"{compose.get(arg) or '—':<14} {pypi_cell(dist, docker_v)}   container-only"
        )

    print()
    if args.bump:
        # The table above is the pre-bump state; every problem it found is
        # about to be overwritten by the latest release, so it is not reported.
        print("Bumping every pin to the latest PyPI release:")
        return bump({d: info[0] for d, info in pypi.items() if info}, locked)

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

    print("Pins agree: the index builder and the container runtime match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
