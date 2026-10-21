"""The worker's book-scoped ``corpus`` values.

The handler starts the worker when it is imported, so the scope rules live in
:mod:`gutenberg_kg.serve.scope` and are tested here without it.
"""

from __future__ import annotations

import sqlite3

from gutenberg_kg.diary_meta import DIARY_META
from gutenberg_kg.serve.scope import (
    dense_scope_sql,
    diary_slug_for_key,
    keep_in_scope,
    resolve_corpus,
    scope_prefix,
)

# Built from DIARY_META, never retyped: the title carries a real em dash.
PEPYS_KEY = "diaries/" + DIARY_META["pepys-complete"]["title"]
PLUTARCH = "philosophy/Plutarch's Morals"
CATALOG = {
    "philosophy/Meditations",
    PLUTARCH,
    "philosophy/A_B",
    PEPYS_KEY,
}
GENRES = {"philosophy", "diaries"}


class TestScopePrefix:
    def test_book_wins_over_genre(self):
        assert scope_prefix("philosophy", "philosophy/Meditations") == "philosophy/Meditations/"

    def test_genre_alone(self):
        assert scope_prefix("philosophy", None) == "philosophy/"

    def test_neither_means_no_prefix(self):
        assert scope_prefix(None, None) is None


class TestDenseScopeSql:
    def test_apostrophe_is_escaped(self):
        frag = dense_scope_sql(scope_prefix(None, PLUTARCH))
        assert frag == " AND file_path LIKE 'philosophy/Plutarch''s Morals/%'"

    def test_escaped_fragment_is_valid_sql_and_matches(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE t (file_path TEXT)")
        con.executemany(
            "INSERT INTO t VALUES (?)",
            [(f"{PLUTARCH}/morals.md",), ("philosophy/Meditations/m.md",)],
        )
        frag = dense_scope_sql(scope_prefix(None, PLUTARCH))
        rows = con.execute(f"SELECT file_path FROM t WHERE 1=1{frag}").fetchall()  # noqa: S608
        assert rows == [(f"{PLUTARCH}/morals.md",)]


class TestKeepInScope:
    def test_drops_a_sibling_a_like_wildcard_would_match(self):
        # LIKE 'philosophy/A_B/%' also matches 'philosophy/AxB/...'.
        rows = [
            {"id": "1", "file_path": "philosophy/A_B/a.md"},
            {"id": "2", "file_path": "philosophy/AxB/a.md"},
        ]
        kept = keep_in_scope(rows, scope_prefix(None, "philosophy/A_B"))
        assert [r["id"] for r in kept] == ["1"]

    def test_drops_a_book_whose_name_extends_the_prefix(self):
        rows = [{"file_path": "philosophy/Meditations II/a.md"}]
        assert keep_in_scope(rows, "philosophy/Meditations/") == []

    def test_no_prefix_keeps_everything(self):
        rows = [{"file_path": "x/y/z.md"}, {"file_path": ""}]
        assert keep_in_scope(rows, None) == rows


class TestDiarySlug:
    def test_pepys_key_resolves(self):
        assert diary_slug_for_key(PEPYS_KEY) == "pepys-complete"

    def test_every_diary_resolves_to_its_slug(self):
        for slug, meta in DIARY_META.items():
            assert diary_slug_for_key("diaries/" + meta["title"]) == slug

    def test_unknown_diary_title(self):
        assert diary_slug_for_key("diaries/The Diary of Nobody") is None

    def test_not_a_diary_key(self):
        assert diary_slug_for_key("philosophy/Meditations") is None


class TestResolveCorpus:
    def test_catalog_key_is_a_book_filter(self):
        scope = resolve_corpus("philosophy/Meditations", CATALOG, GENRES)
        assert scope == {
            "genre_filter": None,
            "book_filter": "philosophy/Meditations",
            "diary_slug": None,
        }

    def test_apostrophe_key_passes_unchanged(self):
        assert resolve_corpus(PLUTARCH, CATALOG, GENRES)["book_filter"] == PLUTARCH

    def test_non_ascii_pepys_key_resolves_to_its_diary(self):
        scope = resolve_corpus(PEPYS_KEY, CATALOG, GENRES)
        assert scope["diary_slug"] == "pepys-complete"
        assert scope["book_filter"] is None  # never a DocKG book filter

    def test_unknown_book_is_an_error(self):
        scope = resolve_corpus("philosophy/Nope", CATALOG, GENRES)
        assert "error" in scope
        assert "<genre>/<book>" in scope["error"]

    def test_unknown_diary_is_an_error(self):
        assert "error" in resolve_corpus("diaries/The Diary of Nobody", CATALOG, GENRES)

    def test_genre_is_unchanged(self):
        assert resolve_corpus("philosophy", CATALOG, GENRES) == {
            "genre_filter": "philosophy",
            "book_filter": None,
            "diary_slug": None,
        }

    def test_all_diary_gutenberg_are_unscoped(self):
        for corpus in ("all", "diary", "gutenberg"):
            scope = resolve_corpus(corpus, CATALOG, GENRES)
            assert scope == {"genre_filter": None, "book_filter": None, "diary_slug": None}

    def test_garbage_is_an_error(self):
        assert "error" in resolve_corpus("nonsense", CATALOG, GENRES)


def test_both_workers_share_the_scope_rules():
    """The local and RunPod workers resolve ``corpus`` through this module.

    Read from source: neither handler can be imported without its startup.
    """
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    for relative in ("src/gutenberg_kg/serve/handler.py", "runpod/handler.py"):
        source = (repo / relative).read_text(encoding="utf-8")
        assert "from gutenberg_kg.serve.scope import resolve_corpus" in source, relative
        assert "_resolve_corpus(corpus, _catalog, _ALL_GENRES)" in source, relative
        assert "unknown corpus {corpus!r}" not in source, f"{relative} validates corpus itself"
