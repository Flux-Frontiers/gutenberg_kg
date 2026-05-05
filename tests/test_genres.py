"""Unit tests for gutenberg_kg.genres — registry load/save/mutate."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import gutenberg_kg.genres as genres_mod
from gutenberg_kg.genres import (
    _DEFAULTS,
    add_genre,
    seed_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_registry(tmp_path: Path):
    """Return a context manager that redirects _REGISTRY_PATH to a tmp file."""
    return patch.object(genres_mod, "_REGISTRY_PATH", tmp_path / "genres.json")


# ---------------------------------------------------------------------------
# seed_registry
# ---------------------------------------------------------------------------


def test_seed_registry_creates_file(tmp_path: Path):
    with _patch_registry(tmp_path):
        result = seed_registry()
    assert result is True
    registry_file = tmp_path / "genres.json"
    assert registry_file.exists()


def test_seed_registry_writes_defaults(tmp_path: Path):
    with _patch_registry(tmp_path):
        seed_registry()
    data = json.loads((tmp_path / "genres.json").read_text(encoding="utf-8"))
    assert "gutenberg" in data
    assert "ia" in data
    assert data["gutenberg"] == _DEFAULTS["gutenberg"]


def test_seed_registry_returns_false_when_exists(tmp_path: Path):
    registry_file = tmp_path / "genres.json"
    registry_file.write_text("{}", encoding="utf-8")
    with _patch_registry(tmp_path):
        result = seed_registry()
    assert result is False


def test_seed_registry_force_overwrites(tmp_path: Path):
    registry_file = tmp_path / "genres.json"
    registry_file.write_text('{"gutenberg": []}', encoding="utf-8")
    with _patch_registry(tmp_path):
        result = seed_registry(force=True)
    assert result is True
    data = json.loads(registry_file.read_text(encoding="utf-8"))
    assert data["gutenberg"] == _DEFAULTS["gutenberg"]


# ---------------------------------------------------------------------------
# add_genre
# ---------------------------------------------------------------------------


def test_add_genre_adds_new_genre(tmp_path: Path):
    with _patch_registry(tmp_path):
        result = add_genre("new-genre", "gutenberg")
    assert result is True
    data = json.loads((tmp_path / "genres.json").read_text(encoding="utf-8"))
    assert "new-genre" in data["gutenberg"]


def test_add_genre_returns_false_if_already_present(tmp_path: Path):
    existing = {"gutenberg": ["ancient-classical"], "ia": []}
    (tmp_path / "genres.json").write_text(json.dumps(existing), encoding="utf-8")
    with _patch_registry(tmp_path):
        result = add_genre("ancient-classical", "gutenberg")
    assert result is False


def test_add_genre_creates_new_source_key(tmp_path: Path):
    with _patch_registry(tmp_path):
        result = add_genre("my-new-source-genre", "my-source")
    assert result is True
    data = json.loads((tmp_path / "genres.json").read_text(encoding="utf-8"))
    assert "my-new-source-genre" in data["my-source"]


def test_add_genre_preserves_existing_genres(tmp_path: Path):
    existing = {"gutenberg": ["ancient-classical"], "ia": ["audel-electric"]}
    (tmp_path / "genres.json").write_text(json.dumps(existing), encoding="utf-8")
    with _patch_registry(tmp_path):
        add_genre("new-genre", "gutenberg")
    data = json.loads((tmp_path / "genres.json").read_text(encoding="utf-8"))
    assert "ancient-classical" in data["gutenberg"]
    assert "new-genre" in data["gutenberg"]
    assert "audel-electric" in data["ia"]


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_gutenberg_genres_is_list():
    from gutenberg_kg.genres import GUTENBERG_GENRES

    assert isinstance(GUTENBERG_GENRES, list)
    assert len(GUTENBERG_GENRES) > 0


def test_ia_genres_is_list():
    from gutenberg_kg.genres import IA_GENRES

    assert isinstance(IA_GENRES, list)
    assert len(IA_GENRES) > 0


def test_all_genres_contains_gutenberg_and_ia():
    from gutenberg_kg.genres import ALL_GENRES, GUTENBERG_GENRES, IA_GENRES

    for g in GUTENBERG_GENRES:
        assert g in ALL_GENRES
    for g in IA_GENRES:
        assert g in ALL_GENRES


def test_defaults_have_known_genres():
    assert "ancient-classical" in _DEFAULTS["gutenberg"]
    assert "shakespeare" in _DEFAULTS["gutenberg"]
    assert "audel-electric" in _DEFAULTS["ia"]
