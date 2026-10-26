"""GutenbergKG MCP Server.

Serves the consolidated corpus bundle's DocKG over the fleet's shared server
base, :mod:`kg_utils.mcp`, with GutenbergKG's illustration tools beside it.

Tools
-----
stats, query, pack, get_node, neighbors
    The fleet's five canonical tools, under the same names as every other KG
    server, over ``bundles/gutenberg-all`` (books, verse and their sections).
    ``query`` and ``pack`` are DocKG's own hybrid dense + BM25 search.
generate_image
    Direct text-to-image on a running image server (no VLM planning).
corpus_imagine
    Query the corpus — diaries first, then the books — for context, then
    generate an illustration.

The image tools call an image server over HTTP -- the one
GUTENKG_IMAGE_ENDPOINT names, or the first of
``image_gen.DEFAULT_IMAGE_ENDPOINTS`` that answers (``make up`` starts one).
They never load a model in-process: mflux is not a dependency of this package.

Run
---
::

  gutenkg mcp                      # stdio transport (Claude Code / Cursor)
  gutenkg mcp --manifest           # the tool list as JSON, without opening the graph

``gutenkg-mcp`` is the same command. ``--repo`` is the GutenbergKG checkout;
``--db`` and ``--vectors`` default to ``bundles/gutenberg-all/.dockg/``.
"""

from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

# At module scope: FastMCP evaluates the tools' annotations when it registers
# them. Only build_server() imports this module, so other gutenkg commands
# still start without mcp.
from kg_utils.mcp import Context, kg_from
from mcp.server.fastmcp import Image

if TYPE_CHECKING:
    from kg_utils.mcp import KGServer
    from PIL import Image as PILImage

#: The bundle served when ``--db`` is not given.
DEFAULT_BUNDLE = Path("bundles") / "gutenberg-all"

PREAMBLE = (
    "GutenbergKG is a knowledge graph of Project Gutenberg and Internet Archive "
    "books: documents ('doc:<genre>/<book>/...'), their sections and chunks, and "
    "the topics, entities and keywords drawn from them. Edges: CONTAINS, NEXT, "
    "REFERENCES, SIMILAR_TO, HAS_TOPIC, MENTIONS_ENTITY, HAS_KEYWORD, "
    "CO_OCCURS_WITH.\n\n"
    "## Recommended workflows\n\n"
    "- **Orientation**: stats\n"
    "- **Find passages**: query → get_node; pack for the text itself\n"
    "- **Read around a passage**: neighbors(node_id, rels=['NEXT'])\n"
    "- **Illustrate**: corpus_imagine for a scene grounded in the corpus "
    "(diaries first); generate_image for a prompt of your own. Both need a "
    "running image server."
)

_MAX_IMAGE_BYTES = 3_750_000


def stats(*, ctx: Context) -> dict[str, Any]:
    """
    Node and edge counts for the corpus bundle, in total and by kind and relation, plus its vector count.
    """
    return {**kg_from(ctx).stats(), "kind": "gutenberg"}


def _compress_for_mcp(pil_img: PILImage.Image, path: str) -> tuple[str, str]:
    """Save image; compress to JPEG if it exceeds the 5 MB MCP limit."""
    from PIL import Image as PILImage  # noqa: PLC0415

    pil_img.save(path)
    size = Path(path).stat().st_size
    if size <= _MAX_IMAGE_BYTES:
        return path, "png"

    # Re-save as JPEG at progressively lower quality
    jpg_path = path.replace(".png", ".jpg")
    for quality in (85, 70, 50):
        buf = BytesIO()
        pil_img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= _MAX_IMAGE_BYTES:
            Path(jpg_path).write_bytes(buf.getvalue())
            return jpg_path, "jpeg"

    # Last resort: scale down
    for scale in (0.75, 0.5):
        small = pil_img.resize(
            (int(pil_img.width * scale), int(pil_img.height * scale)),
            PILImage.Resampling.LANCZOS,
        )
        buf = BytesIO()
        small.convert("RGB").save(buf, format="JPEG", quality=70, optimize=True)
        if buf.tell() <= _MAX_IMAGE_BYTES:
            Path(jpg_path).write_bytes(buf.getvalue())
            return jpg_path, "jpeg"

    raise ValueError("Image could not be compressed below the 5 MB MCP limit.")


def _as_mcp_image(pil: PILImage.Image) -> Image:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        out_path = f.name
    effective_path, fmt = _compress_for_mcp(pil, out_path)
    return Image(path=effective_path, format=fmt)


def _logger():
    import structlog  # noqa: PLC0415

    return structlog.get_logger()


async def generate_image(
    prompt: str,
    size: str = "1536x1024",
    seed: int | None = None,
    steps: int = 4,
) -> Image:
    """
    Generate an image from a text prompt on the running image server, with no VLM planning.

    :param prompt: Text description of the image to generate.
    :param size: Output size "WIDTHxHEIGHT" (default landscape 1536x1024).
    :param seed: Optional integer seed for reproducible outputs.
    :param steps: Inference steps — 4 (fast) to 25 (higher quality).
    """
    from gutenberg_kg import image_gen  # noqa: PLC0415

    _logger().info("generate_image", prompt=prompt[:80], size=size, seed=seed)
    pil = await _run_sync(
        image_gen.generate_via_server,
        prompt,
        server_url=_image_endpoint(),
        size=size,
        seed=seed,
        steps=steps,
    )
    return _as_mcp_image(pil)


