"""Which image backends this worker can use right now -- the ``image_backends`` op.

The chat UI and the apps show an image-backend picker built from this list, so
a reader is only offered backends that will work: no Local entry on a host
without an image server, no OpenAI entry on a worker without a key.

Kept out of ``handler.py`` because importing the handler opens the corpus
indices at module load; this module imports nothing heavier than ``httpx``.
"""

from __future__ import annotations

import os

from gutenberg_kg.image_gen import discover_image_endpoint

#: Backend keys, in the order the pickers list them. They are the worker's
#: ``image_backend`` values (``kg_utils.synthesis.ImageBackend``).
LOCAL = "mflux-serve"
OPENAI = "openai"


def _local_endpoint() -> str:
    """Return the image-server URL the worker is configured with, or ``""``."""
    return (
        os.environ.get("IMAGE_ENDPOINT") or os.environ.get("GUTENKG_IMAGE_ENDPOINT") or ""
    ).strip()


def image_backends(default_backend: str, *, timeout: float = 1.5) -> dict:
    """Report each image backend and whether this worker can use it now.

    Local counts as available when the configured image server answers its
    health check; OpenAI when the worker holds an OpenAI or image API key. The
    key itself is never returned.

    :param default_backend: The worker's configured default (its ``IMAGE_BACKEND``).
    :param timeout: Seconds to wait for the image server's health check.
    :returns: ``{"default": str, "backends": [{"key", "label", "available", "detail"}, ...]}``.
    """
    endpoint = _local_endpoint()
    if not endpoint:
        local_ok, local_detail = False, "no image server configured on the worker"
    elif discover_image_endpoint((endpoint,), timeout=timeout):
        local_ok, local_detail = True, endpoint
    else:
        local_ok, local_detail = False, f"image server at {endpoint} is not responding"

    has_key = bool(os.environ.get("IMAGE_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    openai_detail = "gpt-image-1, billed per image" if has_key else "no OpenAI key on the worker"

    return {
        "default": default_backend,
        "backends": [
            {"key": LOCAL, "label": "Local", "available": local_ok, "detail": local_detail},
            {"key": OPENAI, "label": "OpenAI", "available": has_key, "detail": openai_detail},
        ],
    }
