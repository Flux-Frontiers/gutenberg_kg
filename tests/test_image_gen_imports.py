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
