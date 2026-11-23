# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""image_gen must import without kgmodule-utils.

The FLUX image server (`gutenkg-image-server`) runs in its own `.venv-image`,
installed with `pip install --no-deps -e .`, so kgmodule-utils is absent there.
A module-level import of the shared rewrite prompt crashed the server at start
(2026-11-17, launchd restart loop, "Network is unreachable" in the apps).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def test_image_gen_imports_without_kg_utils() -> None:
    """Block kg_utils, then import image_gen from this checkout's src."""
    code = "import sys\nsys.modules['kg_utils'] = None\nimport gutenberg_kg.image_gen\n"
    # This checkout's source, not whatever an editable install points at.
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr


_ALIASES_WITHOUT_IMAGEWRIGHT = (
    "import sys\n"
    "sys.modules['kg_utils'] = None\n"
    "sys.modules['imagewright'] = None\n"
    "import gutenberg_kg.image_gen\n"
    "import gutenberg_kg.serve.image_server as server\n"
    "import gutenberg_kg.serve.sdxl_server as sdxl\n"
    "assert callable(server.main) and callable(sdxl.main)\n"
)


def test_the_server_aliases_import_without_kg_utils_or_imagewright() -> None:
    """The aliases import in a `.venv-image` that lacks this package's dependencies.

    `.venv-image` is an editable install without them, kept alive by launchd,
    so a `git pull` changes the code it runs before anyone refreshes it. The
    aliases may import nothing but the standard library at module scope.
    """
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run(
        [sys.executable, "-c", _ALIASES_WITHOUT_IMAGEWRIGHT],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr


def test_an_alias_without_imagewright_exits_and_names_the_make_target() -> None:
    """Run as launchd would, in an environment built before imagewright."""
    code = (
        "import sys\n"
        "sys.modules['imagewright'] = None\n"
        "from gutenberg_kg.serve.image_server import main\n"
        "main()\n"
    )
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert result.returncode == 1
    assert "make image-server" in result.stderr
