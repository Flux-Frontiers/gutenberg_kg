# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""`gutenkg-sdxl-server`: an alias of ``imagewright serve --backend sdxl``.

The SDXL-Lightning server lives in imagewright, and `make sdxl-server` runs
``imagewright serve`` directly. This command is kept for one release and then
removed. See :mod:`gutenberg_kg.serve.image_server`.
"""

from __future__ import annotations

from gutenberg_kg.serve.image_server import serve_alias


def main() -> None:
    """Serve SDXL-Lightning through imagewright on ``SDXL_SERVER_HOST``:``SDXL_SERVER_PORT``."""
    serve_alias("gutenkg-sdxl-server", "sdxl", "SDXL_SERVER_HOST", "sdxl-server")


if __name__ == "__main__":
    main()
