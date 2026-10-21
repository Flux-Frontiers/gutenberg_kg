# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Corpus scoping for the worker, kept free of the handler's import-time startup.

``handler`` opens stores and loads the embedder when it is imported, so nothing
in it can be unit-tested cheaply (see :mod:`gutenberg_kg.serve.fusion`). The
rules that turn a request's ``corpus`` value into a search scope are pure, so
they live here and the handler calls in.

A ``corpus`` value is one of:

* ``all``, ``gutenberg`` or ``diary`` -- the whole corpus or one half of it;
* a genre name -- every book under ``<genre>/``;
* a ``"<genre>/<book>"`` catalog key -- that one book;
* ``"diaries/<title>"`` -- that one diary, searched in its own DiaryKG.

Keys can contain apostrophes and non-ASCII characters (the diary titles carry
an em dash). They are passed through unchanged, never normalized.
"""

from __future__ import annotations

from collections.abc import Collection

from gutenberg_kg.diary_meta import DIARY_META

_DIARY_PREFIX = "diaries/"


def diary_slug_for_key(key: str) -> str | None:
    """Resolve a ``"diaries/<title>"`` key to its DiaryKG slug.

    :param key: A corpus value, ``"diaries/"`` plus a diary's exact title as
        ``DIARY_META`` spells it (the titles contain an em dash).
    :returns: The ``DIARY_META`` slug whose title matches exactly, or ``None``
        when the key is not a known diary.
    """
    if not key.startswith(_DIARY_PREFIX):
        return None
    title = key[len(_DIARY_PREFIX) :]
    for slug, meta in DIARY_META.items():
        if meta.get("title") == title:
            return slug
    return None


def resolve_corpus(corpus: str, catalog_keys: Collection[str], genres: Collection[str]) -> dict:
    """Turn a request's ``corpus`` value into a search scope.

    The diary check runs before the catalog check: the diary keys are also in
    the catalog, and a DocKG book filter on them would silently return nothing.

    :param corpus: The request's ``corpus`` field.
    :param catalog_keys: Every ``"<genre>/<book>"`` key in ``catalog.json``.
    :param genres: Every valid genre name.
    :returns: ``{"genre_filter", "book_filter", "diary_slug"}`` (each ``None``
        when not in play), or ``{"error": ...}`` for an unknown value.
    """
    scope: dict = {"genre_filter": None, "book_filter": None, "diary_slug": None}
    if corpus in ("all", "diary", "gutenberg"):
        return scope
    if corpus in genres:
        scope["genre_filter"] = corpus
        return scope
    if corpus.startswith(_DIARY_PREFIX):
        slug = diary_slug_for_key(corpus)
        if slug is not None:
            scope["diary_slug"] = slug
            return scope
    elif corpus in catalog_keys:
        scope["book_filter"] = corpus
        return scope
    return {
        "error": (
            f"unknown corpus {corpus!r}; choose: all, gutenberg, diary, "
            f"a genre name ({', '.join(sorted(genres))}), or <genre>/<book>"
        )
    }


def scope_prefix(genre_filter: str | None, book_filter: str | None) -> str | None:
    """The ``file_path`` prefix a DocKG search is restricted to.

    :param genre_filter: A genre name, or ``None``.
    :param book_filter: A ``"<genre>/<book>"`` key, or ``None``. Wins over the genre.
    :returns: ``"<book_filter>/"``, else ``"<genre_filter>/"``, else ``None``.
    """
    if book_filter:
        return f"{book_filter}/"
    if genre_filter:
        return f"{genre_filter}/"
    return None


def dense_scope_sql(prefix: str) -> str:
    """The ``where`` fragment that scopes the dense channel to a path prefix.

    Single quotes are doubled, since book directory names can contain
    apostrophes. ``_`` and ``%`` in the prefix still act as LIKE wildcards;
    :func:`keep_in_scope` removes what they over-match.

    :param prefix: A ``file_path`` prefix from :func:`scope_prefix`.
    :returns: ``" AND file_path LIKE '<prefix>%'"`` with quotes escaped.
    """
    escaped = prefix.replace("'", "''")
    return f" AND file_path LIKE '{escaped}%'"


def keep_in_scope(rows: list[dict], prefix: str | None) -> list[dict]:
    """Drop rows whose ``file_path`` does not start with the exact prefix.

    Applied to the vector store's rows (which carry ``file_path``) before
    fusion, so the top-k is still filled from in-scope rows.

    :param rows: Vector-store rows, each with a ``file_path`` key.
    :param prefix: A ``file_path`` prefix, or ``None`` to keep every row.
    :returns: The rows inside the prefix, in their original order.
    """
    if not prefix:
        return rows
    return [r for r in rows if (r.get("file_path") or "").startswith(prefix)]
