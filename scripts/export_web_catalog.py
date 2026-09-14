"""
export_web_catalog.py — dump the forest catalog from ingested DocKG graphs.

The web forest does not chunk text. Leaves and attractors are sized from
``n_chunks`` on each book, which ForestLayout also counts as
``kind == 'chunk'`` nodes. This script is the missing bridge: walk
``corpus/<genre>/<book>/.dockg/graph.sqlite`` (or ``.diarykg``), count those
nodes, pull title/author from ``reference.md``, and write the TypeScript
catalog the cart reads.

Requires a local corpus with per-book graphs (``gutenkg ingest`` / the
usual forest load). Does not re-run the chunker.

Usage:
    python scripts/export_web_catalog.py
    python scripts/export_web_catalog.py --dry-run
    python scripts/export_web_catalog.py --out web/knowledge-press-forest/src/game
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "corpus"
DEFAULT_OUT = REPO_ROOT / "web" / "knowledge-press-forest" / "src" / "game"
PART_SIZE = 43

GENRE_LABELS: dict[str, str] = {
    "american-literature": "American Literature",
    "ancient-classical": "Ancient & Classical",
    "biography": "Biography",
    "curiosities": "Curiosities",
    "diaries": "Diaries",
    "drama": "Drama",
    "english-literature": "English Literature",
    "french-literature": "French Literature",
    "german-literature": "German Literature",
    "horror": "Horror",
    "letters": "Letters",
    "natural-history": "Natural History",
    "philosophy": "Philosophy",
    "russian-literature": "Russian Literature",
    "sacred-texts": "Sacred Texts",
    "science-fiction": "Science Fiction",
    "shakespeare": "Shakespeare",
    "spanish-literature": "Spanish Literature",
    "technical-reference": "Technical Reference",
    "travel": "Travel",
    "world-literature": "World Literature",
}

KG_DIRS = (".dockg", ".diarykg")


@dataclass
class BookRow:
    slug: str
    title: str
    author: str
    genre: str
    genre_label: str
    chunks: int
    excerpt: str
    tags: list[str] = field(default_factory=list)


def slug_from_title(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"[\s-]+", "_", s)[:60]


def parse_reference(ref: Path) -> dict[str, str]:
    try:
        from gutenberg_kg.authors import parse_reference as _parse

        return {k: str(v) for k, v in _parse(ref).items() if v is not None}
    except Exception:
        return {}


def kg_db(book_dir: Path) -> Path | None:
    for name in KG_DIRS:
        db = book_dir / name / "graph.sqlite"
        if db.exists() and db.stat().st_size > 100:
            return db
    return None


def excerpt_from_graph(con: sqlite3.Connection) -> str:
    """A mid-book chunk, so we skip Gutenberg front matter when we can."""
    n = con.execute("SELECT COUNT(*) FROM nodes WHERE kind='chunk' AND text IS NOT NULL").fetchone()
    total = int(n[0]) if n else 0
    if total <= 0:
        return ""
    skip = min(max(total // 5, 1), max(total - 1, 0))
    row = con.execute(
        "SELECT text FROM nodes WHERE kind='chunk' AND text IS NOT NULL "
        "ORDER BY rowid LIMIT 1 OFFSET ?",
        (skip,),
    ).fetchone()
    if not row or not row[0]:
        return ""
    text = re.sub(r"\s+", " ", str(row[0])).strip()
    if len(text) > 280:
        text = text[:277].rsplit(" ", 1)[0] + "…"
    return text


def topics_from_graph(con: sqlite3.Connection, limit: int = 6) -> list[str]:
    try:
        rows = con.execute(
            "SELECT name FROM nodes WHERE kind='topic' AND name IS NOT NULL LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for (name,) in rows:
        tag = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def collect_book(book_dir: Path, genre: str) -> BookRow | None:
    db = kg_db(book_dir)
    if db is None:
        return None
    ref = parse_reference(book_dir / "reference.md") if (book_dir / "reference.md").exists() else {}
    title = ref.get("title") or book_dir.name
    author = ref.get("author") or "Unknown"
    with sqlite3.connect(str(db)) as con:
        n = con.execute("SELECT COUNT(*) FROM nodes WHERE kind='chunk'").fetchone()
        chunks = int(n[0]) if n else 0
        excerpt = excerpt_from_graph(con)
        extra = topics_from_graph(con)
    tags = [genre] + [t for t in extra if t != genre]
    return BookRow(
        slug=slug_from_title(title),
        title=title,
        author=author,
        genre=genre,
        genre_label=GENRE_LABELS.get(genre, genre.replace("-", " ").title()),
        chunks=chunks,
        excerpt=excerpt,
        tags=tags[:8],
    )


def scan_corpus(root: Path) -> list[BookRow]:
    books: list[BookRow] = []
    missing = 0
    for genre_dir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if genre_dir.name == "authors":
            continue
        for book_dir in sorted(p for p in genre_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            row = collect_book(book_dir, genre_dir.name)
            if row is None:
                missing += 1
                continue
            books.append(row)
    if missing:
        print(f"skipped {missing} book dir(s) with no graph.sqlite", file=sys.stderr)
    return books


def ts_string(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def emit_part(rows: list[BookRow], index: int) -> str:
    lines = [
        'import type { Book } from "./catalogTypes";',
        "",
        f"export const BOOKS_PART{index}: Book[] = [",
    ]
    for r in rows:
        lines.append("  {")
        lines.append(f"    slug: {ts_string(r.slug)},")
        lines.append(f"    title: {ts_string(r.title)},")
        lines.append(f"    author: {ts_string(r.author)},")
        lines.append(f"    genre: {ts_string(r.genre)},")
        lines.append(f"    genreLabel: {ts_string(r.genre_label)},")
        lines.append(f"    chunks: {r.chunks},")
        lines.append(f"    excerpt: {ts_string(r.excerpt)},")
        lines.append(f"    tags: {json.dumps(r.tags, ensure_ascii=False)},")
        lines.append("  },")
    lines.append("];")
    lines.append("")
    return "\n".join(lines)


def emit_barrel(n_parts: int) -> str:
    imports = "\n".join(f'import {{ BOOKS_PART{i} }} from "./catalogPart{i}";' for i in range(1, n_parts + 1))
    spread = ",\n  ".join(f"...BOOKS_PART{i}" for i in range(1, n_parts + 1))
    return (
        "/* GutenbergKG corpus — public-domain texts, grown as trees.\n"
        " * Regenerated by scripts/export_web_catalog.py from per-book graph.sqlite.\n"
        " */\n"
        'export type { Book } from "./catalogTypes";\n'
        'import type { Book } from "./catalogTypes";\n'
        f"{imports}\n\n"
        "export const BOOKS: Book[] = [\n"
        f"  {spread},\n"
        "];\n\n"
        "export const GENRE_ORDER = [...new Set(BOOKS.map((b) => b.genre))];\n\n"
        "export function bookBySlug(slug: string): Book | undefined {\n"
        "  return BOOKS.find((b) => b.slug === slug);\n"
        "}\n"
    )


CATALOG_TYPES = """export type Book = {
  slug: string;
  title: string;
  author: string;
  genre: string;
  genreLabel: string;
  chunks: number;
  excerpt: string;
  tags: string[];
};
"""


def write_catalog(books: list[BookRow], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "catalogTypes.ts").write_text(CATALOG_TYPES, encoding="utf-8")
    n_parts = max(1, (len(books) + PART_SIZE - 1) // PART_SIZE)
    for i in range(n_parts):
        chunk = books[i * PART_SIZE : (i + 1) * PART_SIZE]
        (out_dir / f"catalogPart{i + 1}.ts").write_text(emit_part(chunk, i + 1), encoding="utf-8")
    (out_dir / "catalog.ts").write_text(emit_barrel(n_parts), encoding="utf-8")
    leftover = sorted(out_dir.glob("catalogPart*.ts"))
    for stale in leftover:
        n = int(re.search(r"(\d+)", stale.stem).group(1)) if re.search(r"(\d+)", stale.stem) else 0
        if n > n_parts:
            stale.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.corpus.is_dir():
        print(f"no corpus at {args.corpus} — ingest books first", file=sys.stderr)
        return 1

    books = scan_corpus(args.corpus)
    if not books:
        print("no books with graph.sqlite found", file=sys.stderr)
        return 1

    hamlet = next((b for b in books if b.slug == "hamlet"), None)
    print(f"{len(books)} books  ·  {sum(b.chunks for b in books):,} chunks")
    if hamlet:
        print(f"hamlet: {hamlet.chunks} chunks")
    by_genre: dict[str, int] = {}
    for b in books:
        by_genre[b.genre] = by_genre.get(b.genre, 0) + 1
    for g, n in sorted(by_genre.items()):
        print(f"  {n:3d}  {g}")

    if args.dry_run:
        return 0

    write_catalog(books, args.out)
    print(f"wrote {args.out / 'catalog.ts'} and {((len(books) + PART_SIZE - 1) // PART_SIZE)} parts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
