"""
test_mcp_server.py

The GutenbergKG MCP server on the fleet's shared base, ``kg_utils.mcp``.

What step 4 of kgrag_priv's MCP centralization plan promises: off the
standalone ``fastmcp`` package; the five canonical tools over the consolidated
bundle's DocKG, then ``generate_image`` and ``corpus_imagine``; ``stats``,
``get_node`` and ``neighbors`` never load the model; the manifest answers
without a bundle; ``gutenkg``'s other commands do not import ``mcp``; a
missing bundle is refused; and a real stdio subprocess serves.

The bundle is a four-node graph written straight into DocKG's store; the image
server and the VLM are stubbed, so nothing is downloaded or generated.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import anyio
import pytest

pytest.importorskip("mcp", reason="MCP server requires the mcp extra")

from click.testing import CliRunner  # noqa: E402
from doc_kg.dockg import DocEdge, DocNode  # noqa: E402
from doc_kg.store import GraphStore  # noqa: E402
from kg_utils.mcp import CANONICAL_TOOLS, manifest  # noqa: E402
from kg_utils.stats import stats_problems  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

import gutenberg_kg  # noqa: E402
from gutenberg_kg import mcp_server  # noqa: E402
from gutenberg_kg.cli.main import cli  # noqa: E402

_SRC = str(Path(gutenberg_kg.__file__).resolve().parents[1])
_EXTRAS = ["generate_image", "corpus_imagine"]


def _node(nid: str, kind: str, **kw) -> DocNode:
    return DocNode(
        id=nid,
        kind=kind,
        name=nid,
        title=kw.get("title"),
        file_path="poetry/Inferno.md",
        char_start=0,
        char_end=10,
        heading_level=None,
        text=kw.get("text", nid),
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A checkout whose default bundle holds one book: doc → section → two chunks."""
    (tmp_path / "corpus").mkdir()
    store = GraphStore(tmp_path / "bundles" / "gutenberg-all" / ".dockg" / "graph.sqlite")
    store.write(
        [
            _node("doc:poetry/Inferno.md", "document", title="Inferno"),
            _node("sec:poetry/Inferno.md:canto-1", "section", title="Canto I"),
            _node("chunk:poetry/Inferno.md:0000", "chunk", text="Midway upon the journey"),
            _node("chunk:poetry/Inferno.md:0001", "chunk", text="a dark wood"),
        ],
        [
            DocEdge(
                src="doc:poetry/Inferno.md", rel="CONTAINS", dst="sec:poetry/Inferno.md:canto-1"
            ),
            DocEdge(
                src="sec:poetry/Inferno.md:canto-1",
                rel="CONTAINS",
                dst="chunk:poetry/Inferno.md:0000",
            ),
            DocEdge(
                src="chunk:poetry/Inferno.md:0000", rel="NEXT", dst="chunk:poetry/Inferno.md:0001"
            ),
        ],
        quiet=True,
    )
    store.close()
    return tmp_path


def _session(server, fn):
    async def main():
        async with create_connected_server_and_client_session(server) as client:
            return await fn(client)

    return anyio.run(main)


@pytest.fixture
def stub_images(monkeypatch):
    """A tiny image from a fake image server; the VLM returns its input."""
    from PIL import Image as PILImage

    from gutenberg_kg import image_gen

    prompts: list[str] = []

    def generate(prompt, **_kw):
        prompts.append(prompt)
        return PILImage.new("RGB", (8, 8), "navy")

    monkeypatch.setenv("GUTENKG_IMAGE_ENDPOINT", "http://image.test")
    monkeypatch.setattr(image_gen, "generate_via_server", generate)
    monkeypatch.setattr(image_gen, "vlm_rewrite", lambda text: (f"VLM: {text}", None))
    monkeypatch.setattr(
        "gutenberg_kg.cli.cmd_imagine._query_corpus", lambda q, book: f"corpus for {q} in {book}"
    )
    return prompts


# ---------------------------------------------------------------------------
# The tool surface
# ---------------------------------------------------------------------------


def test_no_standalone_fastmcp():
    """Step 4: the server is on the SDK's FastMCP via kg_utils.mcp, not `fastmcp`."""
    source = Path(mcp_server.__file__).read_text(encoding="utf-8")
    assert "import fastmcp" not in source and "from fastmcp" not in source


def test_canonical_tools_then_the_image_tools(tmp_path):
    names = [t["name"] for t in manifest(mcp_server.build_server(tmp_path))["tools"]]
    assert names == [*CANONICAL_TOOLS, *_EXTRAS]


