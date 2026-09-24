"""The worker's ``image_backends`` op (``serve/image_backends.py``).

The pickers in the chat UI and the apps list only the backends this reports as
available, so each case here is a picker entry that must or must not appear.
"""

from __future__ import annotations

import pytest

from gutenberg_kg.serve import image_backends as ib

_ENV = ("IMAGE_ENDPOINT", "GUTENKG_IMAGE_ENDPOINT", "IMAGE_API_KEY", "OPENAI_API_KEY")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def _by_key(report: dict) -> dict:
    return {b["key"]: b for b in report["backends"]}


def _server(monkeypatch, up: bool) -> list:
    """Stub the health check; return the list of URLs it was asked about."""
    asked: list = []

    def _discover(candidates, timeout):
        asked.extend(candidates)
        return candidates[0] if up else None

    monkeypatch.setattr(ib, "discover_image_endpoint", _discover)
    return asked


def test_local_available_when_the_server_answers(monkeypatch):
    monkeypatch.setenv("IMAGE_ENDPOINT", "http://host:8090")
    asked = _server(monkeypatch, up=True)

    local = _by_key(ib.image_backends("mflux-serve"))[ib.LOCAL]

    assert local["available"] is True
    assert asked == ["http://host:8090"]


def test_local_unavailable_when_the_server_is_down(monkeypatch):
    monkeypatch.setenv("IMAGE_ENDPOINT", "http://host:8090")
    _server(monkeypatch, up=False)

    local = _by_key(ib.image_backends("mflux-serve"))[ib.LOCAL]

    assert local["available"] is False
    assert "not responding" in local["detail"]


def test_local_unavailable_without_an_endpoint_and_nothing_probed(monkeypatch):
    asked = _server(monkeypatch, up=True)

    local = _by_key(ib.image_backends("mflux-serve"))[ib.LOCAL]

    assert local["available"] is False
    assert asked == []


def test_gutenkg_image_endpoint_is_the_fallback(monkeypatch):
    monkeypatch.setenv("GUTENKG_IMAGE_ENDPOINT", "http://other:8091")
    asked = _server(monkeypatch, up=True)

    ib.image_backends("mflux-serve")

    assert asked == ["http://other:8091"]


@pytest.mark.parametrize("var", ["OPENAI_API_KEY", "IMAGE_API_KEY"])
def test_openai_available_with_either_key_and_the_key_is_not_returned(monkeypatch, var):
    monkeypatch.setenv(var, "sk-secret-value")
    _server(monkeypatch, up=False)

    report = ib.image_backends("openai")

    assert _by_key(report)[ib.OPENAI]["available"] is True
    assert "sk-secret-value" not in repr(report)


def test_openai_unavailable_without_a_key(monkeypatch):
    _server(monkeypatch, up=False)

    assert _by_key(ib.image_backends("mflux-serve"))[ib.OPENAI]["available"] is False


def test_reports_the_workers_default(monkeypatch):
    _server(monkeypatch, up=False)

    assert ib.image_backends("openai")["default"] == "openai"
