# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
image_server.py — GutenbergKG in-process image generation server

Thin FastAPI wrapper around image_gen.generate() that keeps the Flux2Klein
model loaded between requests.  Drop-in replacement for mflux-server with no
uvx subprocess, no per-request downloads.

Usage
-----
    # from repo root (recommended: isolated image env):
    make image-server

    # or run directly from the isolated venv:
    MFLUX_SERVER_HOST=0.0.0.0 .venv-image/bin/gutenkg-image-server

Environment variables
---------------------
GUTENKG_IMAGE_MODEL   HF repo for Flux2Klein (default: mlx-community/flux2-klein-4b-4bit)
IMAGE_STEPS           Default inference steps (default: 4)
IMAGE_OUTPUT_DIR      Directory for saved images when response_format=filepath (default: /tmp/gutenberg_images)
MFLUX_SERVER_HOST     Bind host (default: 0.0.0.0)
MFLUX_SERVER_PORT     Bind port (default: 8090)
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid
from io import BytesIO
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gutenberg_kg import image_gen

app = FastAPI(title="GutenbergKG image server")

_MODEL_NAME = os.environ.get("GUTENKG_IMAGE_MODEL", image_gen._DEFAULT_MODEL)
_DEFAULT_STEPS = int(os.environ.get("IMAGE_STEPS", "4"))
_OUTPUT_DIR = Path(os.environ.get("IMAGE_OUTPUT_DIR", "/tmp/gutenberg_images"))
_PRELOAD = os.environ.get("IMAGE_PRELOAD", "0").strip().lower() in {
    "1",
    "true",
    "yes",
}

# Optional preload for local generation; keep disabled by default so endpoint-only
# deployments do not require local mflux model imports at startup.
if _PRELOAD:
    print(f"[startup] loading model {_MODEL_NAME} ...")
    image_gen._load_model(_MODEL_NAME)
    print("[startup] model ready")
else:
    print("[startup] IMAGE_PRELOAD disabled; model will load on first generation request")


class ImageGenRequest(BaseModel):
    model: str = "flux2-klein-4b"
    prompt: str
    n: int = 1
    size: str = "1536x1024"
    quality: str | None = None
    num_inference_steps: int | None = None
    seed: int | None = None
    response_format: str = "b64_json"


@app.get("/v1/models")
def list_models():
    """List the single model this server serves, in OpenAI-compatible format.

    :returns: OpenAI-style ``{"object": "list", "data": [...]}`` model listing.
    """
    return {
        "object": "list",
        "data": [{"id": "flux2-klein-4b", "object": "model", "owned_by": "mflux"}],
    }


@app.post("/v1/images/generations")
async def generate_image(req: ImageGenRequest):
    """Generate an image via image_gen.generate() and return it as base64 or a filepath.

    Runs the (blocking) generation call in an executor thread to avoid blocking
    the event loop, passing the requested pixel size straight through.

    :param req: Parsed request body (prompt, size, steps, seed, response_format, ...).
    :returns: OpenAI-compatible JSON response with either ``b64_json`` or ``filepath``.
    """
    loop = asyncio.get_event_loop()
    pil = await loop.run_in_executor(
        None,
        lambda: image_gen.generate(
            req.prompt,
            size=req.size,
            seed=req.seed,
            model_name=_MODEL_NAME,
            steps=req.num_inference_steps or _DEFAULT_STEPS,
        ),
    )

    if req.response_format == "filepath":
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = _OUTPUT_DIR / f"{uuid.uuid4().hex}.png"
        pil.save(str(out))
        return JSONResponse({"created": int(time.time()), "data": [{"filepath": str(out)}]})

    buf = BytesIO()
    pil.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return JSONResponse({"created": int(time.time()), "data": [{"b64_json": b64}]})


def main() -> None:
    """Run the FastAPI app with uvicorn, using host/port from environment variables."""
    host = os.environ.get("MFLUX_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("MFLUX_SERVER_PORT", "8090"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
