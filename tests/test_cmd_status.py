"""Tests for gutenberg_kg.cli.cmd_status — pure helpers and CLI."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("kg_rag", reason="kg_rag not installed — integration test skipped")

from click.testing import CliRunner

from gutenberg_kg.cli.cmd_status import (
    _collect_genre_stats,
    _count_book_dirs,
    _fmt_badge_nodes,
    _genre_corpus_name,
    _sqlite_counts,
    _update_readme_badges,
)
from gutenberg_kg.cli.main import cli

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_registry(tmp_path: Path) -> Path:
    """Minimal KGRAG registry: english-literature has 2 live books; science-fiction has none."""
    db1 = tmp_path / "book1.sqlite"
    db2 = tmp_path / "book2.sqlite"
    for db, n, e in [(db1, 10, 20), (db2, 30, 50)]:
        with sqlite3.connect(db) as con:
            con.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY)")
            con.execute("CREATE TABLE edges (a INTEGER, b INTEGER)")
            con.executemany("INSERT INTO nodes VALUES (?)", [(i,) for i in range(n)])
            con.executemany("INSERT INTO edges VALUES (?,?)", [(i, i + 1) for i in range(e)])

    reg = tmp_path / "registry.sqlite"
    with sqlite3.connect(reg) as con:
        con.execute("CREATE TABLE kg_entries (id TEXT, sqlite_path TEXT)")
        con.execute("CREATE TABLE corpora (name TEXT, kg_ids TEXT)")
        con.executemany(
            "INSERT INTO kg_entries VALUES (?,?)",
            [("kg-1", str(db1)), ("kg-2", str(db2))],
        )
        con.execute(
            "INSERT INTO corpora VALUES (?,?)",
            ("gutenberg-english-literature", json.dumps(["kg-1", "kg-2"])),
        )
        con.execute(
            "INSERT INTO corpora VALUES (?,?)",
            ("gutenberg-science-fiction", json.dumps(["kg-missing"])),
        )
    return reg


_SAMPLE_README = """\
# GutenbergKG

