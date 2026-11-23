# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""What image_gen sends to an image server, and how it finds one.

These pin the client side of the HTTP contract against a real server on an
ephemeral port: the request body, the GUTENKG_IMAGE_* defaults, and discovery.
They were written against the in-repo client and kept unchanged when
image_gen moved onto imagewright, so they show the two behave the same.
"""

from __future__ import annotations

import base64
import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import pytest
from PIL import Image

from gutenberg_kg import image_gen


class _ImageServer:
    """A server that answers the image contract and records what it was sent."""

    def __init__(self, *, health: bool = True, status: int = 200) -> None:
        self.bodies: list[dict] = []
        self.paths: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, code: int, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                outer.paths.append(self.path)
                if self.path == "/health" and health:
                    self._reply(200, {"status": "ok"})
                elif self.path == "/v1/models":
                    self._reply(200, {"object": "list", "data": []})
                else:
                    self._reply(404, {"detail": "Not Found"})

            def do_POST(self) -> None:  # noqa: N802
                outer.paths.append(self.path)
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.bodies.append(body)
                if status != 200:
                    self._reply(status, {"detail": "boom"})
                    return
                width, height = (int(v) for v in body["size"].split("x"))
                buf = BytesIO()
                Image.new("RGB", (width // 64, height // 64), "navy").save(buf, format="PNG")
                self._reply(
                    200, {"data": [{"b64_json": base64.b64encode(buf.getvalue()).decode()}]}
                )

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()


@pytest.fixture
def server() -> Iterator[_ImageServer]:
    srv = _ImageServer()
    yield srv
    srv.close()


@pytest.fixture(autouse=True)
def _no_image_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GUTENKG_IMAGE_STEPS", "GUTENKG_IMAGE_SIZE", "IMAGE_STEPS", "IMAGE_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)


def _closed_port_url() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"


def test_request_body_with_every_argument(server: _ImageServer) -> None:
    image = image_gen.generate_via_server(
        "a lighthouse", server_url=server.url + "/", size="768x512", seed=7, steps=6
    )
    assert server.paths == ["/v1/images/generations"]
    assert server.bodies == [
        {
            "prompt": "a lighthouse",
            "n": 1,
            "size": "768x512",
            "num_inference_steps": 6,
            "response_format": "b64_json",
            "seed": 7,
        }
    ]
    assert image.size == (12, 8)


def test_request_body_defaults(server: _ImageServer) -> None:
    image_gen.generate_via_server("a lighthouse", server_url=server.url)
    assert server.bodies == [
        {
            "prompt": "a lighthouse",
            "n": 1,
            "size": "1536x1024",
            "num_inference_steps": 4,
            "response_format": "b64_json",
        }
    ]


def test_gutenkg_env_sets_the_defaults(server: _ImageServer, monkeypatch) -> None:
    monkeypatch.setenv("GUTENKG_IMAGE_STEPS", "9")
    monkeypatch.setenv("GUTENKG_IMAGE_SIZE", "1024x1024")
    image_gen.generate_via_server("a lighthouse", server_url=server.url)
    assert server.bodies[0]["num_inference_steps"] == 9
    assert server.bodies[0]["size"] == "1024x1024"


def test_arguments_beat_the_env(server: _ImageServer, monkeypatch) -> None:
    monkeypatch.setenv("GUTENKG_IMAGE_STEPS", "9")
    monkeypatch.setenv("GUTENKG_IMAGE_SIZE", "1024x1024")
    image_gen.generate_via_server("a lighthouse", server_url=server.url, size="512x512", steps=2)
    assert server.bodies[0]["num_inference_steps"] == 2
    assert server.bodies[0]["size"] == "512x512"


def test_a_size_that_does_not_parse_becomes_the_default(server: _ImageServer) -> None:
    image_gen.generate_via_server("a lighthouse", server_url=server.url, size="huge")
    assert server.bodies[0]["size"] == "1536x1024"


def test_a_server_error_raises() -> None:
    srv = _ImageServer(status=500)
    try:
        with pytest.raises(Exception, match="500"):
            image_gen.generate_via_server("a lighthouse", server_url=srv.url)
    finally:
        srv.close()


def test_discovery_returns_the_first_server_that_answers(server: _ImageServer) -> None:
    down = _closed_port_url()
    assert image_gen.discover_image_endpoint((down, server.url), timeout=1.0) == server.url
    assert server.paths == ["/health"]


def test_discovery_falls_back_to_the_model_listing() -> None:
    srv = _ImageServer(health=False)
    try:
        assert image_gen.discover_image_endpoint((srv.url,), timeout=1.0) == srv.url
        assert srv.paths == ["/health", "/v1/models"]
    finally:
        srv.close()


def test_discovery_finds_nothing_when_nothing_answers() -> None:
    assert image_gen.discover_image_endpoint((_closed_port_url(),), timeout=0.5) is None


def test_discovery_defaults_are_the_two_local_ports() -> None:
    assert image_gen.DEFAULT_IMAGE_ENDPOINTS == ("http://localhost:8090", "http://localhost:8091")
