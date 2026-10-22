"""CORS for the local worker: preflights, allowed origins and everything else."""

from __future__ import annotations

import asyncio

from gutenberg_kg.serve.cors import CORSMiddleware, cors_origins

FOREST = "http://localhost:5173"
ORIGINS = cors_origins(f"{FOREST}, https://flux-frontiers.github.io/")


async def _app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"x")]})
    await send({"type": "http.response.body", "body": b"ok"})


def _call(method, headers):
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b""}

    scope = {
        "type": "http",
        "method": method,
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
    }
    asyncio.run(CORSMiddleware(_app, ORIGINS)(scope, receive, send))
    start = sent[0]
    return start["status"], {k.decode(): v.decode() for k, v in start["headers"]}


def test_origins_are_trimmed_and_lose_a_trailing_slash():
    assert ORIGINS == {FOREST, "https://flux-frontiers.github.io"}
    assert cors_origins("") == frozenset()


def test_preflight_from_an_allowed_origin():
    status, headers = _call(
        "OPTIONS",
        {
            "origin": FOREST,
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type",
        },
    )
    assert status == 204
    assert headers["access-control-allow-origin"] == FOREST
    assert headers["access-control-allow-methods"] == "POST"
    assert headers["access-control-allow-headers"] == "content-type"
    assert "access-control-allow-private-network" not in headers


def test_preflight_asking_for_the_private_network_is_answered():
    _, headers = _call(
        "OPTIONS",
        {
            "origin": "https://flux-frontiers.github.io",
            "access-control-request-method": "POST",
            "access-control-request-private-network": "true",
        },
    )
    assert headers["access-control-allow-private-network"] == "true"


def test_a_post_from_an_allowed_origin_gets_the_header():
    status, headers = _call("POST", {"origin": FOREST})
    assert status == 200
    assert headers["access-control-allow-origin"] == FOREST
    assert headers["vary"] == "Origin"
    assert headers["content-type"] == "x"


def test_other_origins_pass_through_without_cors():
    status, headers = _call("POST", {"origin": "https://evil.example"})
    assert status == 200 and "access-control-allow-origin" not in headers
    # A preflight from elsewhere reaches the app, which refuses OPTIONS itself.
    status, headers = _call(
        "OPTIONS", {"origin": "https://evil.example", "access-control-request-method": "POST"}
    )
    assert "access-control-allow-origin" not in headers


def test_requests_without_an_origin_are_untouched():
    status, headers = _call("POST", {})
    assert status == 200 and "access-control-allow-origin" not in headers