![corpus](https://img.shields.io/badge/corpus-178%20books-blue)
![nodes](https://img.shields.io/badge/nodes-25K-blue)
![edges](https://img.shields.io/badge/edges-100K-blue)

Some other content.
"""


# ---------------------------------------------------------------------------
# _genre_corpus_name
# ---------------------------------------------------------------------------


def test_genre_corpus_name_basic():
    assert _genre_corpus_name("english-literature") == "gutenberg-english-literature"


def test_genre_corpus_name_shakespeare():
    assert _genre_corpus_name("shakespeare") == "gutenberg-shakespeare"


def test_genre_corpus_name_prefix_not_doubled():
    name = _genre_corpus_name("philosophy")
    assert name.count("gutenberg-") == 1


# ---------------------------------------------------------------------------
# _count_book_dirs
# ---------------------------------------------------------------------------


def test_count_book_dirs_nonexistent(tmp_path: Path):
    assert _count_book_dirs(tmp_path / "missing") == 0


def test_count_book_dirs_empty(tmp_path: Path):
    d = tmp_path / "genre"
    d.mkdir()
    assert _count_book_dirs(d) == 0


def test_count_book_dirs_with_two_dirs(tmp_path: Path):
    d = tmp_path / "genre"
    d.mkdir()
    (d / "book-one").mkdir()
    (d / "book-two").mkdir()
    assert _count_book_dirs(d) == 2


def test_count_book_dirs_ignores_hidden(tmp_path: Path):
    d = tmp_path / "genre"
    d.mkdir()
    (d / "book-one").mkdir()
    (d / ".dockg").mkdir()
    assert _count_book_dirs(d) == 1


def test_count_book_dirs_ignores_files(tmp_path: Path):
    d = tmp_path / "genre"
    d.mkdir()
    (d / "book-one").mkdir()
    (d / "catalog.json").write_text("{}")
    assert _count_book_dirs(d) == 1


# ---------------------------------------------------------------------------
# _sqlite_counts
# ---------------------------------------------------------------------------


def test_sqlite_counts_none_path():
    assert _sqlite_counts(None) == (0, 0)


def test_sqlite_counts_nonexistent():
    assert _sqlite_counts("/tmp/definitely_no_such_db_xyz.sqlite") == (0, 0)


def test_sqlite_counts_valid_db(tmp_path: Path):
    db = tmp_path / "graph.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE edges (a INTEGER, b INTEGER)")
        con.executemany("INSERT INTO nodes VALUES (?)", [(i,) for i in range(5)])
        con.executemany("INSERT INTO edges VALUES (?,?)", [(i, i + 1) for i in range(3)])
    assert _sqlite_counts(str(db)) == (5, 3)


def test_sqlite_counts_empty_tables(tmp_path: Path):
    db = tmp_path / "graph.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE nodes (id INTEGER PRIMARY KEY)")
        con.execute("CREATE TABLE edges (a INTEGER, b INTEGER)")
    assert _sqlite_counts(str(db)) == (0, 0)


def test_sqlite_counts_missing_table_returns_zero(tmp_path: Path):
    db = tmp_path / "graph.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE other (id INTEGER PRIMARY KEY)")
    assert _sqlite_counts(str(db)) == (0, 0)


# ---------------------------------------------------------------------------
# _fmt_badge_nodes
# ---------------------------------------------------------------------------


def test_fmt_badge_nodes_zero():
    assert _fmt_badge_nodes(0) == "0"


def test_fmt_badge_nodes_under_thousand():
    assert _fmt_badge_nodes(999) == "999"


def test_fmt_badge_nodes_exactly_thousand():
    assert _fmt_badge_nodes(1_000) == "1K"


def test_fmt_badge_nodes_thousands():
    assert _fmt_badge_nodes(25_000) == "25K"


def test_fmt_badge_nodes_just_under_million():
    assert _fmt_badge_nodes(999_999) == "999K"


def test_fmt_badge_nodes_million():
    assert _fmt_badge_nodes(1_000_000) == "1.0M"


def test_fmt_badge_nodes_millions():
    assert _fmt_badge_nodes(2_500_000) == "2.5M"


# ---------------------------------------------------------------------------
# _update_readme_badges
# ---------------------------------------------------------------------------


def test_update_readme_badges_updates_books(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(_SAMPLE_README, encoding="utf-8")
    _update_readme_badges(readme, total_books=200, total_nodes=25_000, total_edges=100_000)
    assert "corpus-200%20books" in readme.read_text(encoding="utf-8")


def test_update_readme_badges_updates_nodes(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(_SAMPLE_README, encoding="utf-8")
    _update_readme_badges(readme, total_books=178, total_nodes=30_000, total_edges=100_000)
    assert "nodes-30K" in readme.read_text(encoding="utf-8")


def test_update_readme_badges_updates_edges(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(_SAMPLE_README, encoding="utf-8")
    _update_readme_badges(readme, total_books=178, total_nodes=25_000, total_edges=2_000_000)
    assert "edges-2.0M" in readme.read_text(encoding="utf-8")


def test_update_readme_badges_returns_true_on_change(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(_SAMPLE_README, encoding="utf-8")
    changed = _update_readme_badges(
        readme, total_books=200, total_nodes=25_000, total_edges=100_000
    )
    assert changed is True


def test_update_readme_badges_returns_false_when_unchanged(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text(_SAMPLE_README, encoding="utf-8")
    # Values already match the sample README badges
    changed = _update_readme_badges(
        readme, total_books=178, total_nodes=25_000, total_edges=100_000
    )
    assert changed is False


# ---------------------------------------------------------------------------
# _collect_genre_stats
# ---------------------------------------------------------------------------


def test_collect_genre_stats_returns_list(fake_registry: Path):
    stats = _collect_genre_stats(fake_registry)
    assert isinstance(stats, list)
    assert len(stats) > 0


def test_collect_genre_stats_known_genre_books(fake_registry: Path):
    stats = _collect_genre_stats(fake_registry)
    lit = next(s for s in stats if s["corpus"] == "gutenberg-english-literature")
    assert lit["books"] == 2


def test_collect_genre_stats_known_genre_nodes(fake_registry: Path):
    stats = _collect_genre_stats(fake_registry)
    lit = next(s for s in stats if s["corpus"] == "gutenberg-english-literature")
    assert lit["nodes"] == 40  # 10 + 30


def test_collect_genre_stats_known_genre_edges(fake_registry: Path):
    stats = _collect_genre_stats(fake_registry)
    lit = next(s for s in stats if s["corpus"] == "gutenberg-english-literature")
    assert lit["edges"] == 70  # 20 + 50


def test_collect_genre_stats_missing_sqlite_zero_books(fake_registry: Path):
    stats = _collect_genre_stats(fake_registry)
    scifi = next(s for s in stats if s["corpus"] == "gutenberg-science-fiction")
    assert scifi["books"] == 0
    assert scifi["nodes"] == 0


def test_collect_genre_stats_unregistered_genre_zero(fake_registry: Path):
    stats = _collect_genre_stats(fake_registry)
    # Philosophy has no entry in the fake registry
    phil = next(s for s in stats if s["corpus"] == "gutenberg-philosophy")
    assert phil["books"] == 0
    assert phil["nodes"] == 0


def test_collect_genre_stats_all_genres_present(fake_registry: Path):
    from gutenberg_kg.cli.cmd_status import _GENRE_LABELS

    stats = _collect_genre_stats(fake_registry)
    corpora = {s["corpus"] for s in stats}
    assert corpora == set(_GENRE_LABELS.keys())


# ---------------------------------------------------------------------------
# CLI: status --help
# ---------------------------------------------------------------------------


def test_status_help():
    result = CliRunner().invoke(cli, ["status", "--help"])
    assert result.exit_code == 0


def test_status_help_shows_options():
    result = CliRunner().invoke(cli, ["status", "--help"])
    for flag in ("--json", "--update-readme", "--registry"):
        assert flag in result.output, f"expected {flag!r} in status --help"


# ---------------------------------------------------------------------------
# CLI: status — registry errors
# ---------------------------------------------------------------------------


def test_status_missing_registry_nonzero_exit():
    result = CliRunner().invoke(cli, ["status", "--registry", "/tmp/no_such_reg_xyz.sqlite"])
    assert result.exit_code != 0


def test_status_missing_registry_error_message():
    result = CliRunner().invoke(cli, ["status", "--registry", "/tmp/no_such_reg_xyz.sqlite"])
    assert "Registry not found" in result.output


# ---------------------------------------------------------------------------
# CLI: status --json
# ---------------------------------------------------------------------------


def test_status_json_exit_zero(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_status as mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    result = CliRunner().invoke(cli, ["status", "--json", "--registry", str(fake_registry)])
    assert result.exit_code == 0, result.output


def test_status_json_valid_json(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_status as mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    result = CliRunner().invoke(cli, ["status", "--json", "--registry", str(fake_registry)])
    data = json.loads(result.output)
    assert data["kind"] == "corpus_status"


def test_status_json_totals(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_status as mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    result = CliRunner().invoke(cli, ["status", "--json", "--registry", str(fake_registry)])
    totals = json.loads(result.output)["totals"]
    assert totals["books"] == 2
    assert totals["nodes"] == 40
    assert totals["edges"] == 70


def test_status_json_has_genres(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_status as mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    result = CliRunner().invoke(cli, ["status", "--json", "--registry", str(fake_registry)])
    data = json.loads(result.output)
    assert isinstance(data["genres"], list)
    assert len(data["genres"]) > 0


def test_status_json_author_count(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_status as mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    authors = tmp_path / "authors"
    authors.mkdir()
    (authors / "twain").mkdir()
    (authors / "dickens").mkdir()
    result = CliRunner().invoke(cli, ["status", "--json", "--registry", str(fake_registry)])
    data = json.loads(result.output)
    assert data["totals"]["authors"] == 2


# ---------------------------------------------------------------------------
# CLI: status --update-readme
# ---------------------------------------------------------------------------


def test_status_update_readme_reports_change(fake_registry: Path, monkeypatch, tmp_path: Path):
    import gutenberg_kg.cli.cmd_status as mod

    monkeypatch.setattr(mod, "CORPUS_ROOT", tmp_path)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "authors").mkdir()
    (tmp_path / "README.md").write_text(_SAMPLE_README, encoding="utf-8")

    result = CliRunner().invoke(
        cli, ["status", "--json", "--update-readme", "--registry", str(fake_registry)]
    )
    assert result.exit_code == 0, result.output
    assert "README.md" in result.output
