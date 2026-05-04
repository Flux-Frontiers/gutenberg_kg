"""Tests for cli/options.py — constants and option factory decorators."""

from pathlib import Path

import click
from click.testing import CliRunner

from gutenberg_kg.cli.options import (
    ALL_GENRES,
    ALL_IA_GENRES,
    CORPUS_ROOT,
    REPO_ROOT,
    dry_run_option,
    force_option,
    genre_option,
    push_option,
)

# ---------------------------------------------------------------------------
# Genre lists
# ---------------------------------------------------------------------------


def test_all_genres_is_list():
    assert isinstance(ALL_GENRES, list)


def test_all_genres_non_empty():
    assert len(ALL_GENRES) > 0


def test_all_genres_contains_known():
    expected = {"shakespeare", "english-literature", "american-literature", "philosophy"}
    assert expected.issubset(set(ALL_GENRES))


def test_all_genres_no_duplicates():
    assert len(ALL_GENRES) == len(set(ALL_GENRES))


def test_all_ia_genres_is_list():
    assert isinstance(ALL_IA_GENRES, list)


def test_all_ia_genres_contains_audel():
    assert "audel-electric" in ALL_IA_GENRES


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------


def test_repo_root_is_path():
    assert isinstance(REPO_ROOT, Path)


def test_corpus_root_is_path():
    assert isinstance(CORPUS_ROOT, Path)


def test_corpus_root_relative_to_repo_root():
    assert CORPUS_ROOT == REPO_ROOT / "corpus"


def test_repo_root_is_absolute():
    assert REPO_ROOT.is_absolute()


# ---------------------------------------------------------------------------
# Option factories — produce callable decorators without raising
# ---------------------------------------------------------------------------


def test_genre_option_single_returns_callable():
    opt = genre_option(multiple=False)
    assert callable(opt)


def test_genre_option_multiple_returns_callable():
    opt = genre_option(multiple=True)
    assert callable(opt)


def test_genre_option_single_applied_to_command():
    @click.command()
    @genre_option(multiple=False)
    def _cmd(genre):
        pass

    assert isinstance(_cmd, click.Command)


def test_genre_option_multiple_applied_to_command():
    @click.command()
    @genre_option(multiple=True)
    def _cmd(genre):
        pass

    assert isinstance(_cmd, click.Command)


def test_dry_run_option_returns_callable():
    opt = dry_run_option()
    assert callable(opt)


def test_force_option_returns_callable():
    opt = force_option()
    assert callable(opt)


def test_push_option_returns_callable():
    opt = push_option()
    assert callable(opt)


def test_dry_run_option_applied_to_command():
    @click.command()
    @dry_run_option()
    def _cmd(dry_run):
        pass

    result = CliRunner().invoke(_cmd, ["--help"])
    assert "--dry-run" in result.output
