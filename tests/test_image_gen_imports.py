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


_SERVERS_WITHOUT_IMAGEWRIGHT = (
    "import sys\n"
    "sys.modules['kg_utils'] = None\n"
    "sys.modules['imagewright'] = None\n"
    "import gutenberg_kg.image_gen\n"
    "import gutenberg_kg.serve.image_server as server\n"
    "assert callable(server.main)\n"
    "import gutenberg_kg.serve.sdxl_server as sdxl\n"
    "assert callable(sdxl.main)\n"
)


def test_the_image_servers_import_without_imagewright() -> None:
    """The image servers must start in a venv that predates imagewright.

    `.venv-image` is an editable install without this package's dependencies,
    kept alive by launchd, so a `git pull` changes the code it runs before
    anyone refreshes it. The client half of image_gen uses imagewright; the
    server half must not, and importing a server must not pull it in.
    """
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    env.pop("IMAGE_PRELOAD", None)
    result = subprocess.run(
        [sys.executable, "-c", _SERVERS_WITHOUT_IMAGEWRIGHT],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
