#!/usr/bin/env python3
"""Build per-author provenance pages from corpus book reference files.

Steps:
  1. Scan corpus/<genre>/<book>/reference.md for all books.
  2. Parse each reference.md to extract author metadata.
  3. With --refresh: fetch the Gutenberg RDF for any book missing Born/Died/
     Wikipedia and patch its reference.md in place.
  4. Write corpus/authors/<slug>/author.md — one page per unique author.
  5. Write corpus/authors/index.md — master alphabetical list.

Usage:
    python scripts/build_author_index.py
    python scripts/build_author_index.py --refresh
    python scripts/build_author_index.py --dry-run
    python scripts/build_author_index.py --refresh --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "corpus"
AUTHORS_DIR = CORPUS_ROOT / "authors"

# Reuse the download script for RDF fetching
_scripts = str(Path(__file__).resolve().parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import download_gutenberg as _dg  # noqa: E402


# ---------------------------------------------------------------------------
# reference.md parser
# ---------------------------------------------------------------------------

def _field(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def parse_reference(path: Path) -> dict:
    """Extract author + book metadata from a reference.md file."""
    text = path.read_text(encoding="utf-8")
    meta: dict = {"_path": path}

    # Book identity
    meta["title"] = _field(r"^# Reference:\s*(.+)$", text) or path.parent.name
    eid = _field(r"\*\*Project Gutenberg ID\*\*:\s*(\d+)", text)
    meta["ebook_id"] = int(eid) if eid else None

    # Genre is the grandparent dir name (corpus/<genre>/<book>/reference.md)
    meta["genre"] = path.parent.parent.name

    # Author fields
    meta["author"]         = _field(r"\*\*Name\*\*:\s*(.+)$", text)
    meta["author_birth"]   = _field(r"\*\*Born\*\*:\s*(.+)$", text)
    meta["author_death"]   = _field(r"\*\*Died\*\*:\s*(.+)$", text)
    meta["author_url"]     = _field(r"\*\*Wikipedia\*\*:\s*(.+)$", text)
    aid = _field(r"\*\*Gutenberg Agent ID\*\*:\s*(\d+)", text)
    meta["author_agent_id"] = int(aid) if aid else None

    return meta


# ---------------------------------------------------------------------------
# reference.md patcher
# ---------------------------------------------------------------------------

def patch_reference(path: Path, extra: dict, dry_run: bool = False) -> bool:
    """Insert missing Born/Died/Wikipedia/AgentID into the ## Author section.

    Returns True if the file was (or would be) modified.
    """
    text = path.read_text(encoding="utf-8")

    insertions: list[tuple[str, str]] = []
    if extra.get("author_birth") and "**Born**" not in text:
        insertions.append(("author_birth", f"- **Born**: {extra['author_birth']}"))
    if extra.get("author_death") and "**Died**" not in text:
        insertions.append(("author_death", f"- **Died**: {extra['author_death']}"))
    if extra.get("author_url") and "**Wikipedia**" not in text:
        insertions.append(("author_url", f"- **Wikipedia**: {extra['author_url']}"))
    if extra.get("author_agent_id") and "**Gutenberg Agent ID**" not in text:
        insertions.append(("author_agent_id",
                           f"- **Gutenberg Agent ID**: {extra['author_agent_id']}"))

    if not insertions:
        return False

    lines = text.split("\n")
    new_lines: list[str] = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        if not inserted and line.startswith("- **Name**:"):
            for _, insert_line in insertions:
                new_lines.append(insert_line)
            inserted = True

    if not inserted:
        return False  # No ## Author / Name line found

    if not dry_run:
        path.write_text("\n".join(new_lines), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Author page writer
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug.strip("_")


def write_author_page(
    author: str,
    books: list[dict],
    dry_run: bool = False,
) -> Path:
    """Write corpus/authors/<slug>/author.md and return its path."""
    slug = _slugify(author)
    out_dir = AUTHORS_DIR / slug
    out_path = out_dir / "author.md"

    # Consolidate provenance across all books for this author
    births  = {b["author_birth"]    for b in books if b.get("author_birth")}
    deaths  = {b["author_death"]    for b in books if b.get("author_death")}
    urls    = {b["author_url"]      for b in books if b.get("author_url")}
    agents  = {b["author_agent_id"] for b in books if b.get("author_agent_id")}

    birth = next(iter(births), None)
    death = next(iter(deaths), None)
    url   = next(iter(urls), None)
    agent = next(iter(agents), None)

    lines = [f"# {author}", ""]

    if birth or death:
        era = f"{birth or '?'} – {death or '?'}"
        lines += [f"*{era}*", ""]

    if url:
        lines.append(f"- **Wikipedia**: {url}")
    if agent:
        lines.append(f"- **Gutenberg Agent ID**: {agent}")
    if url or agent:
        lines.append("")

    lines += ["## Works in Corpus", "", "| Title | Genre |", "|-------|-------|"]
    for b in sorted(books, key=lambda x: x.get("title", "")):
        lines.append(f"| {b['title']} | {b['genre']} |")
    lines.append("")

    content = "\n".join(lines)
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    return out_path


def write_index(authors_books: dict[str, list[dict]], dry_run: bool = False) -> Path:
    """Write corpus/authors/index.md and return its path."""
    out_path = AUTHORS_DIR / "index.md"

    lines = [
        "# Author Index",
        "",
        "| Author | Born | Died | Works |",
        "|--------|------|------|------:|",
    ]
    for author in sorted(authors_books):
        books = authors_books[author]
        birth = next((b["author_birth"] for b in books if b.get("author_birth")), "—")
        death = next((b["author_death"] for b in books if b.get("author_death")), "—")
        slug  = _slugify(author)
        lines.append(f"| [{author}]({slug}/author.md) | {birth} | {death} | {len(books)} |")
    lines.append("")

    content = "\n".join(lines)
    if not dry_run:
        AUTHORS_DIR.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build per-author provenance pages from corpus books.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Re-fetch Gutenberg RDF and patch reference.md for books "
                             "missing Born/Died/Wikipedia.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print actions without writing any files.")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN — no files will be written]\n")

    # 1. Scan all reference.md files
    ref_files = sorted(CORPUS_ROOT.glob("*/*/reference.md"))
    print(f"Found {len(ref_files)} reference files across corpus/\n")

    metas: list[dict] = []
    for ref in ref_files:
        metas.append(parse_reference(ref))

    # 2. Optionally refresh missing provenance from Gutenberg RDF
    if args.refresh:
        needs_refresh = [
            m for m in metas
            if m.get("ebook_id") and not m.get("author_birth") and not m.get("author_death")
        ]
        print(f"--- Refreshing metadata ({len(needs_refresh)} books missing provenance) ---")
        refreshed = patched = 0
        for m in needs_refresh:
            eid = m["ebook_id"]
            title = m["title"]
            print(f"  [{title}] fetching RDF #{eid}...", end=" ", flush=True)
            time.sleep(0.3)  # polite rate-limiting
            extra = _dg._fetch_rdf_author(eid)
            if not extra:
                print("no data")
                continue
            refreshed += 1
            parts = []
            if extra.get("author_birth"):
                parts.append(extra["author_birth"])
                m["author_birth"] = extra["author_birth"]
            if extra.get("author_death"):
                parts.append(extra["author_death"])
                m["author_death"] = extra["author_death"]
            if extra.get("author_url"):
                m["author_url"] = extra["author_url"]
            if extra.get("author_agent_id"):
                m["author_agent_id"] = extra["author_agent_id"]
            label = " / ".join(parts) if parts else "dates unknown"
            print(label, end="")
            if patch_reference(m["_path"], extra, dry_run=args.dry_run):
                patched += 1
                print(" [patched]")
            else:
                print()
        print(f"\n  RDF fetched: {refreshed}  reference.md patched: {patched}\n")

    # 3. Group books by author
    authors_books: dict[str, list[dict]] = defaultdict(list)
    skipped_no_author = 0
    for m in metas:
        author = m.get("author")
        if not author:
            skipped_no_author += 1
            continue
        authors_books[author].append(m)

    print(f"--- Building author pages ({len(authors_books)} unique authors) ---")
    if skipped_no_author:
        print(f"  (skipped {skipped_no_author} books with no author field)\n")

    # 4. Write per-author pages
    for author, books in sorted(authors_books.items()):
        out_path = write_author_page(author, books, dry_run=args.dry_run)
        tag = "[dry]" if args.dry_run else "[+]"
        print(f"  {tag} {author} ({len(books)} work{'s' if len(books) != 1 else ''}) → {out_path.relative_to(REPO_ROOT)}")

    # 5. Write index
    print()
    index_path = write_index(authors_books, dry_run=args.dry_run)
    tag = "[dry]" if args.dry_run else "[+]"
    print(f"  {tag} index → {index_path.relative_to(REPO_ROOT)}")
    print(f"\nDone. {len(authors_books)} author pages, {len(metas)} books.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
