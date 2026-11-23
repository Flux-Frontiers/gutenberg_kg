# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Which server `gutenkg-image-server` and `gutenkg-sdxl-server` run.

Both serve through imagewright when the environment has it, and through this
repo's own code when it does not. The second case is the one that matters in
production: `.venv-image` is an editable install kept alive by launchd, so a
`git pull` changes this code before anyone refreshes the environment, and a
server that could not start there loops (2026-11-17).

Only `uvicorn.run` is faked: it would bind a port and never return.
"""

from __future__ import annotations

import sys
from importlib.machinery import ModuleSpec
from types import ModuleType

import pytest

from gutenberg_kg import image_gen
from gutenberg_kg.serve import image_server, sdxl_server


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Record what each server hands to ``uvicorn.run`` instead of serving."""
    import uvicorn

    calls: list[dict] = []

    def run(app, host: str, port: int) -> None:
        calls.append({"app": app, "host": host, "port": port})

    monkeypatch.setattr(uvicorn, "run", run)
    for name in (
        "MFLUX_SERVER_HOST",
        "MFLUX_SERVER_PORT",
        "SDXL_SERVER_HOST",
        "SDXL_SERVER_PORT",
        "IMAGE_OUTPUT_DIR",
        "IMAGE_PRELOAD",
        "IMAGE_IDLE_UNLOAD_S",
    ):
        monkeypatch.delenv(name, raising=False)
    return calls


@pytest.fixture
def no_model_loads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fail the test's expectations if the built-in code loads a model."""
    loads: list[str] = []
    monkeypatch.setattr(image_gen, "_load_model", lambda name: loads.append(name))
    monkeypatch.setattr(sdxl_server, "_load_pipeline", lambda: loads.append("sdxl"))
    return loads


def _block(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    for name in names:
        monkeypatch.setitem(sys.modules, name, None)


def _pretend_installed(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Make ``importlib.util.find_spec`` see these packages, without their code."""
    for name in names:
        module = ModuleType(name)
        module.__spec__ = ModuleSpec(name, None)
        monkeypatch.setitem(sys.modules, name, module)


def _title(app) -> str:
    return app.title


# --------------------------------------------------------------------- FLUX


def test_flux_falls_back_when_imagewright_is_absent(served, no_model_loads, monkeypatch, capsys):
    _block(monkeypatch, "imagewright", "imagewright.flux_server")
    image_server.main()
    assert served == [{"app": image_server.app, "host": "0.0.0.0", "port": 8090}]
    out = capsys.readouterr().out
    assert "imagewright cannot serve here" in out
    assert "serving with the built-in FLUX server" in out
    assert "make image-server" in out


def test_flux_falls_back_when_mflux_is_absent(served, no_model_loads, monkeypatch, capsys):
    """imagewright is installed but its flux extra is not: still the built-in server."""
    _block(monkeypatch, "mflux")
    image_server.main()
    assert served[0]["app"] is image_server.app
    assert "MissingExtraError" in capsys.readouterr().out


def test_flux_falls_back_when_imagewright_is_broken(served, no_model_loads, monkeypatch, capsys):
    """Any failure, not only a missing package, keeps the server up."""
    from imagewright import flux_server

    def boom() -> None:
        raise RuntimeError("half-installed")

    _pretend_installed(monkeypatch, "mflux")
    monkeypatch.setattr(flux_server, "require_extras", boom)
    image_server.main()
    assert served[0]["app"] is image_server.app
    assert "RuntimeError: half-installed" in capsys.readouterr().out


def test_flux_serves_through_imagewright_when_it_can(served, no_model_loads, monkeypatch, capsys):
    _pretend_installed(monkeypatch, "mflux")
    image_server.main()
    assert len(served) == 1
    assert served[0]["app"] is not image_server.app
    assert _title(served[0]["app"]) == "imagewright FLUX image server"
    assert (served[0]["host"], served[0]["port"]) == ("0.0.0.0", 8090)
    assert "serving FLUX through imagewright" in capsys.readouterr().out
    assert no_model_loads == []


def test_flux_host_and_port_come_from_the_environment_on_both_paths(served, monkeypatch):
    monkeypatch.setenv("MFLUX_SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("MFLUX_SERVER_PORT", "8092")
    _pretend_installed(monkeypatch, "mflux")
    image_server.main()
    _block(monkeypatch, "imagewright", "imagewright.flux_server")
    image_server.main()
    assert [(c["host"], c["port"]) for c in served] == [("127.0.0.1", 8092)] * 2


def test_flux_keeps_this_repos_output_folder_through_imagewright(served, monkeypatch):
    import os

    _pretend_installed(monkeypatch, "mflux")
    image_server.main()
    assert os.environ["IMAGE_OUTPUT_DIR"] == "/tmp/gutenberg_images"
    assert str(served[0]["app"].state.server.output_dir) == "/tmp/gutenberg_images"


def test_flux_preload_loads_once_and_only_on_the_built_in_path(served, no_model_loads, monkeypatch):
    """Importing the module loads nothing; imagewright's server does its own preload."""
    monkeypatch.setattr(image_server, "_PRELOAD", True)
    _pretend_installed(monkeypatch, "mflux")
    image_server.main()
    assert no_model_loads == []  # imagewright path: the built-in loader stays out of it

    _block(monkeypatch, "imagewright", "imagewright.flux_server")
    image_server.main()
    assert no_model_loads == [image_server._MODEL_NAME]


# --------------------------------------------------------------------- SDXL

_SDXL_STACK = ("torch", "diffusers", "transformers", "accelerate", "safetensors")


def test_sdxl_falls_back_when_imagewright_is_absent(served, no_model_loads, monkeypatch, capsys):
    _block(monkeypatch, "imagewright", "imagewright.sdxl_server")
    sdxl_server.main()
    assert served == [{"app": sdxl_server.app, "host": "0.0.0.0", "port": 8091}]
    assert no_model_loads == ["sdxl"]  # the built-in server builds its pipeline first
    out = capsys.readouterr().out
    assert "serving with the built-in SDXL server" in out
    assert "make sdxl-server" in out


def test_sdxl_falls_back_when_its_stack_is_absent(served, no_model_loads, monkeypatch, capsys):
    _block(monkeypatch, "diffusers")
    sdxl_server.main()
    assert served[0]["app"] is sdxl_server.app
    assert "MissingExtraError" in capsys.readouterr().out


def test_sdxl_serves_through_imagewright_when_it_can(served, no_model_loads, monkeypatch, capsys):
    _pretend_installed(monkeypatch, *_SDXL_STACK)
    sdxl_server.main()
    assert len(served) == 1
    assert served[0]["app"] is not sdxl_server.app
    assert _title(served[0]["app"]) == "imagewright SDXL-Lightning image server"
    assert (served[0]["host"], served[0]["port"]) == ("0.0.0.0", 8091)
    assert "serving SDXL through imagewright" in capsys.readouterr().out
    assert no_model_loads == []


def test_sdxl_host_and_port_come_from_the_environment(served, monkeypatch):
    monkeypatch.setenv("SDXL_SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("SDXL_SERVER_PORT", "8093")
    _pretend_installed(monkeypatch, *_SDXL_STACK)
    sdxl_server.main()
    assert (served[0]["host"], served[0]["port"]) == ("127.0.0.1", 8093)
