"""GutenbergKG MCP Server.

Exposes image generation and corpus-grounded illustration tools.

Tools
-----
generate_image    — Direct text-to-image via local FLUX.2-Klein (no VLM planning).
corpus_imagine    — Query the corpus for context, then generate an image.

Run
---
  gutenkg-mcp          # stdio transport (Claude Code / Cursor)
"""

from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path

import structlog
from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from PIL import Image as PILImage

logger = structlog.get_logger()

mcp = FastMCP("GutenbergKG")

_ASPECT_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "3:2": (1536, 1024),
    "2:3": (1024, 1536),
    "16:9": (1536, 864),
    "9:16": (864, 1536),
    "4:3": (1365, 1024),
    "3:4": (1024, 1365),
}

_MAX_IMAGE_BYTES = 3_750_000


def _compress_for_mcp(pil_img: PILImage.Image, path: str) -> tuple[str, str]:
    """Save image; compress to JPEG if it exceeds the 5 MB MCP limit."""
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


@mcp.tool
async def generate_image(
    prompt: str,
    aspect_ratio: str = "3:2",
    seed: int | None = None,
    steps: int = 4,
) -> Image:
    """Generate an image directly from a text prompt using local FLUX.2-Klein on MLX.

    No VLM planning — fast direct generation (~20s on Apple Silicon).

    Args:
        prompt: Text description of the image to generate.
        aspect_ratio: 1:1, 3:2 (default landscape), 2:3, 16:9, 9:16, 4:3, 3:4.
        seed: Optional integer seed for reproducible outputs.
        steps: Inference steps — 4 (fast) to 25 (higher quality).

    Returns:
        The generated image.
    """
    from gutenberg_kg import image_gen

    logger.info("generate_image", prompt=prompt[:80], aspect_ratio=aspect_ratio, seed=seed)
    pil = await _run_sync(
        image_gen.generate, prompt, aspect_ratio=aspect_ratio, seed=seed, steps=steps
    )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        out_path = f.name
    effective_path, fmt = _compress_for_mcp(pil, out_path)
    return Image(path=effective_path, format=fmt)


@mcp.tool
async def corpus_imagine(
    query: str,
    book: str | None = None,
    extra_prompt: str | None = None,
    aspect_ratio: str = "3:2",
    seed: int | None = None,
    steps: int = 4,
) -> Image:
    """Query the Gutenberg corpus for context, then generate an illustration.

    Retrieves the most relevant chunks from the corpus (diaries, prose, etc.)
    for *query*, optionally filtered to *book*, combines them into an image
    prompt, and generates an image with FLUX.2-Klein.

    Args:
        query: What to search for in the corpus (e.g. "great fire of London").
        book: Optional book/author name substring to restrict the search
              (e.g. "pepys", "evelyn", "republic").
        extra_prompt: Additional style or scene instructions appended to the
                      corpus text (e.g. "oil painting, dramatic lighting").
        aspect_ratio: 1:1, 3:2 (default), 2:3, 16:9, 9:16, 4:3, 3:4.
        seed: Optional integer seed for reproducibility.
        steps: Inference steps — 4 (fast) to 25 (higher quality).

    Returns:
        The generated illustration.
    """
    from gutenberg_kg import image_gen
    from gutenberg_kg.cli.cmd_imagine import _query_corpus
    from gutenberg_kg.image_gen import vlm_rewrite

    corpus_text = _query_corpus(query, book)
    logger.info("corpus_imagine", query=query, book=book, corpus_chars=len(corpus_text))

    vlm_input = corpus_text
    if extra_prompt:
        vlm_input = f"{corpus_text}\n\nAdditional style/scene notes: {extra_prompt}"
    prompt, vlm_error = vlm_rewrite(vlm_input)
    if vlm_error:
        logger.warning("vlm_rewrite_failed", error=vlm_error)

    pil = await _run_sync(
        image_gen.generate, prompt, aspect_ratio=aspect_ratio, seed=seed, steps=steps
    )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        out_path = f.name
    effective_path, fmt = _compress_for_mcp(pil, out_path)
    return Image(path=effective_path, format=fmt)


async def _run_sync(fn, *args, **kwargs):
    """Run a blocking function in a thread so the event loop stays free."""
    import asyncio

    loop = asyncio.get_event_loop()
    import functools

    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
