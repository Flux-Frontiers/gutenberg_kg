"""Image generation — local Flux2Klein via mflux (Apple Silicon only).

Used by image_server.py to keep the model loaded between requests.
Remote-server and VLM-rewrite paths live in kg_utils.synthesis.ImageSynthesizer
and kg_utils.synthesis.TextSynthesizer respectively.

Environment variables
---------------------
GUTENKG_IMAGE_MODEL   HuggingFace repo or mflux model name
                      (default: mlx-community/flux2-klein-4b-4bit)
IMAGE_STEPS           Inference steps (default: 4)
"""

from __future__ import annotations

import os
import random
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

# Module-level model cache for image_server.py reuse
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
    steps = steps or int(os.environ.get("IMAGE_STEPS", _DEFAULT_STEPS))
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
