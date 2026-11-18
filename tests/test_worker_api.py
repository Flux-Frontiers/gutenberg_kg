"""The worker's /runsync server: RunPod's request and reply format, kept exactly."""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from gutenberg_kg.serve.cors import cors_origins
from gutenberg_kg.serve.worker_api import ClientClosesFirst, create_app, run_job

FOREST = "http://localhost:5173"


def _client(handler, origins=frozenset()):
    return TestClient(create_app(handler, origins))


def test_a_result_comes_back_completed_with_its_none_values():
    seen = []

    def handler(job):
        seen.append(job)
        return {"hits": [], "synthesis": None}

    body = _client(handler).post("/runsync", json={"input": {"op": "x"}}).json()
    assert body["status"] == "COMPLETED"
    assert body["output"] == {"hits": [], "synthesis": None}
    assert "error" not in body
    assert seen[0]["input"] == {"op": "x"}
    assert seen[0]["id"] == body["id"]


def test_an_error_in_the_result_comes_back_failed_without_output():
    reply = _client(lambda job: {"error": "book not found: nope/nope", "x": 1}).post(
        "/runsync", json={"input": {}}
    )
    assert reply.status_code == 200
    body = reply.json()
    assert body["status"] == "FAILED"
    assert body["error"] == "book not found: nope/nope"
    assert "output" not in body


def test_an_empty_error_is_dropped_and_the_result_completes():
    body = run_job(lambda job: {"error": None, "stopped": False}, {})
    assert body["status"] == "COMPLETED"
    assert body["output"] == {"stopped": False}


def test_a_result_that_is_not_a_dict_is_passed_through():
    assert run_job(lambda job: [1, 2], {})["output"] == [1, 2]


def test_an_exception_comes_back_failed_with_its_type_and_message():
    def handler(job):
        return int(job["input"]["k"])

    reply = _client(handler).post("/runsync", json={"input": {"k": "abc"}})
    assert reply.status_code == 200
    body = reply.json()
    assert body["status"] == "FAILED"
    error = json.loads(body["error"])
    assert error["error_type"] == "<class 'ValueError'>"
    assert "invalid literal" in error["error_message"]
    assert "Traceback" in error["error_traceback"]


def test_a_body_without_a_dict_input_is_refused():
    client = _client(lambda job: {})
    assert client.post("/runsync", json={"x": 1}).status_code == 422
    assert client.post("/runsync", json={"input": [1, 2]}).status_code == 422
    bad = client.post(
        "/runsync", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert bad.status_code == 422


def test_cors_is_added_only_for_allowed_origins():
    client = _client(lambda job: {"ok": True}, cors_origins(FOREST))
    pre = client.options(
        "/runsync",
        headers={"origin": FOREST, "access-control-request-method": "POST"},
    )
    assert pre.status_code == 204
    assert pre.headers["access-control-allow-origin"] == FOREST
    ok = client.post("/runsync", json={"input": {}}, headers={"origin": FOREST})
    assert ok.headers["access-control-allow-origin"] == FOREST
    other = client.post("/runsync", json={"input": {}}, headers={"origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


async def _reply(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"data"})


def _hold(headers, http_version="1.1", events=("http.disconnect",), wait=5.0):
    """Run ClientClosesFirst over a one-frame reply; return what was sent, in order."""
    log: list = []
    queue = list(events)

    async def receive():
        log.append("receive")
        if not queue:
            await asyncio.sleep(3600)
        return {"type": queue.pop(0)}

    async def send(message):
        log.append((message["type"], message.get("body"), message.get("more_body", False)))

    scope = {"type": "http", "http_version": http_version, "headers": headers}
    asyncio.run(ClientClosesFirst(_reply, wait=wait)(scope, receive, send))
    return log


def test_a_closing_request_waits_for_the_client_before_the_last_frame():
    log = _hold([(b"connection", b"close")])
    assert log == [
        ("http.response.start", None, False),
        ("http.response.body", b"data", True),
        "receive",
        ("http.response.body", b"", False),
    ]


def test_other_events_are_skipped_until_the_disconnect():
    log = _hold([(b"connection", b"Close")], events=("http.request", "http.disconnect"))
    assert log.count("receive") == 2
    assert log[-1] == ("http.response.body", b"", False)


def test_the_wait_gives_up_after_its_timeout():
    log = _hold([(b"connection", b"close")], events=(), wait=0.05)
    assert log[-1] == ("http.response.body", b"", False)


def test_keep_alive_requests_pass_through_untouched():
    log = _hold([(b"connection", b"keep-alive")])
    assert log == [("http.response.start", None, False), ("http.response.body", b"data", False)]
    assert _hold([]) == log


def test_http_1_0_closes_unless_it_asks_for_keep_alive():
    assert "receive" in _hold([], http_version="1.0")
    assert "receive" not in _hold([(b"connection", b"keep-alive")], http_version="1.0")
