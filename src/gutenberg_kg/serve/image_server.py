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
IMAGE_IDLE_UNLOAD_S   Unload FLUX after this many idle seconds, so a small Mac gets
                      its 12-15 GB back for the LLM; the next render reloads it.
                      0 (default) keeps it loaded.  `make models` sets 300 on
                      Macs of 24 GB or less (scripts/model_tiers.json).
"""

from __future__ import annotations

import asyncio
import base64
import os
import threading
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


def _preload() -> None:
    """Load the model now if ``IMAGE_PRELOAD`` asks for it.

    Called when the built-in server starts, not at import: when imagewright
    serves instead, it loads the model itself, and loading here as well would
    hold FLUX in memory twice.
    """
    if _PRELOAD:
        print(f"[startup] loading model {_MODEL_NAME} ...")
        image_gen._load_model(_MODEL_NAME)
        print("[startup] model ready")
    else:
        print("[startup] IMAGE_PRELOAD disabled; model will load on first generation request")


_IDLE_UNLOAD_S = int(os.environ.get("IMAGE_IDLE_UNLOAD_S", "0") or 0)
# One render at a time, and never an unload in the middle of one.
_gen_lock = threading.Lock()
_last_used = time.monotonic()


def _render(**kwargs):
    """Run image_gen.generate() under the lock and note when it finished."""
    global _last_used
    with _gen_lock:
        try:
            return image_gen.generate(**kwargs)
        finally:
            _last_used = time.monotonic()


def maybe_unload(now: float | None = None) -> bool:
    """Unload FLUX if it has been idle for ``IMAGE_IDLE_UNLOAD_S`` seconds.

    Skipped while a render holds the lock; the watcher tries again later.

    :param now: The current ``time.monotonic()`` reading (for tests).
    :returns: ``True`` if the model was unloaded.
    """
    if _IDLE_UNLOAD_S <= 0 or not image_gen.model_loaded():
        return False
    now = time.monotonic() if now is None else now
    if now - _last_used < _IDLE_UNLOAD_S:
        return False
    if not _gen_lock.acquire(blocking=False):
        return False
    try:
        return image_gen.unload_model()
    finally:
        _gen_lock.release()


def _idle_watcher() -> None:
    """Check for an idle model every few seconds, for the life of the server."""
    interval = max(5.0, min(30.0, _IDLE_UNLOAD_S / 4))
    while True:
        time.sleep(interval)
        if maybe_unload():
            print(f"[idle] FLUX unloaded after {_IDLE_UNLOAD_S}s idle; the next render reloads it")


class ImageGenRequest(BaseModel):
    model: str = "flux2-klein-4b"
    prompt: str
    n: int = 1
    size: str = "1536x1024"
    quality: str | None = None
    num_inference_steps: int | None = None
    seed: int | None = None
    response_format: str = "b64_json"


@app.get("/health")
def health():
    """Liveness probe.

    Deliberately does no model work: it answers while a generation is in
    flight and before any weights are resident, so a caller can tell "this
    port is mine" apart from "this port is ready to be fast".

    :returns: ``{"status": "ok", ...}`` identifying the backend.
    """
    return {
        "status": "ok",
        "backend": "flux",
        "model": "flux2-klein-4b",
        "loaded": image_gen.model_loaded(),
        "idle_unload_s": _IDLE_UNLOAD_S,
    }


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
        lambda: _render(
            prompt=req.prompt,
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


def _imagewright_server():
    """Return imagewright's FLUX server module, or None when it cannot serve here.

    `.venv-image` is an editable install, so a `git pull` changes this code
    before anyone refreshes the environment. One built before imagewright
    existed has no imagewright, and this server must keep serving there. Any
    failure to import it, or a missing extra, therefore means "use the
    built-in server", never a crash.

    :return: ``imagewright.flux_server``, or None.
    """
    try:
        from imagewright import flux_server  # noqa: PLC0415 - may be absent, see above

        flux_server.require_extras()
    except Exception as exc:  # noqa: BLE001 - any failure selects the built-in server
        print(f"[startup] imagewright cannot serve here ({type(exc).__name__}: {exc})")
        return None
    return flux_server


def _serve_builtin(host: str, port: int) -> None:
    """Run this module's own FastAPI app, as every release before imagewright did."""
    _preload()
    if _IDLE_UNLOAD_S > 0:
        threading.Thread(target=_idle_watcher, name="flux-idle-unload", daemon=True).start()
        print(f"[startup] FLUX unloads after {_IDLE_UNLOAD_S}s idle (IMAGE_IDLE_UNLOAD_S)")
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    """Serve FLUX on ``MFLUX_SERVER_HOST``:``MFLUX_SERVER_PORT``.

    Through imagewright's server when this environment has it (the same routes,
    request fields and response bodies), else through the built-in one.
    """
    host = os.environ.get("MFLUX_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("MFLUX_SERVER_PORT", "8090"))
    server = _imagewright_server()
    if server is None:
        print(
            "[startup] serving with the built-in FLUX server; "
            "run `make image-server` to refresh .venv-image"
        )
        _serve_builtin(host, port)
        return
    # imagewright's default is its own temp folder; keep this repo's.
    os.environ.setdefault("IMAGE_OUTPUT_DIR", str(_OUTPUT_DIR))
    print("[startup] serving FLUX through imagewright")
    uvicorn.run(server.create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
