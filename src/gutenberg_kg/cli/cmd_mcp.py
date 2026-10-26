"""``gutenkg mcp`` -- the fleet's standard MCP command, from :mod:`kg_utils.mcp`.

::

    gutenkg mcp [--repo DIR] [--db FILE] [--vectors FILE] [--model NAME]
                [--transport stdio|streamable-http] [--host H] [--port N]
                [--manifest]

``--repo`` is the GutenbergKG checkout; the bundle served defaults to
``bundles/gutenberg-all``. Registering the command imports neither ``mcp`` nor
the server module, so every other ``gutenkg`` command starts without them.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from kg_utils.mcp import add_mcp_command

from gutenberg_kg.cli.main import cli

if TYPE_CHECKING:
    from kg_utils.mcp import KGServer


def _build_server(repo: Path, db: Path | None, vectors: Path | None, model: str | None) -> KGServer:
    from gutenberg_kg.mcp_server import build_server  # noqa: PLC0415

    return build_server(repo, db, vectors, model)


mcp_command = add_mcp_command(cli, _build_server)
