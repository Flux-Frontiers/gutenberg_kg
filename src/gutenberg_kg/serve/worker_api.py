# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""The worker's HTTP server: ``POST /runsync`` in RunPod's request and reply format.

The worker used to run RunPod's local test server (``runpod.serverless.start``
with ``--rp_serve_api``). It was never deployed to RunPod, and that server
offers no control over uvicorn, so this module serves the same contract with
FastAPI and uvicorn directly. The Knowledge Press app, the web forest and the
chat UI all speak it, so it must not change:

Request: ``{"input": {...}}``. Anything else is answered 422, as before.

Reply, HTTP 200 once the request parses:

- ``{"id", "status": "COMPLETED", "output": <the handler's result>}``
- ``{"id", "status": "FAILED", "error": <message>}`` when the handler's result
  carries a truthy ``"error"``, or the handler raises. A raised exception's
  message is a JSON string with ``error_type``, ``error_message`` and
  ``error_traceback``, as RunPod sent it.

The handler runs on the event loop, one job at a time, as it did under RunPod:
its module state (registry, stores, moot sessions, the FLUX client) has only
ever been used from one thread.
"""

from __future__ import annotations

import json
import traceback
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from gutenberg_kg.serve.cors import CORSMiddleware

Handler = Callable[[dict], Any]


class RunRequest(BaseModel):
    """The body of a ``/runsync`` request.

    :param input: The handler's input; see the handler module's request schema.
    """

    input: dict[str, Any]


def run_job(handler: Handler, inp: dict[str, Any]) -> dict[str, Any]:
    """Run one job and wrap its result in the reply envelope.

    :param handler: The worker's handler; called with ``{"id", "input"}``.
    :param inp: The request's ``input``.
    :returns: The COMPLETED or FAILED envelope described in the module docstring.
    """
    job_id = str(uuid.uuid4())
    try:
        result = handler({"id": job_id, "input": inp})
    except Exception as exc:  # noqa: BLE001 -- every failure becomes a FAILED reply
        traceback.print_exc()
        error = {
            "error_type": str(type(exc)),
            "error_message": str(exc),
            "error_traceback": traceback.format_exc(),
        }
        return {"id": job_id, "status": "FAILED", "error": json.dumps(error)}
    if isinstance(result, dict) and result.get("error"):
        return {"id": job_id, "status": "FAILED", "error": result["error"]}
    if isinstance(result, dict) and "error" in result:
        result = {k: v for k, v in result.items() if k != "error"}
    return {"id": job_id, "status": "COMPLETED", "output": result}


def create_app(handler: Handler, origins: frozenset[str] = frozenset()):
    """Build the worker's ASGI app.

    :param handler: The worker's handler.
    :param origins: Origins a browser may call from; empty for no CORS.
    :returns: The app, wrapped in :class:`CORSMiddleware` when ``origins`` is set.
    """
    app = FastAPI(title="GutenbergKG worker", docs_url="/")

    @app.post("/runsync")
    async def runsync(request: RunRequest) -> dict[str, Any]:
        # async on purpose: the handler runs on the loop, one job at a time.
        return run_job(handler, request.input)

    if origins:
        app.add_middleware(CORSMiddleware, origins=origins)
    return app
