# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
image_server.py — GutenbergKG in-process image generation server

Thin FastAPI wrapper around image_gen.generate() that keeps the Flux2Klein
model loaded between requests.  Drop-in replacement for mflux-server with no
uvx subprocess, no per-request downloads.

Usage
-----
    # from repo root, with the venv active:
    MFLUX_SERVER_HOST=0.0.0.0 python docker/image_server.py

    # or via the venv directly:
    MFLUX_SERVER_HOST=0.0.0.0 .venv/bin/python docker/image_server.py

Environment variables
---------------------
GUTENKG_IMAGE_MODEL   HF repo for Flux2Klein (default: mlx-community/flux2-klein-4b-4bit)
GUTENKG_IMAGE_STEPS   Default inference steps (default: 4)
MFLUX_SERVER_HOST     Bind host (default: 0.0.0.0)
MFLUX_SERVER_PORT     Bind port (default: 8090)
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from io import BytesIO

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gutenberg_kg import image_gen

app = FastAPI(title="GutenbergKG image server")

_MODEL_NAME = os.environ.get("GUTENKG_IMAGE_MODEL", image_gen._DEFAULT_MODEL)
_DEFAULT_STEPS = int(os.environ.get("GUTENKG_IMAGE_STEPS", "4"))

# Pre-load the model at startup so the first request isn't slow.
print(f"[startup] loading model {_MODEL_NAME} ...")
image_gen._load_model(_MODEL_NAME)
print("[startup] model ready")


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
    return {
        "object": "list",
        "data": [{"id": "flux2-klein-4b", "object": "model", "owned_by": "mflux"}],
    }


@app.post("/v1/images/generations")
async def generate_image(req: ImageGenRequest):
    try:
        width, height = map(int, req.size.split("x"))
    except ValueError:
        width, height = 1536, 1024

    # Derive aspect ratio string from dimensions for image_gen.generate()
    ratio_map = {
        (1024, 1024): "1:1",
        (1536, 1024): "3:2",
        (1024, 1536): "2:3",
        (1536, 864): "16:9",
        (864, 1536): "9:16",
        (1365, 1024): "4:3",
        (1024, 1365): "3:4",
    }
    aspect = ratio_map.get((width, height), "3:2")

    loop = asyncio.get_event_loop()
    pil = await loop.run_in_executor(
        None,
        lambda: image_gen.generate(
            req.prompt,
            aspect_ratio=aspect,
            seed=req.seed,
            model_name=_MODEL_NAME,
            steps=req.num_inference_steps or _DEFAULT_STEPS,
        ),
    )

    buf = BytesIO()
    pil.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    return JSONResponse(
        {
            "created": int(time.time()),
            "data": [{"b64_json": b64}],
        }
    )


def main() -> None:
    host = os.environ.get("MFLUX_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("MFLUX_SERVER_PORT", "8090"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
