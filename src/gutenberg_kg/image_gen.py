"""Image generation through an image server, and the scene rewrite before it.

  generate_via_server()      HTTP call to a running image server
  discover_image_endpoint()  find one that is up on this machine
  vlm_rewrite()              turn corpus text into an image prompt

The servers themselves are imagewright's (``imagewright serve``); `make
image-server` and `make sdxl-server` start them. This module is the client
side only and loads no model.

Environment variables
---------------------
GUTENKG_IMAGE_STEPS      Inference steps (default: 4)
GUTENKG_IMAGE_SIZE       Default output size WIDTHxHEIGHT (default: 1536x1024)
GUTENKG_IMAGE_ENDPOINT   Base URL of a running image server, read by the
                         callers of this module (`gutenkg imagine`, the MCP
                         image tools). Example: http://localhost:8090
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

_DEFAULT_STEPS = 4
_DEFAULT_SIZE = "1536x1024"
_DEFAULT_DIMS = (1536, 1024)


def _parse_size(size: str | None) -> tuple[int, int] | None:
    """Parse an explicit ``"WIDTHxHEIGHT"`` string into an ``(width, height)`` pair.

    :param size: Size string such as ``"768x512"`` (case-insensitive ``x``), or None.
    :returns: ``(width, height)`` when *size* parses to two positive ints, else None.
    """
    if not size:
        return None
    try:
        w_str, h_str = size.lower().split("x", 1)
        width, height = int(w_str), int(h_str)
    except (ValueError, AttributeError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


_DEFAULT_VLM_BASE_URL = "http://localhost:8080/v1"

#: Endpoints probed when nothing is configured, in preference order — the two
#: ports `make up` actually binds: FLUX/mflux on 8090, SDXL-Lightning on 8091.
#: Which one is running depends on the host, and the Makefile already picks
#: between them, so asking the user to name a port they did not choose is
#: friction over a fact the machine can establish in a few milliseconds.
DEFAULT_IMAGE_ENDPOINTS: tuple[str, ...] = (
    "http://localhost:8090",
    "http://localhost:8091",
)


def discover_image_endpoint(
    candidates: tuple[str, ...] = DEFAULT_IMAGE_ENDPOINTS,
    timeout: float = 1.5,
) -> str | None:
    """
    Find a local image server that is actually up.

    Tries ``/health`` first and falls back to ``/v1/models``.  imagewright's
    servers answer both, but a third-party mflux-serve will only answer the
    model listing.  Falling back costs one extra request against a port that
    is live either way.

    A connection refused, a timeout, or any non-200 all mean "not this one".

    :param candidates: Base URLs to try, in order.
    :param timeout: Per-candidate timeout in seconds.
    :return: The first responding base URL, or None if none answered.
    """
    # Imported here, not at module level, so importing this module stays cheap.
    from imagewright import discover_image_endpoint as _discover

    return _discover(candidates, timeout)


_DEFAULT_VLM_MODEL = "Qwen3-8B-MLX-4bit"


def vlm_rewrite(
    corpus_text: str,
    *,
    base_url: str | None = None,
    model: str | None = None,
) -> tuple[str, str | None]:
    """Rewrite corpus prose into a visual image-generation prompt via a local VLM.

    :param corpus_text: Historical text to rewrite as a visual scene description.
    :param base_url: OpenAI-compatible endpoint URL. Falls back to GUTENKG_VLM_ENDPOINT
                     or http://localhost:8080/v1.
    :param model: Model ID. Falls back to GUTENKG_VLM_MODEL or _DEFAULT_VLM_MODEL.
    :returns: (prompt, error) — prompt is the rewritten text (or corpus_text on failure);
              error is None on success or a short message describing the failure.
    """
    import re

    # Imported here, not at module level, so importing this module stays cheap.
    # One prompt for every rewrite path: the worker's, this CLI/MCP one,
    # and the app's Swift mirror (test_synthesis_parity.py).
    from gutenberg_kg.synthesis_prompts import IMAGE_REWRITE_SYSTEM

    try:
        from openai import OpenAI
    except ImportError:
        return corpus_text, "openai package not installed"

    url = base_url or os.environ.get("GUTENKG_VLM_ENDPOINT", _DEFAULT_VLM_BASE_URL)
    mdl = model or os.environ.get("GUTENKG_VLM_MODEL", _DEFAULT_VLM_MODEL)

    try:
        client = OpenAI(base_url=url, api_key="not-needed")
        response = client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": IMAGE_REWRITE_SYSTEM},
                {"role": "user", "content": corpus_text},
            ],
            max_tokens=300,
            temperature=0.7,
            extra_body={"think": False, "chat_template_kwargs": {"enable_thinking": False}},
        )
        raw = (response.choices[0].message.content or "").strip()
        # Strip any <think>…</think> blocks the model emitted despite being asked not to.
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        return (cleaned or corpus_text), None
    except Exception as exc:  # noqa: BLE001
        return corpus_text, str(exc)


def generate_via_server(
    prompt: str,
    *,
    server_url: str,
    size: str | None = None,
    seed: int | None = None,
    steps: int | None = None,
) -> PILImage:
    """Generate an image by calling a running mflux-serve HTTP server.

    The request goes through imagewright's client, which needs only httpx and
    pillow, so this is safe to call from a Linux container or any environment
    without mflux installed.

    :param prompt: Text description of the image to generate.
    :param server_url: Base URL of the mflux-serve instance, e.g. http://localhost:8088.
    :param size: Output size ``"WIDTHxHEIGHT"`` (default: GUTENKG_IMAGE_SIZE or 1536x1024).
    :param seed: Optional integer seed for reproducibility.
    :param steps: Override inference steps (default: GUTENKG_IMAGE_STEPS or 4).
    :returns: PIL Image decoded from the server response.
    """
    # Imported here, not at module level: see discover_image_endpoint.
    from imagewright import ImageBackend, ImageConfig, ImageSynthesizer

    steps = steps or int(os.environ.get("GUTENKG_IMAGE_STEPS", _DEFAULT_STEPS))
    size = size or os.environ.get("GUTENKG_IMAGE_SIZE", _DEFAULT_SIZE)
    width, height = _parse_size(size) or _DEFAULT_DIMS

    client = ImageSynthesizer(
        ImageConfig(backend=ImageBackend.MFLUX_SERVE, server_url=server_url, steps=steps)
    )
    return client.generate(prompt, size=f"{width}x{height}", seed=seed, steps=steps)
