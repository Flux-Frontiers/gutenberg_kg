# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""sdxl_server.py — GutenbergKG SDXL-Lightning image server (diffusers / MPS).

A fast, lightweight drop-in alternative to :mod:`gutenberg_kg.serve.image_server`
(mflux / FLUX.2). Exposes the identical OpenAI-style ``/v1/images/generations``
contract, so the worker only needs ``GUTENKG_IMAGE_ENDPOINT`` repointed — no
worker code changes.

Backed by SDXL base + a ByteDance SDXL-Lightning UNet (2/4/8-step). Much smaller
inference footprint than FLUX.2 and 2–4 step generation.

Runs from an env with torch + diffusers (NOT the mflux .venv-image). On this
machine personal_agent's venv already has everything:

    /Users/egs/repos/personal_agent/.venv/bin/python \
        /Users/egs/repos/gutenberg_kg/src/gutenberg_kg/serve/sdxl_server.py

Environment variables
---------------------
SDXL_MODEL        Lightning variant: sdxl_lightning_2 | _4 (default) | _8
SDXL_BASE         SDXL base repo (default: stabilityai/stable-diffusion-xl-base-1.0)
MPS_DTYPE         float16 (default; uses fp16-fix VAE) | float32 (heavier fallback)
IMAGE_OUTPUT_DIR  Dir for response_format=filepath (default: /tmp/gutenberg_images)
SDXL_SERVER_HOST  Bind host (default: 0.0.0.0)
SDXL_SERVER_PORT  Bind port (default: 8091)
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid
from io import BytesIO
from pathlib import Path

import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from huggingface_hub import hf_hub_download
from pydantic import BaseModel
from safetensors.torch import load_file

app = FastAPI(title="GutenbergKG SDXL-Lightning image server")

_MODEL = os.environ.get("SDXL_MODEL", "sdxl_lightning_4")
_BASE = os.environ.get("SDXL_BASE", "stabilityai/stable-diffusion-xl-base-1.0")
_OUTPUT_DIR = Path(os.environ.get("IMAGE_OUTPUT_DIR", "/tmp/gutenberg_images"))
_LIGHTNING_REPO = "ByteDance/SDXL-Lightning"
# fp16-safe VAE: the SDXL VAE overflows in float16 and yields black images; this
# fixed VAE lets the whole pipeline run float16 on MPS (~half the memory).
_VAE_FP16_FIX = "madebyollin/sdxl-vae-fp16-fix"

# SDXL-Lightning enforces its trained step count; guidance is ~1.0 (no CFG).
_STEPS = {"sdxl_lightning_2": 2, "sdxl_lightning_4": 4, "sdxl_lightning_8": 8}

_pipe = None  # module-level pipeline cache


def _device_dtype() -> tuple[str, torch.dtype]:
    """Resolve (device, dtype). MPS defaults to float16 — safe because we swap in
    the fp16-fix VAE; set MPS_DTYPE=float32 to force the heavier full-precision path."""
    if torch.cuda.is_available():
        return "cuda", torch.float16
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        want = os.environ.get("MPS_DTYPE", "float16").strip().lower()
        return "mps", (torch.float32 if want == "float32" else torch.float16)
    return "cpu", torch.float32


def _load_pipeline():
    """Build the SDXL + Lightning-UNet pipeline once and cache it."""
    global _pipe
    if _pipe is not None:
        return _pipe

    # diffusers is deferred: it lives only in the isolated .venv-sdxl
    # (docker/requirements-sdxl.txt), NOT the main Poetry env, so importing this
    # module for docs/tests/CLI never requires it. Only actually loading the
    # pipeline does — mirroring how image_server defers its mflux import.
    try:
        from diffusers import AutoencoderKL
        from diffusers.pipelines.stable_diffusion_xl.pipeline_stable_diffusion_xl import (
            StableDiffusionXLPipeline,
        )
        from diffusers.schedulers.scheduling_euler_discrete import EulerDiscreteScheduler
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The SDXL backend requires the isolated diffusers environment. "
            "Run `make sdxl-server` (creates .venv-sdxl from "
            "docker/requirements-sdxl.txt) instead of launching this module from "
            "the main env."
        ) from exc

    device, dtype = _device_dtype()
    steps = _STEPS.get(_MODEL, 4)
    print(f"[startup] loading {_BASE} + {_MODEL} on {device}/{dtype} …", flush=True)

    pipe = StableDiffusionXLPipeline.from_pretrained(
        _BASE, torch_dtype=dtype, local_files_only=True
    ).to(device)

    # In float16 the stock SDXL VAE overflows to black images; swap in the fp16-fix VAE.
    if dtype == torch.float16:
        print(f"[startup] loading fp16-fix VAE {_VAE_FP16_FIX} …", flush=True)
        pipe.vae = AutoencoderKL.from_pretrained(_VAE_FP16_FIX, torch_dtype=dtype).to(device)

    filename = f"sdxl_lightning_{steps}step_unet.safetensors"
    unet_path = hf_hub_download(_LIGHTNING_REPO, filename, local_files_only=True)
    state = load_file(unet_path, device=device)
    missing, unexpected = pipe.unet.load_state_dict(state, strict=False)
    if missing or unexpected:
        print(
            f"[startup] UNet load: missing={len(missing)} unexpected={len(unexpected)}", flush=True
        )

    # Lightning wants Euler + trailing timestep spacing.
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing"
    )
    try:
        pipe.enable_attention_slicing()
        pipe.vae.enable_slicing()
    except (AttributeError, RuntimeError, NotImplementedError):
        pass

    _pipe = pipe
    print("[startup] pipeline ready", flush=True)
    return _pipe


class ImageGenRequest(BaseModel):
    model: str = "sdxl_lightning_4"
    prompt: str
    n: int = 1
    size: str = "1024x1024"
    quality: str | None = None
    num_inference_steps: int | None = None
    seed: int | None = None
    response_format: str = "b64_json"
    negative_prompt: str = "blurry, bad quality, distorted"


@app.get("/v1/models")
def list_models():
    """OpenAI-compatible single-model listing."""
    return {
        "object": "list",
        "data": [{"id": _MODEL, "object": "model", "owned_by": "sdxl-lightning"}],
    }


def _render(req: ImageGenRequest):
    """Blocking SDXL-Lightning render. Returns a PIL image."""
    try:
        width, height = (int(v) for v in req.size.lower().split("x", 1))
    except (ValueError, AttributeError):
        width, height = 1024, 1024

    pipe = _load_pipeline()
    steps = _STEPS.get(_MODEL, req.num_inference_steps or 4)
    device, _ = _device_dtype()

    generator = None
    if req.seed is not None:
        try:
            generator = torch.Generator(device=device).manual_seed(int(req.seed))
        except (RuntimeError, TypeError):
            generator = None

    result = pipe(
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=1.0,  # Lightning: no CFG
        generator=generator,
    )
    image = result.images[0]

    # Release the MPS caching allocator's freed blocks so idle wired memory
    # returns to baseline between renders (analogous to CUDA's empty_cache).
    if device == "mps":
        torch.mps.empty_cache()
    return image


@app.post("/v1/images/generations")
async def generate_image(req: ImageGenRequest):
    """Generate an image via SDXL-Lightning; return base64 or a filepath."""
    loop = asyncio.get_event_loop()
    pil = await loop.run_in_executor(None, lambda: _render(req))

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
    """Run the SDXL-Lightning server (preloads the pipeline at startup)."""
    _load_pipeline()
    host = os.environ.get("SDXL_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SDXL_SERVER_PORT", "8091"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
