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

The worker never closes a connection first (:class:`ClientClosesFirst` and
:data:`KEEP_ALIVE_S`). Apple ``container``'s published-port forwarder drops
whatever it has not yet relayed when the server closes, so a large reply (a
render is 2-9 MB) reached slow or remote clients cut short. In apple/container
1.1.0 that is ``Sources/SocketForwarder/GlueHandler.swift:93-95``, which closes
the client side fully when the backend goes away. Docker's forwarder does not.
"""

from __future__ import annotations

import asyncio
import json
import traceback
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from gutenberg_kg.serve.cors import CORSMiddleware

Handler = Callable[[dict], Any]

#: uvicorn's idle keep-alive timeout, in seconds. Its default of 5 s let the
#: worker close an idle connection before a slow client had read the reply.
KEEP_ALIVE_S = 300
#: How long :class:`ClientClosesFirst` waits for the client to hang up.
CLOSE_WAIT_S = 300.0


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


class ClientClosesFirst:
    """Let the client close a ``Connection: close`` request's connection first.

    uvicorn closes the socket as soon as the last byte of such a reply is
    written. Here the reply's final, empty body frame is held back until the
    client disconnects, or :data:`CLOSE_WAIT_S` passes. The client already has
    every byte by then: the reply carries a Content-Length.

    :param app: The ASGI app to wrap.
    :param wait: Seconds to wait for the client to disconnect.
    """

    def __init__(self, app, wait: float = CLOSE_WAIT_S) -> None:
        self.app = app
        self.wait = wait

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not _closes(scope):
            await self.app(scope, receive, send)
            return

        async def held_send(message) -> None:
            if message["type"] != "http.response.body" or message.get("more_body", False):
                await send(message)
                return
            await send({**message, "more_body": True})
            try:
                async with asyncio.timeout(self.wait):
                    while (await receive())["type"] != "http.disconnect":
                        pass
            except TimeoutError:
                pass
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        await self.app(scope, receive, held_send)


def _closes(scope) -> bool:
    """Whether the request asked the server to close the connection after it."""
    tokens = b",".join(v for k, v in scope.get("headers", []) if k.lower() == b"connection")
    tokens = {t.strip() for t in tokens.lower().split(b",")}
    if scope.get("http_version") == "1.0":
        return b"keep-alive" not in tokens
    return b"close" in tokens


def create_app(handler: Handler, origins: frozenset[str] = frozenset()):
    """Build the worker's ASGI app.

    :param handler: The worker's handler.
    :param origins: Origins a browser may call from; empty for no CORS.
    :returns: The app, wrapped in :class:`CORSMiddleware` when ``origins`` is
        set, and in :class:`ClientClosesFirst`.
    """
    app = FastAPI(title="GutenbergKG worker", docs_url="/")

    @app.post("/runsync")
    async def runsync(request: RunRequest) -> dict[str, Any]:
        # async on purpose: the handler runs on the loop, one job at a time.
        return run_job(handler, request.input)

    if origins:
        app.add_middleware(CORSMiddleware, origins=origins)
    return ClientClosesFirst(app)
