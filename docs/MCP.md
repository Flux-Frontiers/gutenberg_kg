# MCP server

`gutenkg mcp` serves the corpus to an AI agent over the Model Context Protocol:
Claude Code, Cursor, GitHub Copilot or any other MCP client. It is built on the
fleet's shared server base, `kg_utils.mcp`, so its first five tools have the
same names and arguments as every other Flux-Frontiers KG server.

The server reads the consolidated bundle, `bundles/gutenberg-all`, which
`gutenkg build-corpus` builds. Build it first: a missing bundle is refused at
session start rather than served empty, and that includes the image tools.

## Install and configure

The server needs the `mcp` extra, which brings the MCP SDK through
`kgmodule-utils[mcp]`:

```bash
poetry install --extras mcp
```

Add it to the client's MCP configuration, such as `.mcp.json` in the repo
root:

```json
{
  "mcpServers": {
    "gutenkg": {
      "command": "/path/to/repo/.venv/bin/gutenkg",
      "args": ["mcp", "--repo", "/path/to/repo"]
    }
  }
}
```

`gutenkg-mcp` is the same command under its older name.

| Option | Meaning |
|---|---|
| `--repo DIRECTORY` | Repository root. Default `.` |
| `--db PATH` | Graph database. Default `bundles/gutenberg-all/.dockg/graph.sqlite` under `--repo` |
| `--vectors PATH` | Vector store. Default the `vectors.sqlite` beside `--db` |
| `--model NAME` | Embedding model. Default DocKG's default model |
| `--transport [stdio\|streamable-http]` | MCP transport. Default `stdio` |
| `--host`, `--port` | Bind address for `streamable-http`. Default `127.0.0.1:8765` |
| `--manifest` | Print the tools as JSON and exit, without opening the bundle |

A relative `--db` or `--vectors` is taken from `--repo`.

## Tools

| Tool | Returns |
|---|---|
| `stats()` | Node and edge counts for the bundle, by kind and relation, plus its vector count, in the fleet stats shape with `kind: "gutenberg"` |
| `query(q, k, hop, max_nodes, rels)` | Hybrid search: ranked sections, chunks and topics, and the edges among them |
| `pack(q, k, hop, max_nodes, rels, max_chars, traced)` | The same search as a Markdown pack of text excerpts, ready to read |
| `get_node(node_id)` | One node with its kind, location, docstring and metadata |
| `neighbors(node_id, rels, direction, limit)` | A node's edges and the nodes at their far ends |
| `generate_image(prompt, size, seed, steps)` | An image from a text prompt, on the running image server |
| `corpus_imagine(query, book, extra_prompt, size, seed, steps)` | Search the corpus for a scene (diaries first, then the books) and illustrate it |

`query` and `pack` are DocKG's own hybrid search over the bundle. The image
tools call a running image server and never load a model themselves; start one
with `make up`, and see the
[image-generation cheatsheet](CHEATSHEET.md#corpus-grounded-image-generation)
for the endpoints and options.

The server's instructions are generated from the tools' docstrings, so
`gutenkg mcp --manifest` is the authoritative list. Each session opens the
bundle when it starts, prints the paths it serves to stderr, and closes the
bundle when it ends.
