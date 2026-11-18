"""The worker's /runsync server: RunPod's request and reply format, kept exactly."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from gutenberg_kg.serve.cors import cors_origins
from gutenberg_kg.serve.worker_api import create_app, run_job

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
