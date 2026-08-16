"""Unit tests for gutenberg_kg.serve.sdxl_server — the portable image backend.

The module imports cleanly here with **no stubbing at all**: torch, diffusers
and uvicorn are deferred behind ``_torch()`` / ``_load_pipeline()`` / ``main()``,
so only an actual render needs the isolated ``.venv-sdxl``. That is the point of
the deferral, and the first test pins it — before this, torch was imported at
module scope, which made the whole module untestable outside that venv.

Only ``fastapi``/``pydantic`` are needed to import it, and both come from the
project's own ``image`` extra, which the CI test job installs.

Integration rather than unit: this exercises the serving surface, and it is
only importable when an optional extra is present. Hence both the
``integration`` mark (so ``-m "not integration"`` can deselect it) and the
``importorskip`` (so a checkout without the extra *skips* rather than failing
at collection, which aborts the entire run — the same reason ``test_cli.py``
guards on ``kg_rag``). CI installs ``image``, so these tests run there; it is
the local narrow install that used to break.
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed — integration test skipped")

from gutenberg_kg.serve import sdxl_server  # noqa: E402

pytestmark = pytest.mark.integration

# Modules that must not be imported when this one is, so it stays importable
# outside .venv-sdxl. torch and diffusers are the heavy pair; uvicorn is only
# needed to actually serve; huggingface_hub and safetensors ride along with
# diffusers.
_DEFERRED = {"torch", "diffusers", "uvicorn", "huggingface_hub", "safetensors"}


def _module_scope_imports() -> set[str]:
    """Top-level imports actually executed when the module is imported.

    Parsed from the source rather than probed via ``sys.modules``: this suite
    shares an interpreter with tests that legitimately import torch, so global
    module state says nothing about what *this* module pulls in. Imports inside
    functions are deferred by construction and so are not in ``tree.body``, and
    an ``if TYPE_CHECKING:`` block never runs, so both are skipped.
    """
    import ast

    tree = ast.parse(pathlib.Path(sdxl_server.__file__).read_text())
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.If):
            continue  # `if TYPE_CHECKING:` — not executed at runtime
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


class TestImportsWithoutTheHeavyStack:
    def test_no_heavy_module_is_imported_at_module_scope(self):
        # The regression this file exists to prevent: torch used to be imported
        # here, which made the module unimportable outside .venv-sdxl and so
        # untestable at all.
        assert _module_scope_imports() & _DEFERRED == set()

    def test_type_checking_block_may_still_reference_torch(self):
        # The `if TYPE_CHECKING: import torch` that types _device_dtype is fine
        # — it never executes — so the check above must not flag it.
        source = pathlib.Path(sdxl_server.__file__).read_text()
        assert "import torch" in source

    def test_torch_is_not_bound_on_the_module_at_runtime(self):
        # Complements the static check: _torch() returns the module rather than
        # binding it globally, so nothing re-exports it by accident.
        assert not hasattr(sdxl_server, "torch")

    def test_torch_helper_raises_a_directive_not_an_importerror(self):
        # `None` in sys.modules makes `import torch` raise ModuleNotFoundError,
        # so this exercises the real handler whether or not torch is installed.
        with patch.dict("sys.modules", {"torch": None}):
            with pytest.raises(RuntimeError, match="make sdxl-server"):
                sdxl_server._torch()


class TestParseSize:
    def test_parses_plain_size(self):
        assert sdxl_server._parse_size("768x512") == (768, 512)

    def test_parses_uppercase_x(self):
        assert sdxl_server._parse_size("1536X1024") == (1536, 1024)

    def test_accepts_arbitrary_dimensions(self):
        assert sdxl_server._parse_size("999x333") == (999, 333)

    @pytest.mark.parametrize("bad", [None, "", "1024", "axb", "1024x", "x1024", "1024x1024x1024"])
    def test_malformed_falls_back_to_default(self, bad):
        assert sdxl_server._parse_size(bad) == sdxl_server._DEFAULT_DIMS

    @pytest.mark.parametrize("bad", ["0x512", "512x0", "-1x512"])
    def test_non_positive_falls_back_to_default(self, bad):
        assert sdxl_server._parse_size(bad) == sdxl_server._DEFAULT_DIMS

    def test_default_dims_are_two_positive_ints(self):
        w, h = sdxl_server._DEFAULT_DIMS
        assert w > 0 and h > 0


class TestStepsFor:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [("sdxl_lightning_2", 2), ("sdxl_lightning_4", 4), ("sdxl_lightning_8", 8)],
    )
    def test_model_name_determines_steps(self, model, expected):
        assert sdxl_server._steps_for(model) == expected

    def test_model_wins_over_a_request_override(self):
        # Lightning UNets are distilled for a fixed step count — honouring a
        # per-request 30 would degrade the image, not improve it.
        assert sdxl_server._steps_for("sdxl_lightning_4", 30) == 4

    def test_unknown_model_honours_the_request(self):
        assert sdxl_server._steps_for("something-else", 6) == 6

    @pytest.mark.parametrize("requested", [None, 0, -1])
    def test_unknown_model_without_a_usable_request_defaults_to_four(self, requested):
        assert sdxl_server._steps_for("something-else", requested) == 4


class TestOffline:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", " Yes "])
    def test_truthy_values_enable_offline(self, value, monkeypatch):
        monkeypatch.setenv("SDXL_OFFLINE", value)
        assert sdxl_server._offline() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
    def test_other_values_leave_downloads_enabled(self, value, monkeypatch):
        monkeypatch.setenv("SDXL_OFFLINE", value)
        assert sdxl_server._offline() is False

    def test_unset_defaults_to_downloads_enabled(self, monkeypatch):
        # A fresh machine must be able to fetch weights, or the portable
        # backend is not portable — and `make up` now defaults to it wherever
        # mflux cannot run.
        monkeypatch.delenv("SDXL_OFFLINE", raising=False)
        assert sdxl_server._offline() is False


class TestDeviceDtype:
    @staticmethod
    def _torch(cuda: bool, mps: bool):
        t = MagicMock()
        t.cuda.is_available = MagicMock(return_value=cuda)
        t.backends.mps.is_available = MagicMock(return_value=mps)
        t.float16, t.float32 = "float16", "float32"
        return t

    def test_cuda_preferred(self):
        with patch.object(sdxl_server, "_torch", return_value=self._torch(True, True)):
            assert sdxl_server._device_dtype() == ("cuda", "float16")

    def test_mps_when_no_cuda(self):
        with patch.object(sdxl_server, "_torch", return_value=self._torch(False, True)):
            assert sdxl_server._device_dtype() == ("mps", "float16")

    def test_cpu_fallback(self):
        # The fallback that makes this backend portable where mflux is not.
        with patch.object(sdxl_server, "_torch", return_value=self._torch(False, False)):
            assert sdxl_server._device_dtype() == ("cpu", "float32")

    def test_mps_dtype_override(self, monkeypatch):
        monkeypatch.setenv("MPS_DTYPE", "float32")
        with patch.object(sdxl_server, "_torch", return_value=self._torch(False, True)):
            assert sdxl_server._device_dtype() == ("mps", "float32")

    def test_missing_mps_backend_attribute_is_survivable(self):
        t = MagicMock()
        t.cuda.is_available = MagicMock(return_value=False)
        t.backends = MagicMock(spec=[])  # no `mps` attribute at all
        t.float32 = "float32"
        with patch.object(sdxl_server, "_torch", return_value=t):
            assert sdxl_server._device_dtype() == ("cpu", "float32")


class TestRequestContract:
    def test_defaults_match_the_mflux_image_server(self):
        req = sdxl_server.ImageGenRequest(prompt="a candlelit study")
        assert req.size == "1024x1024"
        assert req.response_format == "b64_json"
        assert req.n == 1
        assert req.seed is None

    def test_list_models_reports_the_active_variant(self):
        body = sdxl_server.list_models()
        assert body["object"] == "list"
        assert body["data"][0]["id"] == sdxl_server._MODEL


class TestHealth:
    """The liveness route the endpoint probe and `make up` rely on."""

    def test_it_answers_without_touching_the_model(self):
        # The point of a health route on this server: SDXL weights are ~7 GB
        # and load lazily, so a probe that needed them would report "down"
        # for the entire window in which you most want to know the port is up.
        from fastapi.testclient import TestClient

        from gutenberg_kg.serve import sdxl_server

        with patch.object(sdxl_server, "_load_pipeline", side_effect=AssertionError("loaded!")):
            reply = TestClient(sdxl_server.app).get("/health")
        assert reply.status_code == 200
        assert reply.json()["status"] == "ok"
        assert reply.json()["backend"] == "sdxl-lightning"
