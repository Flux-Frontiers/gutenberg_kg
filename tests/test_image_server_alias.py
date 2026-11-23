# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""`gutenkg-image-server` and `gutenkg-sdxl-server` run ``imagewright serve``.

The servers are imagewright's. These two commands stay for one release so a
LaunchAgent written before it keeps starting a server. The tests run the real
``imagewright serve`` command and the real FastAPI apps; only ``uvicorn``,
which would bind a port and never return, is replaced.
"""

from __future__ import annotations

import sys
from importlib.machinery import ModuleSpec
from types import ModuleType

import pytest

from gutenberg_kg.serve import image_server, sdxl_server

_SDXL_STACK = ("torch", "diffusers", "transformers", "accelerate", "safetensors")


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Record what ``imagewright serve`` hands to ``uvicorn.run`` instead of serving."""
    calls: list[dict] = []
    fake = ModuleType("uvicorn")
    fake.__spec__ = ModuleSpec("uvicorn", None)
    fake.run = lambda app, host, port: calls.append({"app": app, "host": host, "port": port})
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    for name in (
        "MFLUX_SERVER_HOST",
        "MFLUX_SERVER_PORT",
        "SDXL_SERVER_HOST",
        "SDXL_SERVER_PORT",
        "IMAGE_PRELOAD",
        "IMAGE_IDLE_UNLOAD_S",
    ):
        monkeypatch.delenv(name, raising=False)
    return calls


def _pretend_installed(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Make ``importlib.util.find_spec`` see these packages, without their code."""
    for name in names:
        module = ModuleType(name)
        module.__spec__ = ModuleSpec(name, None)
        monkeypatch.setitem(sys.modules, name, module)


def _run(main) -> int:
    """Run an alias to completion and return its exit code.

    :param main: The command's ``main``.
    :returns: The code click exits with once ``uvicorn.run`` returns.
    """
    with pytest.raises(SystemExit) as stopped:
        main()
    return stopped.value.code


# --------------------------------------------------------------------- FLUX


def test_flux_alias_serves_imagewright_on_all_interfaces(served, monkeypatch, capsys):
    _pretend_installed(monkeypatch, "mflux")
    assert _run(image_server.main) == 0
    assert len(served) == 1
    assert served[0]["app"].title == "imagewright FLUX image server"
    assert (served[0]["host"], served[0]["port"]) == ("0.0.0.0", 8090)
    assert "alias of `imagewright serve --backend flux`" in capsys.readouterr().out


def test_flux_alias_takes_host_and_port_from_the_environment(served, monkeypatch):
    monkeypatch.setenv("MFLUX_SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("MFLUX_SERVER_PORT", "8092")
    _pretend_installed(monkeypatch, "mflux")
    assert _run(image_server.main) == 0
    assert (served[0]["host"], served[0]["port"]) == ("127.0.0.1", 8092)


def test_flux_alias_passes_idle_unload_to_imagewright(served, monkeypatch):
    monkeypatch.setenv("IMAGE_IDLE_UNLOAD_S", "300")
    _pretend_installed(monkeypatch, "mflux")
    assert _run(image_server.main) == 0
    assert served[0]["app"].state.server.idle_unload_s == 300


def test_flux_alias_without_mflux_names_the_pip_command(served, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "mflux", None)
    assert _run(image_server.main) == 1
    assert served == []
    assert "imagewright[serve,flux]" in capsys.readouterr().err


def test_flux_alias_without_imagewright_names_the_make_target(served, monkeypatch):
    monkeypatch.setitem(sys.modules, "imagewright", None)
    monkeypatch.setitem(sys.modules, "imagewright.cli", None)
    with pytest.raises(SystemExit) as stopped:
        image_server.main()
    assert "make image-server" in str(stopped.value.code)
    assert served == []


# --------------------------------------------------------------------- SDXL


def test_sdxl_alias_serves_imagewright_on_all_interfaces(served, monkeypatch, capsys):
    _pretend_installed(monkeypatch, *_SDXL_STACK)
    assert _run(sdxl_server.main) == 0
    assert len(served) == 1
    assert served[0]["app"].title == "imagewright SDXL-Lightning image server"
    assert (served[0]["host"], served[0]["port"]) == ("0.0.0.0", 8091)
    assert "alias of `imagewright serve --backend sdxl`" in capsys.readouterr().out


def test_sdxl_alias_takes_host_and_port_from_the_environment(served, monkeypatch):
    monkeypatch.setenv("SDXL_SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("SDXL_SERVER_PORT", "8093")
    _pretend_installed(monkeypatch, *_SDXL_STACK)
    assert _run(sdxl_server.main) == 0
    assert (served[0]["host"], served[0]["port"]) == ("127.0.0.1", 8093)


def test_sdxl_alias_without_imagewright_names_the_make_target(served, monkeypatch):
    monkeypatch.setitem(sys.modules, "imagewright", None)
    monkeypatch.setitem(sys.modules, "imagewright.cli", None)
    with pytest.raises(SystemExit) as stopped:
        sdxl_server.main()
    assert "make sdxl-server" in str(stopped.value.code)
    assert served == []
