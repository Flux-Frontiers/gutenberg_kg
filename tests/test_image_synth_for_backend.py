"""A request's ``image_backend`` override in the worker (``image_synth_for_backend``).

The chat UI's Local/OpenAI picker sends ``image_backend``; the synthesizer it
gets must be configured from the environment exactly as the worker's default
is. Until 1.43.0 the override was built by hand and dropped ``IMAGE_STEPS``
and the ``GUTENKG_IMAGE_ENDPOINT`` fallback; Compose's ``IMAGE_STEPS=4``
matched the hardcoded default, so nothing showed it.
"""

from __future__ import annotations

import pytest
from imagewright import ImageBackend, ImageConfig, ImageSynthesizer

from gutenberg_kg.serve.image_backends import image_synth_for_backend

_ENV = (
    "IMAGE_BACKEND",
    "IMAGE_ENDPOINT",
    "GUTENKG_IMAGE_ENDPOINT",
    "IMAGE_STEPS",
    "IMAGE_MODEL",
    "GUTENKG_IMAGE_MODEL",
    "IMAGE_API_KEY",
    "OPENAI_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


def _default(backend: ImageBackend = ImageBackend.MFLUX_SERVE) -> ImageSynthesizer:
    return ImageSynthesizer(ImageConfig(backend=backend, server_url="http://default:8090"))


@pytest.mark.parametrize("name", ["", "   ", "no-such-backend"])
def test_empty_or_unknown_name_gives_the_default(name):
    default = _default()
    assert image_synth_for_backend(name, default) is default


@pytest.mark.parametrize("name", ["mflux-serve", " MFLUX-SERVE "])
def test_the_defaults_own_backend_reuses_it(name):
    default = _default()
    assert image_synth_for_backend(name, default) is default


def test_mflux_serve_override_reads_steps_and_endpoint_fallback(monkeypatch):
    monkeypatch.setenv("GUTENKG_IMAGE_ENDPOINT", "http://host.docker.internal:8090")
    monkeypatch.setenv("IMAGE_STEPS", "8")
    synth = image_synth_for_backend("mflux-serve", _default(ImageBackend.OPENAI))
    cfg = synth._cfg  # pylint: disable=protected-access
    assert cfg.backend is ImageBackend.MFLUX_SERVE
    assert cfg.resolved_server_url() == "http://host.docker.internal:8090"
    assert cfg.steps == 8


def test_image_endpoint_wins_over_the_fallback(monkeypatch):
    monkeypatch.setenv("IMAGE_ENDPOINT", "http://primary:8090")
    monkeypatch.setenv("GUTENKG_IMAGE_ENDPOINT", "http://fallback:8090")
    synth = image_synth_for_backend("mflux-serve", _default(ImageBackend.OPENAI))
    assert synth._cfg.resolved_server_url() == "http://primary:8090"  # pylint: disable=protected-access


@pytest.mark.parametrize("key_var", ["IMAGE_API_KEY", "OPENAI_API_KEY"])
def test_openai_override_gets_the_key(monkeypatch, key_var):
    monkeypatch.setenv(key_var, "sk-test")
    synth = image_synth_for_backend("openai", _default())
    cfg = synth._cfg  # pylint: disable=protected-access
    assert cfg.backend is ImageBackend.OPENAI
    assert cfg.api_key == "sk-test"


def test_switching_backend_drops_the_defaults_model(monkeypatch):
    # IMAGE_MODEL names the default backend's model; OpenAI must not be sent it.
    monkeypatch.setenv("IMAGE_MODEL", "flux2-klein-4b")
    synth = image_synth_for_backend("openai", _default())
    assert synth._cfg.resolved_model() == "gpt-image-1"  # pylint: disable=protected-access
