"""Unit tests for gutenberg_kg.serve.sdxl_server — the portable image backend.

The module imports cleanly here with **no stubbing at all**: torch, diffusers
and uvicorn are deferred behind ``_torch()`` / ``_load_pipeline()`` / ``main()``,
so only an actual render needs the isolated ``.venv-sdxl``. That is the point of
the deferral, and the first test pins it — before this, torch was imported at
module scope, which made the whole module untestable outside that venv.

Only ``fastapi``/``pydantic`` are needed to import it, and both come from the
project's own ``image`` extra, which the CI test job installs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gutenberg_kg.serve import sdxl_server


class TestImportsWithoutTheHeavyStack:
    def test_module_imported_without_torch_or_diffusers(self):
        import sys

        assert "torch" not in sys.modules
        assert "diffusers" not in sys.modules

    def test_torch_helper_raises_a_directive_not_an_importerror(self):
        with patch.dict("sys.modules", {"torch": None}):
            with pytest.raises(RuntimeError, match="make sdxl-server"):
                sdxl_server._torch()

    def test_uvicorn_not_required_to_import(self):
        import sys

        assert "uvicorn" not in sys.modules


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
