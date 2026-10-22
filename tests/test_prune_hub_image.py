"""prune_hub_image.py: which digests a publish deletes, and when it does nothing."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "prune_hub_image.py"

# scripts/ is not a package, so load the file straight from its path.
_spec = importlib.util.spec_from_file_location("prune_hub_image", _SCRIPT)
assert _spec is not None and _spec.loader is not None
prune = importlib.util.module_from_spec(_spec)
sys.modules["prune_hub_image"] = prune
_spec.loader.exec_module(prune)

IMAGE = "docker.io/egsuchanek/corpus-gutenberg:latest"
OLD, NEW = "sha256:" + "a" * 64, "sha256:" + "b" * 64
INDEX = {
    "manifests": [
        {"digest": "sha256:amd64", "platform": {"architecture": "amd64"}},
        {"digest": "sha256:arm64", "platform": {"architecture": "arm64"}},
        {"digest": "sha256:att", "platform": {"architecture": "unknown"}},
    ]
}


@pytest.mark.parametrize(
    ("image", "parsed"),
    [
        (IMAGE, ("egsuchanek/corpus-gutenberg", "latest")),
        ("egsuchanek/corpus-gutenberg", ("egsuchanek/corpus-gutenberg", "latest")),
        (
            "docker.io/egsuchanek/corpus-gutenberg:shakespeare-demo",
            ("egsuchanek/corpus-gutenberg", "shakespeare-demo"),
        ),
        ("ghcr.io/someone/image:latest", None),
        ("corpus-gutenberg:latest", None),
    ],
)
def test_only_docker_hub_images_are_handled(image, parsed):
    assert prune.parse_image(image) == parsed


def test_the_replaced_index_goes_first_then_what_it_listed():
    assert prune.plan(OLD, NEW, INDEX) == [OLD, "sha256:amd64", "sha256:arm64", "sha256:att"]


def test_nothing_is_deleted_when_the_push_did_not_move_the_tag():
    assert prune.plan(OLD, OLD, INDEX) == []
    assert prune.plan("", NEW, INDEX) == []


def test_a_manifest_the_new_tag_points_at_is_never_listed():
    assert NEW not in prune.plan(OLD, NEW, {"manifests": [{"digest": NEW}]})


def test_a_single_platform_image_has_no_children():
    assert prune.plan(OLD, NEW, {"config": {}}) == [OLD]


def test_prune_without_a_token_skips_and_says_what_to_set(monkeypatch, capsys):
    monkeypatch.delenv("DOCKERHUB_USERNAME", raising=False)
    monkeypatch.delenv("DOCKERHUB_TOKEN", raising=False)
    assert prune.main(["prune", IMAGE, OLD]) == 0
    assert "DOCKERHUB_TOKEN" in capsys.readouterr().out


@pytest.mark.parametrize(("image", "old"), [(IMAGE, ""), ("ghcr.io/someone/image:latest", OLD)])
def test_prune_does_nothing_without_an_old_image_or_off_docker_hub(image, old, capsys):
    assert prune.main(["prune", image, old]) == 0
    assert "nothing" in capsys.readouterr().out


def test_digest_off_docker_hub_is_empty(capsys):
    assert prune.main(["digest", "ghcr.io/someone/image:latest"]) == 0
    assert capsys.readouterr().out == "\n"
