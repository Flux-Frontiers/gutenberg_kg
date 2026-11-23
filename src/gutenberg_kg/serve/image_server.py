# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""`gutenkg-image-server`: an alias of ``imagewright serve --backend flux``.

The FLUX server lives in imagewright. `make image-server` and the LaunchAgent
that `make image-agent-install` writes run ``imagewright serve`` directly.
This command is kept for one release so a LaunchAgent installed before that
keeps starting its server, and is then removed.

It binds all interfaces unless ``MFLUX_SERVER_HOST`` says otherwise, as this
command always has; ``imagewright serve`` on its own binds 127.0.0.1. Every
other setting is imagewright's: see ``imagewright.flux_server``.

Nothing is imported at module scope beyond the standard library. The command
runs from `.venv-image`, an editable install without this package's
dependencies, and a module-level import there once kept the server from
starting (2026-11-17).
"""

from __future__ import annotations

import os
import sys


def serve_alias(command: str, backend: str, host_variable: str, make_target: str) -> None:
    """Run ``imagewright serve`` for one of this repo's two server commands.

    :param command: The command being run, for messages.
    :param backend: ``flux`` or ``sdxl``.
    :param host_variable: Environment variable that names the bind address.
    :param make_target: The make target that builds this server's environment.
    """
    try:
        from imagewright.cli import cli  # noqa: PLC0415 - absent from an old environment
    except ImportError as exc:
        sys.exit(
            f"{command}: this environment has no imagewright ({exc}). "
            f"Run `make {make_target}` to rebuild it."
        )
    os.environ.setdefault(host_variable, "0.0.0.0")
    print(
        f"[startup] {command} is an alias of `imagewright serve --backend {backend}` "
        "and goes away in the next release",
        flush=True,
    )
    cli(["serve", "--backend", backend], prog_name="imagewright")


def main() -> None:
    """Serve FLUX through imagewright on ``MFLUX_SERVER_HOST``:``MFLUX_SERVER_PORT``."""
    serve_alias("gutenkg-image-server", "flux", "MFLUX_SERVER_HOST", "image-server")


if __name__ == "__main__":
    main()
