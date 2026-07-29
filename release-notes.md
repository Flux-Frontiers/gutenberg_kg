# Release Notes — v1.12.0

> Released: 2026-07-29

A dependency-hygiene release. GutenbergKG is the only KG in the family built on the
standalone `fastmcp` package rather than the SDK's bundled `mcp.server.fastmcp`, so it was
untouched by the mcp 2.0 breakage that hit its siblings. But its `fastmcp` requirement had
no upper bound at all, against a project that has already shipped two majors on its own
schedule. That is now bounded, and the floor moves up rather than down.

## What changed

**`fastmcp` bounded to `>=3.0,<4`.** The requirement was an unbounded `fastmcp>=2.0`, free
to cross a major version on any clean install. The obvious conservative fix would have been
to freeze at `<3` — but that assumption turned out to be wrong. The lock file already
resolves to fastmcp **3.4.4**, and the server imports and registers both tools cleanly
against it. Freezing at `<3` would have been a downgrade away from the known-good state
rather than a preservation of it, so the floor moved up instead. The generalizable lesson:
read the resolved lock, not the declared spec, before deciding which side of a major to
freeze on. The bound applies to both the `mcp` and `full` extras.

**Import-level MCP server tests.** `mcp_server.py` builds its `FastMCP` instance and
registers both tools at module import, so an incompatible major breaks `gutenkg-mcp` at
import time — invisibly to anyone with a pinned lock file. The new `tests/test_mcp_server.py`
skips cleanly when the `mcp` extra is absent, but **fails** rather than skips when `fastmcp`
is present at an incompatible major, which is the case worth catching.

**A snapshot-tracking bug fixed.** GutenbergKG's ignore rules carried a blanket
`**/.dockg/` pattern that swallowed the repository's own `.dockg/snapshots/` directory. The
result: every pre-commit run generated DocKG snapshots and then silently discarded them —
none were ever tracked. The ignore rules now follow one canonical form shared across all
eleven KG repos, written so the ~250 per-book stores under `corpus/` stay fully ignored
while root-level `snapshots/` is tracked.

**`serve/sdxl_server.py` imports cleanly in the main environment** again.

## Upgrading

If you install the `mcp` or `full` extras and had pinned `fastmcp` to a 2.x release, you
will need to move to 3.x. Everything else is unchanged — no rebuild, no migration, no API
change to the corpus tooling.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
