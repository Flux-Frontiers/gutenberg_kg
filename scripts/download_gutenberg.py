#!/usr/bin/env python3
"""Download books from Project Gutenberg and place them in the repo.

Usage:
    # Download a single book by Gutenberg ID
    python scripts/download_gutenberg.py 2680 --title "Meditations"

    # Download a single book (auto-detects title from Gutenberg metadata)
    python scripts/download_gutenberg.py 2680

    # Download multiple books from a catalog file
    python scripts/download_gutenberg.py --catalog scripts/catalog.txt

    # Strip Gutenberg boilerplate only (no download)
    python scripts/download_gutenberg.py 2680 --title "Meditations" --strip-only

Catalog file format (one book per line, tab-separated):
    2680\tMeditations
    1342\tPride and Prejudice
    84\tFrankenstein

Books are saved as plain UTF-8 text files with Gutenberg header/footer
boilerplate stripped. The directory structure follows the existing repo
convention:

    <Title>/
        <slug>.txt

This makes each book directory compatible with DocKG's `dockg build` command
and DiaryKG's processing pipeline — both expect .txt (or .md) files in a
corpus directory tree.
"""

import argparse
import os
import re
import sys
import time
import urllib.error
import urllib.request

GUTENBERG_TXT_URL = "https://www.gutenberg.org/cache/epub/{ebook_id}/pg{ebook_id}.txt"
GUTENBERG_PAGE_URL = "https://www.gutenberg.org/ebooks/{ebook_id}"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

START_MARKER = re.compile(r"\*\*\* ?START OF THE PROJECT GUTENBERG EBOOK .+? \*\*\*")
END_MARKER = re.compile(r"\*\*\* ?END OF THE PROJECT GUTENBERG EBOOK .+? \*\*\*")


def slugify(title: str) -> str:
    """Convert a title to a filesystem-friendly slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug


def fetch_url(url: str, retries: int = 3, backoff: float = 2.0) -> str:
    """Fetch a URL with retries and exponential backoff. Returns text content."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GreatBooksProject/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8-sig")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            if attempt == retries - 1:
                raise
            wait = backoff * (2 ** attempt)
            print(f"  Retry {attempt + 1}/{retries} after error: {exc}  (waiting {wait:.0f}s)")
            time.sleep(wait)
    return ""  # unreachable


def detect_title(ebook_id: int) -> str:
    """Attempt to detect the book title from Gutenberg metadata in the text."""
    url = GUTENBERG_TXT_URL.format(ebook_id=ebook_id)
    text = fetch_url(url)
    # Look for "Title: ..." in the Gutenberg header
    match = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    raise ValueError(f"Could not auto-detect title for ebook {ebook_id}. Use --title to specify.")


def strip_boilerplate(text: str) -> str:
    """Remove Project Gutenberg header and footer boilerplate."""
    start = START_MARKER.search(text)
    end = END_MARKER.search(text)

    if start:
        text = text[start.end():]
    if end:
        text = text[:END_MARKER.search(text).start()] if END_MARKER.search(text) else text

    # Strip leading/trailing whitespace
    return text.strip() + "\n"


def download_book(ebook_id: int, title: str, strip: bool = True) -> str:
    """Download a book and save it to the repo. Returns the output path."""
    book_dir = os.path.join(REPO_ROOT, title)
    os.makedirs(book_dir, exist_ok=True)

    slug = slugify(title)
    out_path = os.path.join(book_dir, f"{slug}.txt")

    print(f"Downloading: {title} (Gutenberg #{ebook_id})")
    url = GUTENBERG_TXT_URL.format(ebook_id=ebook_id)
    text = fetch_url(url)

    if strip:
        text = strip_boilerplate(text)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"  Saved: {out_path} ({size_kb:.1f} KB)")
    return out_path


def parse_catalog(catalog_path: str) -> list[tuple[int, str]]:
    """Parse a catalog file. Each line: <ebook_id>\\t<title>"""
    entries = []
    with open(catalog_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                print(f"  Warning: skipping malformed line {line_num}: {line!r}")
                continue
            try:
                ebook_id = int(parts[0].strip())
            except ValueError:
                print(f"  Warning: skipping non-numeric ID on line {line_num}: {parts[0]!r}")
                continue
            title = parts[1].strip()
            entries.append((ebook_id, title))
    return entries


def main():
    parser = argparse.ArgumentParser(
        description="Download books from Project Gutenberg into the great_books repo."
    )
    parser.add_argument(
        "ebook_id",
        nargs="?",
        type=int,
        help="Project Gutenberg ebook ID (e.g. 2680 for Meditations)",
    )
    parser.add_argument("--title", help="Book title (used for directory name). Auto-detected if omitted.")
    parser.add_argument(
        "--catalog",
        help="Path to a catalog file with multiple books to download.",
    )
    parser.add_argument(
        "--strip-only",
        action="store_true",
        help="Only strip boilerplate, don't re-download if file exists.",
    )
    parser.add_argument(
        "--no-strip",
        action="store_true",
        help="Keep Gutenberg header/footer boilerplate.",
    )

    args = parser.parse_args()

    if not args.ebook_id and not args.catalog:
        parser.error("Provide either an ebook_id or --catalog path.")

    books: list[tuple[int, str]] = []

    if args.catalog:
        books = parse_catalog(args.catalog)
        if not books:
            print("No valid entries found in catalog file.")
            sys.exit(1)
        print(f"Catalog loaded: {len(books)} book(s)")

    if args.ebook_id:
        title = args.title or detect_title(args.ebook_id)
        books.append((args.ebook_id, title))

    strip = not args.no_strip
    downloaded = []

    for ebook_id, title in books:
        try:
            path = download_book(ebook_id, title, strip=strip)
            downloaded.append(path)
        except Exception as exc:
            print(f"  ERROR downloading {title} (#{ebook_id}): {exc}", file=sys.stderr)

    print(f"\nDone. {len(downloaded)}/{len(books)} book(s) downloaded.")


if __name__ == "__main__":
    main()