async def corpus_imagine(
    query: str,
    book: str | None = None,
    extra_prompt: str | None = None,
    size: str = "1536x1024",
    seed: int | None = None,
    steps: int = 4,
) -> Image:
    """
    Search the corpus for a scene (diaries first, then the books), then illustrate it.

    The matching passages are rewritten into an image prompt by the local VLM
    and generated on the running image server.

    :param query: What to search for, e.g. "great fire of London".
    :param book: Optional book or author name substring to search within, e.g. "pepys".
    :param extra_prompt: Style or scene notes appended to the corpus text, e.g. "oil painting".
    :param size: Output size "WIDTHxHEIGHT" (default landscape 1536x1024).
    :param seed: Optional integer seed for reproducibility.
    :param steps: Inference steps — 4 (fast) to 25 (higher quality).
    """
    from gutenberg_kg import image_gen  # noqa: PLC0415
    from gutenberg_kg.cli.cmd_imagine import _query_corpus  # noqa: PLC0415
    from gutenberg_kg.image_gen import vlm_rewrite  # noqa: PLC0415

    corpus_text = _query_corpus(query, book)
    log = _logger()
    log.info("corpus_imagine", query=query, book=book, corpus_chars=len(corpus_text))

    vlm_input = corpus_text
    if extra_prompt:
        vlm_input = f"{corpus_text}\n\nAdditional style/scene notes: {extra_prompt}"
    prompt, vlm_error = vlm_rewrite(vlm_input)
    if vlm_error:
        log.warning("vlm_rewrite_failed", error=vlm_error)

    pil = await _run_sync(
        image_gen.generate_via_server,
        prompt,
        server_url=_image_endpoint(),
        size=size,
        seed=seed,
        steps=steps,
    )
    return _as_mcp_image(pil)


EXTRA_TOOLS = (generate_image, corpus_imagine)


def _image_endpoint() -> str:
    """Resolve the image server to call, as ``gutenkg imagine`` does.

    :return: GUTENKG_IMAGE_ENDPOINT if set, else the first default endpoint
        that answers.
    :raises RuntimeError: When no image server is configured or running.
    """
    from gutenberg_kg import image_gen  # noqa: PLC0415

    endpoint = os.environ.get("GUTENKG_IMAGE_ENDPOINT") or image_gen.discover_image_endpoint()
    if not endpoint:
        probed = ", ".join(image_gen.DEFAULT_IMAGE_ENDPOINTS)
        raise RuntimeError(
            "No image server found. Start one with `make up`, or set "
            f"GUTENKG_IMAGE_ENDPOINT to a running one. Probed: {probed}"
        )
    return endpoint


async def _run_sync(fn, *args, **kwargs):
    """Run a blocking function in a thread so the event loop stays free."""
    import asyncio  # noqa: PLC0415
    import functools  # noqa: PLC0415

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


def build_server(
    repo: str | Path,
    db: str | Path | None = None,
    vectors: str | Path | None = None,
    model: str | None = None,
) -> KGServer:
    """Build the GutenbergKG MCP server, without opening the bundle's graph.

    :param repo: The GutenbergKG checkout; its ``corpus/`` is the corpus root.
    :param db: Bundle graph; ``None`` for ``<repo>/bundles/gutenberg-all/.dockg/graph.sqlite``.
    :param vectors: Bundle vectors; ``None`` for the ``vectors.sqlite`` beside *db*.
    :param model: Embedding model; ``None`` for DocKG's default.
    :return: The server; serve it with :func:`kg_utils.mcp.run`.
    """
    from doc_kg import DocKG  # noqa: PLC0415
    from doc_kg.dockg import DEFAULT_MODEL  # noqa: PLC0415
    from doc_kg.mcp_server import pack, query  # noqa: PLC0415
    from kg_utils.mcp import make_server  # noqa: PLC0415

    from gutenberg_kg import __version__  # noqa: PLC0415

    root = Path(repo).resolve()
    db_path = Path(db) if db else root / DEFAULT_BUNDLE / ".dockg" / "graph.sqlite"
    vectors_path = Path(vectors) if vectors else db_path.parent / "vectors.sqlite"

    def open_kg() -> DocKG:
        return DocKG(root / "corpus", db_path, vectors_path, model=model or DEFAULT_MODEL)

    server = make_server(
        open_kg, name="gutenkg", kind="gutenberg", version=__version__, instructions=PREAMBLE
    )
    server.canonical("stats")(stats)
    server.canonical("query")(query)
    server.canonical("pack")(pack)
    for tool in EXTRA_TOOLS:
        server.tool()(tool)
    return server


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``gutenkg-mcp``: the same command as ``gutenkg mcp``.

    :param argv: Arguments; ``None`` for ``sys.argv[1:]``.
    """
    from gutenberg_kg.cli.cmd_mcp import mcp_command  # noqa: PLC0415

    mcp_command.main(args=argv, prog_name="gutenkg-mcp")


if __name__ == "__main__":
    main()
