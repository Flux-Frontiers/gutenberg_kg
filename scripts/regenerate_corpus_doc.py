"""Regenerate docs/CORPUS.md from the on-disk corpus catalog.

This keeps the public corpus book list aligned with the actual corpus directory.

Author resolution priority (first non-empty wins):
  1. ``(Author)`` suffix in directory name  — e.g. ``My Antonia (Cather)``
  2. ``— Author`` suffix in directory name  — e.g. ``A Doll's House — Henrik Ibsen``
     (blocked for structural labels like "Volume 1", "Complete", "Part II")
  3. ``reference.md`` ## Author section     — Gutenberg / IA metadata
  4. ``SPECIAL_AUTHORS`` override           — last resort for structural edge cases
  5. "Unknown"
"""

from __future__ import annotations

import platform
import re
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "corpus"
OUTPUT_FILE = REPO_ROOT / "docs" / "CORPUS.md"

GENRE_ORDER = [
    "philosophy",
    "english-literature",
    "ancient-classical",
    "american-literature",
    "russian-literature",
    "french-literature",
    "biography",
    "drama",
    "science-fiction",
    "travel",
    "natural-history",
    "sacred-texts",
    "letters",
    "world-literature",
    "german-literature",
    "diaries",
    "audel-electric",
    "spanish",
    "shakespeare",
]

GENRE_LABELS = {
    "philosophy": "Philosophy",
    "english-literature": "English Literature",
    "ancient-classical": "Ancient & Classical",
    "american-literature": "American Literature",
    "russian-literature": "Russian Literature",
    "french-literature": "French Literature",
    "biography": "Biography",
    "drama": "Drama",
    "science-fiction": "Science Fiction",
    "travel": "Travel",
    "natural-history": "Natural History",
    "sacred-texts": "Sacred Texts",
    "letters": "Letters",
    "world-literature": "World Literature",
    "german-literature": "German Literature",
    "diaries": "Diaries",
    "audel-electric": "Technical Reference - Internet Archive",
    "spanish": "Spanish Literature",
    "shakespeare": "Shakespeare",
}

# Last-resort overrides for books where the author cannot be inferred from the
# directory name and reference.md metadata is structurally absent or ambiguous.
# Key is (genre, dirname.strip()).  Keep this list as short as possible — fix
# reference.md files rather than adding entries here.
SPECIAL_AUTHORS: dict[tuple[str, str], str] = {
    ("russian-literature", "The Possessed"): "Fyodor Dostoevsky",
    ("philosophy", "Tractatus Logico-Philosophicus"): "Ludwig Wittgenstein",
    ("ancient-classical", "On Duties"): "Marcus Tullius Cicero",
}

# Parts of a "Title — X" dirname where X is a structural label, not an author.
_STRUCTURAL_LABEL_RE = re.compile(
    r"^(Volume\s+\d+|Part\s+[IVX\d]+|Complete|Book\s+[IVX\d]+|Volumes?\s+[IVX\d&–-]+)$",
    re.IGNORECASE,
)


def _author_from_dash(dirname: str) -> str:
    """Extract author from a ``Title — Author`` directory name.

    Returns empty string when the segment after ``—`` is a structural label
    such as "Volume 1", "Complete", or "Part II".
    """
    if " — " not in dirname:
        return ""
    candidate = dirname.rsplit(" — ", 1)[1].strip()
    return "" if _STRUCTURAL_LABEL_RE.match(candidate) else candidate


def _author_from_parens(dirname: str) -> tuple[str, str]:
    """Extract ``(title, author)`` from a ``Title (Author)`` directory name."""
    match = re.match(r"^(.*) \(([^()]+)\)$", dirname)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return dirname.strip(), ""


def _parse_reference(ref_path: Path) -> tuple[str, str]:
    """Extract title and author name from a ``reference.md`` file."""
    if not ref_path.exists():
        return "", ""
    title = ""
    author = ""
    for line in ref_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not title and line.startswith("# Reference: "):
            title = line[len("# Reference: ") :].strip()
        elif not author and line.startswith("- **Name**: "):
            author = line[len("- **Name**: ") :].strip()
        if title and author:
            break
    return title, author


