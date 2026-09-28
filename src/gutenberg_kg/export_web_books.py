# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
export_web_books.py -- write each book's text as static JSON for the web forest.

The forest's reader used to ask the worker for chapters (``get_chapters``,
``get_chapter``), which the published site on GitHub Pages cannot reach. This
writes the same chapters as files instead, one per book:

    <out>/<slug>.json   {"chapters": [{"title": ..., "text": ...}, ...]}

``<slug>`` is the catalog's slug (:func:`gutenberg_kg.export_web.slug_from_title`
over ``reference.md``), so the forest finds a book's text from its catalog row.

The text comes from the on-device packs ``gutenkg export-swift`` writes, and
chapters are rebuilt exactly as the worker rebuilds them
(``serve/handler.py:_get_chapter``): a book's chunks between one section's
``char_start`` and the next's; a verse-chunked book with no sections by its
``chapter`` column; a diary by dated entry
(:mod:`gutenberg_kg.serve.diary_browse`).

Usage:
    gutenkg export-web-books
    make export-web-books
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from gutenberg_kg.diary_meta import diary_slug
from gutenberg_kg.export_web import (
    KNOWLEDGE_PRESS_DIR,
    REPO_ROOT,
    kg_db,
    parse_reference,
    slug_from_title,
)
from gutenberg_kg.serve.diary_browse import format_diary_date

DEFAULT_PACKS = REPO_ROOT / "bundles" / "gutenberg-all" / "swift"
DEFAULT_OUT = KNOWLEDGE_PRESS_DIR / "web" / "public" / "books"


@dataclass
class BookText:
    slug: str
    genre: str
    book: str
    chapters: list[dict]


def _connect(pack: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{pack}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def book_chapters(con: sqlite3.Connection, file_path: str) -> list[dict]:
    """A book's chapters from ``gutenberg.pack``, as the worker builds them.

    :param con: Open ``gutenberg.pack``.
    :param file_path: The book's content document, from ``core.pack``.
    :returns: ``[{"title", "text"}, ...]`` in reading order; empty when the
        book has neither sections nor chapter numbers.
    """
    sections = con.execute(
        "SELECT COALESCE(node_title, name) AS title, char_start FROM passages "
        "WHERE kind='section' AND file_path=? ORDER BY char_start",
        (file_path,),
    ).fetchall()
    chunks = con.execute(
        "SELECT char_start, chapter, content FROM passages "
        "WHERE kind='chunk' AND file_path=? ORDER BY char_start",
        (file_path,),
    ).fetchall()
    if sections:
        chapters = []
        for i, s in enumerate(sections):
            end = sections[i + 1]["char_start"] if i + 1 < len(sections) else None
            text = "\n\n".join(
                c["content"]
                for c in chunks
                if c["char_start"] >= s["char_start"] and (end is None or c["char_start"] < end)
            )
            chapters.append({"title": s["title"], "text": text})
        return chapters

    # Verse-chunked genres (sacred-texts) may carry no section nodes.
    by_chapter: dict[int, list[str]] = {}
    for c in chunks:
        if c["chapter"] is not None:
            by_chapter.setdefault(c["chapter"], []).append(c["content"])
    return [{"title": f"Chapter {n}", "text": "\n\n".join(t)} for n, t in by_chapter.items()]


def diary_chapters(con: sqlite3.Connection, kg_name: str) -> list[dict]:
    """A diary's dated entries from ``diaries.pack``, earliest first.

    :param con: Open ``diaries.pack``.
    :param kg_name: The diary's slug, :func:`gutenberg_kg.diary_meta.diary_slug`.
    :returns: ``[{"title", "text"}, ...]``, one per distinct timestamp.
    """
    rows = con.execute(
        "SELECT timestamp, content FROM passages "
        "WHERE kg_name=? AND kind='chunk' AND timestamp IS NOT NULL "
        "ORDER BY timestamp, file_path, char_start",
        (kg_name,),
    )
    entries: dict[str, list[str]] = {}
    for r in rows:
        entries.setdefault(r["timestamp"], []).append(r["content"])
    return [{"title": format_diary_date(ts), "text": "\n\n".join(t)} for ts, t in entries.items()]


def collect_books(corpus: Path, packs: Path) -> tuple[list[BookText], list[str]]:
    """Every catalog book's chapters.

    Walks the corpus the way ``export-web-catalog`` does, so the set of books
    and their slugs match the catalog.

    :param corpus: Corpus root.
    :param packs: Directory holding ``core.pack``, ``gutenberg.pack`` and ``diaries.pack``.
    :returns: The books, and ``"<genre>/<book>"`` for each one the packs had no text for.
    """
    books: list[BookText] = []
    missing: list[str] = []
    with (
        _connect(packs / "core.pack") as core,
        _connect(packs / "gutenberg.pack") as gut,
        _connect(packs / "diaries.pack") as dia,
    ):
        file_paths = {
            (r["genre"], r["book"]): r["file_path"]
            for r in core.execute("SELECT genre, book, file_path FROM books")
        }
        for genre_dir in sorted(
            p for p in corpus.iterdir() if p.is_dir() and not p.name.startswith(".")
        ):
            if genre_dir.name == "authors":
                continue
            for book_dir in sorted(
                p for p in genre_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
            ):
                if kg_db(book_dir) is None:
                    continue
                genre, book = genre_dir.name, book_dir.name
                title = parse_reference(book_dir / "reference.md").get("title") or book
                if genre == "diaries":
                    chapters = diary_chapters(dia, diary_slug(book))
                else:
                    file_path = file_paths.get((genre, book))
                    chapters = book_chapters(gut, file_path) if file_path else []
                if not chapters:
                    missing.append(f"{genre}/{book}")
                    continue
                books.append(BookText(slug_from_title(title), genre, book, chapters))
    return books, missing


def write_books(books: list[BookText], out_dir: Path) -> int:
    """Write one ``<slug>.json`` per book, removing files for books no longer exported.

    :param books: From :func:`collect_books`.
    :param out_dir: Output directory.
    :returns: Total bytes written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    keep = set()
    for b in books:
        path = out_dir / f"{b.slug}.json"
        data = json.dumps({"chapters": b.chapters}, ensure_ascii=False, separators=(",", ":"))
        path.write_text(data, encoding="utf-8")
        total += path.stat().st_size
        keep.add(path.name)
    for stale in out_dir.glob("*.json"):
        if stale.name not in keep:
            stale.unlink()
    return total
