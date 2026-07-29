"""
test_mcp_server.py

Import-level regression tests for gutenberg_kg.mcp_server.

The MCP server builds its ``FastMCP`` instance and registers both tools with
module-level decorators, so an incompatible ``fastmcp`` release breaks it at
*import* time rather than at call time — and only for people who installed
from PyPI, since a developer's pinned lock file keeps working.

GutenbergKG is the one repo in the family on the standalone ``fastmcp``
package rather than the SDK's bundled ``mcp.server.fastmcp``, so it dodged the
mcp 2.0 break — but it tracks a project that has already shipped 2.x and 3.x
on its own schedule. `pyproject.toml` bounds it to ``>=3.0,<4``; these tests
fail loudly if that ceiling is lifted without verifying the next major.

``fastmcp`` lives in the ``mcp`` extra, so these skip when it is absent
entirely. They still fail — rather than skip — when it is installed at an
incompatible major, which is the case that matters.

Ported from pycode_kg's ``tests/test_mcp_server.py``.
"""

from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastmcp", reason="MCP server requires the mcp extra (fastmcp)")


def test_server_module_imports():
    """The module must import cleanly against the installed fastmcp release."""
    importlib.import_module("gutenberg_kg.mcp_server")


def test_fastmcp_import_paths_exist():
    """The names the server imports must exist on the installed fastmcp.

    Asserted directly so the failure names the actual incompatibility rather
    than surfacing as an opaque ImportError from our own module.
    """
    fastmcp = importlib.import_module("fastmcp")
    assert hasattr(fastmcp, "FastMCP")
    types = importlib.import_module("fastmcp.utilities.types")
    assert hasattr(types, "Image")


def test_entry_point_target_exists():
    """``gutenkg-mcp`` resolves to gutenberg_kg.mcp_server:main."""
    server = importlib.import_module("gutenberg_kg.mcp_server")
    assert callable(server.main)


def test_tools_are_registered():
    """The tool list survives registration and covers the documented surface."""
    server = importlib.import_module("gutenberg_kg.mcp_server")
    names = {t.name for t in _list_tools(server)}
    assert names == {"corpus_imagine", "generate_image"}


def test_tool_count_matches_documented_surface():
    """The server advertises 2 tools, as stated in the README and MCP docs."""
    server = importlib.import_module("gutenberg_kg.mcp_server")
    assert len(_list_tools(server)) == 2


def _list_tools(server):
    """Return the registered FastMCP tools.

    ``FastMCP.list_tools()`` is async; run it on a private loop rather than
    depending on an async test plugin.
    """
    import asyncio

    return asyncio.run(server.mcp.list_tools())
