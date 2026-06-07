"""Image generation — local MLX or remote mflux-serve.

Two code paths:
  generate()            — local Flux2Klein via mflux (Apple Silicon only)
  generate_via_server() — HTTP call to a running mflux-serve instance
  generate_auto()       — server if GUTENKG_IMAGE_ENDPOINT / server_url set,
                          else local fallback

Environment variables
---------------------
GUTENKG_IMAGE_MODEL      HuggingFace repo or mflux model name
                         (default: mlx-community/flux2-klein-4b-4bit)
GUTENKG_IMAGE_STEPS      Inference steps (default: 4)
GUTENKG_IMAGE_ENDPOINT   Base URL of a running mflux-serve instance
                         (default: empty — use local generation)
                         Example: http://localhost:8090  (mflux-server default)
"""

from __future__ import annotations

import base64
import os
import random
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

_DEFAULT_MODEL = "mlx-community/flux2-klein-4b-4bit"
_DEFAULT_STEPS = 4

_ASPECT_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "3:2": (1536, 1024),
    "2:3": (1024, 1536),
    "16:9": (1536, 864),
    "9:16": (864, 1536),
    "4:3": (1365, 1024),
    "3:4": (1024, 1365),
}

_DEFAULT_VLM_BASE_URL = "http://localhost:8080/v1"
_DEFAULT_VLM_MODEL = "Qwen3-4B-Instruct-2507-MLX-8bit"

_VLM_SYSTEM = (
    "You are an expert art director. Given a passage of historical text, write a single concise "
    "image generation prompt (one paragraph, no bullet points, no quotation marks) that vividly "
    "describes the scene for a text-to-image model. Focus on visual elements: setting, lighting, "
    "figures, mood, and artistic style. Do NOT include any text, labels, captions, or words in "
    "the scene description. Output ONLY the prompt, nothing else."
)


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
    :param model: Model ID. Falls back to GUTENKG_VLM_MODEL or the Qwen3-30B default.
    :returns: (prompt, error) — prompt is the rewritten text (or corpus_text on failure);
              error is None on success or a short message describing the failure.
    """
    import re

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
                {"role": "system", "content": _VLM_SYSTEM},
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


# Module-level model cache for MCP server reuse
_cached_model = None
_cached_model_name: str | None = None


def _load_model(model_name: str):
    """Load Flux2Klein, reusing the cached instance when model_name is unchanged."""
    global _cached_model, _cached_model_name
    if _cached_model is not None and _cached_model_name == model_name:
        return _cached_model

    from mflux.models.flux2.variants.txt2img.flux2_klein import Flux2Klein

    _cached_model = Flux2Klein(model_path=model_name)
    _cached_model_name = model_name
    return _cached_model


def generate(
    prompt: str,
    *,
    aspect_ratio: str = "3:2",
    seed: int | None = None,
    output_path: str | Path | None = None,
    model_name: str | None = None,
    steps: int | None = None,
) -> PILImage:
    """Generate an image locally via Flux2Klein (Apple Silicon / mflux).

    :param prompt: Text description of the image to generate.
    :param aspect_ratio: One of 1:1, 3:2, 2:3, 16:9, 9:16, 4:3, 3:4.
    :param seed: Random seed for reproducibility (random if omitted).
    :param output_path: If given, save the PNG here in addition to returning it.
    :param model_name: Override the HF model repo (default: mlx-community/flux2-klein-4b-4bit).
    :param steps: Override inference steps (default: 4).
    :returns: PIL Image.
    """
    model_name = model_name or os.environ.get("GUTENKG_IMAGE_MODEL", _DEFAULT_MODEL)
    steps = steps or int(os.environ.get("GUTENKG_IMAGE_STEPS", _DEFAULT_STEPS))
    seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    width, height = _ASPECT_SIZES.get(aspect_ratio, _ASPECT_SIZES["3:2"])

    model = _load_model(model_name)
    result = model.generate_image(
        seed=seed,
        prompt=prompt,
        width=width,
        height=height,
        guidance=1.0,
        num_inference_steps=steps,
        scheduler="flow_match_euler_discrete",
    )

    pil_image: PILImage = result.image

    if output_path is not None:
        pil_image.save(str(output_path))

    return pil_image


def generate_via_server(
    prompt: str,
    *,
    server_url: str,
    aspect_ratio: str = "3:2",
    seed: int | None = None,
    steps: int | None = None,
) -> PILImage:
    """Generate an image by calling a running mflux-serve HTTP server.

    Requires only httpx + pillow — safe to call from Linux containers or any
    environment without mflux installed.

    :param prompt: Text description of the image to generate.
    :param server_url: Base URL of the mflux-serve instance, e.g. http://localhost:8088.
    :param aspect_ratio: One of 1:1, 3:2, 2:3, 16:9, 9:16, 4:3, 3:4.
    :param seed: Optional integer seed for reproducibility.
    :param steps: Override inference steps (default: GUTENKG_IMAGE_STEPS or 4).
    :returns: PIL Image decoded from the server response.
    """
    import httpx
    from PIL import Image

    steps = steps or int(os.environ.get("GUTENKG_IMAGE_STEPS", _DEFAULT_STEPS))
    width, height = _ASPECT_SIZES.get(aspect_ratio, _ASPECT_SIZES["3:2"])

    payload: dict = {
        "prompt": prompt,
        "n": 1,
        "size": f"{width}x{height}",
        "num_inference_steps": steps,
        "response_format": "b64_json",
    }
    if seed is not None:
        payload["seed"] = seed

    resp = httpx.post(
        server_url.rstrip("/") + "/v1/images/generations",
        json=payload,
        timeout=httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0),
    )
    resp.raise_for_status()
    b64 = resp.json()["data"][0]["b64_json"]
    return Image.open(BytesIO(base64.b64decode(b64)))


def generate_auto(
    prompt: str,
    *,
    server_url: str | None = None,
    aspect_ratio: str = "3:2",
    seed: int | None = None,
    steps: int | None = None,
    model_name: str | None = None,
) -> PILImage:
    """Generate an image, preferring a remote server and falling back to local mflux.

    Resolution order:
      1. *server_url* argument (non-empty string)
      2. GUTENKG_IMAGE_ENDPOINT environment variable
      3. Local generate() — requires mflux on Apple Silicon

    :param prompt: Text description of the image to generate.
    :param server_url: Override server URL; pass None to use env var or local.
    :param aspect_ratio: One of 1:1, 3:2, 2:3, 16:9, 9:16, 4:3, 3:4.
    :param seed: Optional integer seed for reproducibility.
    :param steps: Override inference steps.
    :param model_name: Local model override (ignored when using server).
    :returns: PIL Image.
    """
    url = server_url or os.environ.get("GUTENKG_IMAGE_ENDPOINT", "")
    if url:
        return generate_via_server(
            prompt, server_url=url, aspect_ratio=aspect_ratio, seed=seed, steps=steps
        )
    return generate(
        prompt, aspect_ratio=aspect_ratio, seed=seed, steps=steps, model_name=model_name
    )
