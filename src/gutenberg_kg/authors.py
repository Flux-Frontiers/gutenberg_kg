"""Author provenance — build ``corpus/authors/`` from ``reference.md`` files.

Entry point for callers: :func:`build`. The CLI wrapper lives at
``gutenberg_kg.cli.cmd_authors`` and exposes this as ``gutenkg authors``.
"""
from __future__ import annotations

import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from gutenberg_kg.cli.options import CORPUS_ROOT, REPO_ROOT

AUTHORS_DIR = CORPUS_ROOT / "authors"


# ---------------------------------------------------------------------------
# RDF fetcher — lazy import of scripts/download_gutenberg.py
# ---------------------------------------------------------------------------

def _dg():
    """Lazy-import ``download_gutenberg`` from ``scripts/`` for RDF fetching."""
    scripts = str(REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import download_gutenberg as _mod  # noqa: PLC0415
    return _mod


# ---------------------------------------------------------------------------
# reference.md parser
# ---------------------------------------------------------------------------

def _field(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def parse_reference(path: Path) -> dict:
    """Extract author + book metadata from a ``reference.md`` file."""
    text = path.read_text(encoding="utf-8")
    meta: dict = {"_path": path}

    meta["title"] = _field(r"^# Reference:\s*(.+)$", text) or path.parent.name
    eid = _field(r"\*\*Project Gutenberg ID\*\*:\s*(\d+)", text)
    meta["ebook_id"] = int(eid) if eid else None

    # Genre is the grandparent dir name (corpus/<genre>/<book>/reference.md)
    meta["genre"] = path.parent.parent.name

    meta["author"]       = _field(r"\*\*Name\*\*:\s*(.+)$", text)
    meta["author_birth"] = _field(r"\*\*Born\*\*:\s*(.+)$", text)
    meta["author_death"] = _field(r"\*\*Died\*\*:\s*(.+)$", text)
    meta["author_url"]   = _field(r"\*\*Wikipedia\*\*:\s*(.+)$", text)
    aid = _field(r"\*\*Gutenberg Agent ID\*\*:\s*(\d+)", text)
    meta["author_agent_id"] = int(aid) if aid else None

    return meta


# ---------------------------------------------------------------------------
# reference.md patcher
# ---------------------------------------------------------------------------

def patch_reference(path: Path, extra: dict, dry_run: bool = False) -> bool:
    """Insert missing Born/Died/Wikipedia/AgentID into the ``## Author`` section.

    Returns True iff the file was (or would be) modified.
    """
    text = path.read_text(encoding="utf-8")

    insertions: list[str] = []
    if extra.get("author_birth") and "**Born**" not in text:
        insertions.append(f"- **Born**: {extra['author_birth']}")
    if extra.get("author_death") and "**Died**" not in text:
        insertions.append(f"- **Died**: {extra['author_death']}")
    if extra.get("author_url") and "**Wikipedia**" not in text:
        insertions.append(f"- **Wikipedia**: {extra['author_url']}")
    if extra.get("author_agent_id") and "**Gutenberg Agent ID**" not in text:
        insertions.append(f"- **Gutenberg Agent ID**: {extra['author_agent_id']}")

    if not insertions:
        return False

    lines = text.split("\n")
    new_lines: list[str] = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        if not inserted and line.startswith("- **Name**:"):
            new_lines.extend(insertions)
            inserted = True

    if not inserted:
        return False

    if not dry_run:
        path.write_text("\n".join(new_lines), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Author page + index writers
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
    """Write ``corpus/authors/<slug>/author.md`` and return its path."""
    slug = _slugify(author)
    out_dir = AUTHORS_DIR / slug
    out_path = out_dir / "author.md"

    births = {b["author_birth"]    for b in books if b.get("author_birth")}
    deaths = {b["author_death"]    for b in books if b.get("author_death")}
    urls   = {b["author_url"]      for b in books if b.get("author_url")}
    agents = {b["author_agent_id"] for b in books if b.get("author_agent_id")}

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
    """Write ``corpus/authors/index.md`` and return its path."""
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
# Orchestrator
# ---------------------------------------------------------------------------

def build(refresh: bool = False, dry_run: bool = False) -> int:
    """Rebuild ``corpus/authors/`` from all ``reference.md`` files.

    :param refresh: If True, re-fetch the Gutenberg RDF for any book missing
        Born/Died and patch its ``reference.md`` in place before building.
    :param dry_run: If True, print what would happen without writing any files.
    :return: ``0`` on success (always, unless an unhandled exception propagates).
    """
    if dry_run:
        print("[DRY RUN — no files will be written]\n")

    # 1. Scan reference.md files
    ref_files = sorted(CORPUS_ROOT.glob("*/*/reference.md"))
    print(f"Found {len(ref_files)} reference files across corpus/\n")

    metas: list[dict] = [parse_reference(ref) for ref in ref_files]

    # 2. Optional refresh
    if refresh:
        dg = _dg()
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
            extra = dg._fetch_rdf_author(eid)
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
            if patch_reference(m["_path"], extra, dry_run=dry_run):
                patched += 1
                print(" [patched]")
            else:
                print()
        print(f"\n  RDF fetched: {refreshed}  reference.md patched: {patched}\n")

    # 3. Group by author
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
        out_path = write_author_page(author, books, dry_run=dry_run)
        tag = "[dry]" if dry_run else "[+]"
        n = len(books)
        suffix = "s" if n != 1 else ""
        print(f"  {tag} {author} ({n} work{suffix}) → {out_path.relative_to(REPO_ROOT)}")

    # 5. Write index
    print()
    index_path = write_index(authors_books, dry_run=dry_run)
    tag = "[dry]" if dry_run else "[+]"
    print(f"  {tag} index → {index_path.relative_to(REPO_ROOT)}")
    print(f"\nDone. {len(authors_books)} author pages, {len(metas)} books.\n")
    return 0
