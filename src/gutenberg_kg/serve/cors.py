# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""CORS for the local worker, so the Knowledge Press Forest can call it.

RunPod's local API server (``--rp_serve_api``) sends no CORS headers, so a
browser page cannot read its answers. :class:`CORSMiddleware` is plain ASGI:
it answers preflight requests from the allowed origins and adds
``Access-Control-Allow-Origin`` to their responses. A request from any other
origin passes through untouched, without CORS headers, so the browser refuses
it as before.

The handler installs it only when ``GUTENKG_CORS_ORIGINS`` is set (see
:func:`cors_origins`).
"""

from __future__ import annotations

#: The environment variable naming the allowed origins, comma separated.
CORS_ENV = "GUTENKG_CORS_ORIGINS"
#: How long a browser may cache a preflight answer, in seconds.
PREFLIGHT_MAX_AGE = 600


def cors_origins(value: str) -> frozenset[str]:
    """The allowed origins in a ``GUTENKG_CORS_ORIGINS`` value.

    :param value: Comma-separated origins, e.g.
        ``"http://localhost:5173,https://flux-frontiers.github.io"``.
    :returns: Each origin, trimmed, without a trailing slash; empty for ``""``.
    """
    return frozenset(o.strip().rstrip("/") for o in value.split(",") if o.strip())


def _header(scope: dict, name: bytes) -> str | None:
    for key, val in scope.get("headers", []):
        if key.lower() == name:
            return val.decode("latin-1")
    return None


class CORSMiddleware:
    """Allow POST requests from a fixed set of origins.

    :param app: The ASGI app to wrap.
    :param origins: The allowed origins, as :func:`cors_origins` returns them.
    """

    def __init__(self, app, origins: frozenset[str]) -> None:
        self.app = app
        self.origins = origins

    async def __call__(self, scope, receive, send) -> None:
        origin = _header(scope, b"origin") if scope["type"] == "http" else None
        if origin is None or origin not in self.origins:
            await self.app(scope, receive, send)
            return
        allow = [
            (b"access-control-allow-origin", origin.encode("latin-1")),
            (b"vary", b"Origin"),
        ]
        if scope["method"] == "OPTIONS" and _header(scope, b"access-control-request-method"):
            headers = [
                *allow,
                (b"access-control-allow-methods", b"POST"),
                (b"access-control-allow-headers", b"content-type"),
                (b"access-control-max-age", str(PREFLIGHT_MAX_AGE).encode()),
            ]
            # Chrome asks before a public page reaches a local address.
            if _header(scope, b"access-control-request-private-network") == "true":
                headers.append((b"access-control-allow-private-network", b"true"))
            await send({"type": "http.response.start", "status": 204, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), *allow]}
            await send(message)

        await self.app(scope, receive, send_with_cors)