def _gutenkg_version() -> str:
    """Return the installed gutenkg version string, or 'unknown'."""
    try:
        import gutenberg_kg  # noqa: PLC0415

        return gutenberg_kg.__version__
    except ImportError:
        return "unknown"


def _collect_rows() -> tuple[dict[str, list[tuple[str, str]]], int]:
    """Walk corpus directories and return (rows_by_genre, total_books)."""
    rows_by_genre: dict[str, list[tuple[str, str]]] = {}
    total = 0
    for genre in GENRE_ORDER:
        genre_dir = CORPUS_DIR / genre
        if not genre_dir.exists():
            rows_by_genre[genre] = []
            continue
        books = sorted(
            [p for p in genre_dir.iterdir() if p.is_dir() and not p.name.startswith(".")],
            key=lambda p: p.name.lower(),
        )
        total += len(books)
        rows: list[tuple[str, str]] = []
        for book_dir in books:
            dir_title, dir_author = _author_from_parens(book_dir.name)
            ref_title, ref_author = _parse_reference(book_dir / "reference.md")
            # Directory names are curated and more stable than reference.md metadata.
            title = (dir_title or ref_title or book_dir.name).strip()
            author = (
                dir_author
                or _author_from_dash(book_dir.name)
                or ref_author
                or SPECIAL_AUTHORS.get((genre, book_dir.name.strip()))
                or "Unknown"
            )
            rows.append((title.replace("|", "\\|"), author.replace("|", "\\|")))
        rows_by_genre[genre] = rows
    return rows_by_genre, total


def _render(rows_by_genre: dict[str, list[tuple[str, str]]], total: int, elapsed: float) -> str:
    """Render the full CORPUS.md content as a string."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    version = _gutenkg_version()
    host = f"{socket.gethostname()} ({platform.system()} {platform.machine()})"
    n_genres = sum(1 for g in GENRE_ORDER if rows_by_genre.get(g))

    provenance_block = "\n".join(
        [
            "> **Generated**",
            "> - Script: `regenerate_corpus_doc.py`",
            f"> - gutenkg: `{version}`",
            f"> - Date: `{ts}`",
            f"> - Host: `{host}`",
            f"> - Elapsed: `{elapsed:.2f}s`",
        ]
    )
    provenance_comment = (
        f"<!-- generated by regenerate_corpus_doc.py"
        f" | gutenkg {version} | {ts} | {host} | {elapsed:.2f}s -->"
    )

    lines: list[str] = [
        "# Books in the Corpus",
        "",
        provenance_block,
        "",
        (
            f"{total} public-domain texts across {n_genres} genres. "
            "Planned additions are tracked in [`CORPUS_WISHLIST.md`](CORPUS_WISHLIST.md)."
        ),
        "",
    ]
    for genre in GENRE_ORDER:
        rows = rows_by_genre.get(genre, [])
        if not rows:
            continue
        lines.append(f"### {GENRE_LABELS[genre]} ({len(rows)})")
        lines.append("")
        lines.append("| Title | Author |")
        lines.append("|---|---|")
        for title, author in rows:
            lines.append(f"| {title} | {author} |")
        lines.append("")
    lines.append(provenance_comment)
    return "\n".join(lines)


def main() -> None:
    """Walk the corpus directories and write a fresh docs/CORPUS.md."""
    t0 = time.perf_counter()
    rows_by_genre, total = _collect_rows()
    elapsed = time.perf_counter() - t0
    OUTPUT_FILE.write_text(_render(rows_by_genre, total, elapsed), encoding="utf-8")
    n_genres = sum(1 for g in GENRE_ORDER if rows_by_genre.get(g))
    print(f"Wrote {OUTPUT_FILE}  ({total} books across {n_genres} genres)  [{elapsed:.2f}s]")


if __name__ == "__main__":
    main()