def test_graph_tools_answer_without_a_model(repo, monkeypatch):
    def refuse(*_a, **_k):
        raise RuntimeError("embedding model load refused by test")

    monkeypatch.setattr("doc_kg.kg.make_embedder", refuse)

    async def calls(client: ClientSession):
        return (
            await client.call_tool("stats", {}),
            await client.call_tool("get_node", {"node_id": "sec:poetry/Inferno.md:canto-1"}),
            await client.call_tool(
                "neighbors", {"node_id": "chunk:poetry/Inferno.md:0000", "rels": ["NEXT"]}
            ),
            await client.call_tool("query", {"q": "dark wood"}),
        )

    stats, node, near, query = _session(mcp_server.build_server(repo), calls)
    assert not stats.isError and stats_problems(stats.structuredContent) == []
    assert stats.structuredContent["kind"] == "gutenberg"
    assert stats.structuredContent["nodes"]["total"] == 4
    assert not node.isError and node.structuredContent["title"] == "Canto I"
    assert [n["id"] for n in near.structuredContent["nodes"]] == ["chunk:poetry/Inferno.md:0001"]
    assert query.isError and "embedding model load refused by test" in query.content[0].text


def test_image_tools_return_images(repo, stub_images):
    async def calls(client: ClientSession):
        return (
            await client.call_tool("generate_image", {"prompt": "a dark wood"}),
            await client.call_tool(
                "corpus_imagine", {"query": "dark wood", "book": "inferno", "extra_prompt": "ink"}
            ),
        )

    direct, grounded = _session(mcp_server.build_server(repo), calls)
    assert not direct.isError and direct.content[0].type == "image"
    assert not grounded.isError and grounded.content[0].type == "image"
    assert stub_images == [
        "a dark wood",
        "VLM: corpus for dark wood in inferno\n\nAdditional style/scene notes: ink",
    ]


def test_a_missing_bundle_is_refused(tmp_path):
    with pytest.raises(BaseException) as info:  # noqa: PT011 -- ExceptionGroup from the task group
        _session(mcp_server.build_server(tmp_path), lambda c: c.call_tool("stats", {}))
    assert "no graph at" in repr(info.value) or any(
        "no graph at" in str(e) for e in getattr(info.value, "exceptions", ())
    )


def test_query_corpus_opens_stores_by_vectors_path(tmp_path, monkeypatch):
    """`gutenkg imagine` used to pass lancedb_dir=, which doc-kg 0.29.0 refuses;
    its blanket except turned that into a silent fall back to the raw query."""
    import doc_kg

    from gutenberg_kg.cli import cmd_imagine

    opened: list[dict] = []

    class _Recorder:
        def __init__(self, **kwargs):
            opened.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def query(self, *_a, **_k):
            class _R:
                nodes = [{"text": "x" * 50, "file_path": "poetry/Inferno.md"}]

            return _R()

    monkeypatch.setattr(doc_kg, "DocKG", _Recorder)
    monkeypatch.setattr(cmd_imagine, "__file__", str(tmp_path / "src" / "pkg" / "cli" / "f.py"))
    (tmp_path / "bundles" / "gutenberg-all" / ".dockg").mkdir(parents=True)
    assert cmd_imagine._query_corpus("wood", None) == "x" * 50
    assert opened and "lancedb_dir" not in opened[0]
    assert opened[0]["vectors_path"].endswith("vectors.sqlite")


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def test_manifest_answers_without_a_bundle_and_creates_nothing(tmp_path):
    result = CliRunner().invoke(cli, ["mcp", "--repo", str(tmp_path), "--manifest"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["canonical"] == list(CANONICAL_TOOLS)
    assert list(tmp_path.iterdir()) == []


def test_sse_is_refused(tmp_path):
    result = CliRunner().invoke(cli, ["mcp", "--repo", str(tmp_path), "--transport", "sse"])
    assert result.exit_code == 2


def test_other_commands_do_not_import_mcp():
    out = subprocess.run(
        [sys.executable, "-c", "import sys, gutenberg_kg.cli.main; print('mcp' in sys.modules)"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert out == "False"


def test_stdio_subprocess_serves(repo, tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from gutenberg_kg.mcp_server import main; main()", "--repo", str(repo)],
        env={**os.environ, "PYTHONPATH": _SRC},
    )

    async def run():
        with open(tmp_path / "stderr.log", "w", encoding="utf-8") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as client:
                    init = await client.initialize()
                    tools = await client.list_tools()
                    stats = await client.call_tool("stats", {})
                    return init, tools, stats

    init, tools, stats = anyio.run(run)
    assert (init.serverInfo.name, init.serverInfo.version) == ("gutenkg", gutenberg_kg.__version__)
    assert [t.name for t in tools.tools] == [*CANONICAL_TOOLS, *_EXTRAS]
    assert stats.structuredContent["nodes"]["total"] == 4
    err = (tmp_path / "stderr.log").read_text(encoding="utf-8")
    assert "gutenkg MCP server starting (stdio)" in err
    assert "bundles/gutenberg-all/.dockg/graph.sqlite" in err
