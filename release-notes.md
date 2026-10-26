# Release Notes -- v1.30.0

> Released: 2026-10-26

Step 4 of the fleet's MCP centralization (kgrag_priv
`docs/MCP_CENTRALIZATION_PLAN.md`, sweep item 93), with this repo's LanceDB
paths removed. **Needs kgmodule-utils 0.29.0** (for `kg_utils.mcp`), **doc-kg
0.29.0** and **diary-kg 0.101.0**: the KG pins are kgmodule-utils 0.29.0,
doc-kg 0.29.0, diary-kg 0.101.0 and kg-rag 0.18.0, and the `mcp` extra takes
`kgmodule-utils[mcp]`.

### Changed

- **The MCP server is built on `kg_utils.mcp`**, off the standalone `fastmcp`
  package. It now serves the consolidated bundle (`bundles/gutenberg-all`)
  through the fleet's five canonical tools, under the same names as every
  other KG server (`stats`, `query`, `pack`, `get_node`, `neighbors`), with
  DocKG's own hybrid search behind `query` and `pack`, and keeps
  `generate_image` and `corpus_imagine` beside them. The tool list is
  generated from the tools, and `gutenkg mcp --manifest` prints it as JSON
  without opening the bundle. Each session prints the bundle it serves to
  stderr, and **a missing bundle is refused** (`no graph at ...`): build it
  with `gutenkg build-corpus` before serving, including to use the image tools.
- **The `stats` tool reports `kind: "gutenberg"`.** It returns the bundle
  DocKG's stats in the fleet shape (kgrag_priv `docs/FLEET_STANDARDS.md`,
  "KG stats shape") -- `nodes` / `edges` totals with their breakdowns by kind
  and relation, plus `vector_count` -- with `kind` set to the server's own
  kind rather than DocKG's `"doc"`.
- **`gutenkg mcp`** is the MCP command, with the fleet's standard flags
  (`--repo`, `--db`, `--vectors`, `--model`,
  `--transport stdio|streamable-http`, `--host`, `--port`, `--manifest`);
  `--db` defaults to `bundles/gutenberg-all/.dockg/graph.sqlite` under
  `--repo`. `gutenkg-mcp` is the same command. Registering it does not import
  `mcp`.
- The `mcp` extra is `mcp>=1.23.0,<2` and `structlog`; `fastmcp` and its 27
  dependencies are gone from the lock (closes MCP_MIGRATION Phase 4).
- `vector_store.resolve_vectors_path(store_dir)` replaces
  `resolve_vector_paths()`: it returns the `vectors.sqlite` file or `None`.

### Added

- **`docs/MCP.md`**, the MCP server guide (in the docs nav), and a README
  section pointing to it: configuration, options and the seven tools.

### Fixed

- **`make publish-worker-image` no longer leaves the replaced image on
  Docker Hub.** Each push moved `latest` and Docker Hub kept the previous
  image untagged, about 6 GB a publish (`corpus-gutenberg` had reached
  47.5 GB for one live image). The target now records the tag's digest
  before the push and, after it, deletes that image and its platform and
  attestation manifests with `scripts/prune_hub_image.py`, through the
  registry API, which refuses anything still referenced. It needs
  `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (a personal access token with
  Read, Write and Delete); without them the publish succeeds and says the
  old image was kept. Both runtimes' targets do this.
- **`gutenkg imagine --query` and the `corpus_imagine` tool** opened their
  DocKGs with `lancedb_dir=`, which doc-kg 0.29.0 refuses; a blanket `except`
  turned that into a silent fall back to the raw query, with no corpus text at
  all. They now pass `vectors_path=`, with a test.
- `runpod/handler.py` registered the consolidated DocKG and every diary with a
  `lancedb_path` even when only `vectors.sqlite` existed; it now registers
  `vectors_path`.

### Removed

- **LanceDB reading**, everywhere: the worker's `lancedb/` fallback in
  `serve/handler.py` and `runpod/handler.py` (the image never installed
  LanceDB, so it could not run), `export_swift`'s LanceDB reader and its dual
  `(vectors, lancedb)` lookup, and the registry's `lancedb_path` from ingest.
  `dockg_defect` now reports a LanceDB-only store as a defect, so ingest
  rebuilds it. `build-corpus` still deletes a stale `lancedb/` directory.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
