#!/usr/bin/env python3
# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
Fail on any mkdocs --strict warning that is not already an accepted one.

Plain ``mkdocs build`` (what docs.yml's CI job runs) exits 0 on a broken
internal link or a missing nav target — those are warnings, not errors, so
they build a working site with a dead link and nobody notices until someone
clicks it. ``--strict`` turns every warning into a build failure, but two
categories of warning are permanent and expected rather than regressions —
see the matching comment in .github/workflows/docs.yml:

    - docs/*.md cross-links to files outside docs_dir (src/, benchmarks/,
      scripts/, docker/, the top-level README) — these render fine on
      GitHub but have no target inside the built site.
    - one griffe warning on GutenbergForestVisualizer (viz3d.py), a
      param.Parameterized class whose docstring does not match its
      dynamically-generated __init__ signature.

This runs --strict, then reports failure only if a warning falls outside
those two patterns — so a *new* broken link or nav target still fails the
build, without permanently blocking on the known, accepted noise.

Skips (exit 0) when mkdocs is not installed: it lives in the optional
``docs`` Poetry group, not ``dev``, so most contributors will not have it.

Usage:
    python scripts/check_docs_build.py

Exit status:
    0  mkdocs is not installed, or every warning is an accepted one
    1  a warning fell outside the accepted patterns
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MKDOCS = ROOT / ".venv" / "bin" / "mkdocs"

ACCEPTED = [
    re.compile(r"contains a link '\.\./"),
    re.compile(r"griffe: src/gutenberg_kg/viz3d\.py:392:.*corpus_root"),
]


def main() -> int:
    """Run mkdocs --strict and triage its warnings against ACCEPTED.

    :returns: process exit status.
    """
    if not MKDOCS.exists():
        return 0

    result = subprocess.run(
        [str(MKDOCS), "build", "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return 0

    output = result.stdout + result.stderr
    unexpected = [
        line
        for line in output.splitlines()
        if "WARNING" in line and not any(p.search(line) for p in ACCEPTED)
    ]
    if not unexpected:
        return 0

    print("mkdocs build --strict found warning(s) outside the accepted set:\n")
    for line in unexpected:
        print(f"  {line}")
    print(
        "\nIf this is real, fix it. If it is a new, deliberately-accepted "
        "category, add it to ACCEPTED in scripts/check_docs_build.py and to "
        "the matching comment in .github/workflows/docs.yml."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
