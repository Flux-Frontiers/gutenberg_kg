#!/usr/bin/env python3
"""Download books from Project Gutenberg as structured Markdown.

Commands:
    download  - Download a book by Gutenberg ID
    search    - Search Gutenberg catalog by author, title, or keyword
    catalog   - Download multiple books from a catalog file

Usage:
    # Search for books by an author
    python scripts/download_gutenberg.py search --author "Charles Dickens"

    # Search by title keyword
    python scripts/download_gutenberg.py search --title "Frankenstein"

    # General keyword search
    python scripts/download_gutenberg.py search "greek philosophy"

    # Download a single book by Gutenberg ID
    python scripts/download_gutenberg.py download 2680

    # Download with explicit title override
    python scripts/download_gutenberg.py download 2680 --title "Meditations"

    # Download multiple books from a catalog file
    python scripts/download_gutenberg.py catalog scripts/catalog.txt

Output structure (per book):
    <Title>/
        <slug>.md          # Structured Markdown with chapter headings
        reference.md       # Gutenberg metadata, subjects, and source info

The Markdown output preserves chapter/section structure with proper headings,
making it directly compatible with DocKG's `dockg build` and DiaryKG's
processing pipelines.
"""

import argparse
import html
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GUTENBERG_TXT_URL = "https://www.gutenberg.org/cache/epub/{ebook_id}/pg{ebook_id}.txt"
GUTENBERG_OPDS_URL = "https://www.gutenberg.org/ebooks/{ebook_id}.opds"
GUTENBERG_SEARCH_URL = "https://www.gutenberg.org/ebooks/search.opds/"
GUTENBERG_PAGE_URL = "https://www.gutenberg.org/ebooks/{ebook_id}"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

START_MARKER = re.compile(r"\*\*\* ?START OF THE PROJECT GUTENBERG EBOOK .+? \*\*\*")
END_MARKER = re.compile(r"\*\*\* ?END OF THE PROJECT GUTENBERG EBOOK .+? \*\*\*")

# Namespaces used in Gutenberg OPDS feeds
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dcterms": "http://purl.org/dc/terms/",
    "opds": "http://opds-spec.org/2010/catalog",
    "xhtml": "http://www.w3.org/1999/xhtml",
}

# Common heading patterns found in Gutenberg texts, ordered by specificity.
# Each tuple: (compiled regex, markdown heading level, group index for title)
HEADING_PATTERNS = [
    # "THE FIRST BOOK" / "THE SECOND BOOK" (ordinal, e.g. Meditations)
    (re.compile(
        r"^THE\s+(?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|"
        r"NINTH|TENTH|ELEVENTH|TWELFTH|THIRTEENTH)\s+BOOK$",
        re.IGNORECASE,
    ), 2),
    # VOLUME / BOOK / PART + numeral (h2)
    (re.compile(
        r"^(?:VOLUME|BOOK|PART)\s+"
        r"(?:THE\s+)?"
        r"(?:[IVXLCDM]+|FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|"
        r"NINTH|TENTH|ELEVENTH|TWELFTH|\d+)"
        r"(?:\.?\s*[-—:.]?\s*(.+))?$",
        re.IGNORECASE,
    ), 2),
    # "Book the First--Recalled to Life" (Dickens style)
    (re.compile(
        r"^Book\s+the\s+\w+[-—].+$",
        re.IGNORECASE,
    ), 2),
    # ACT (for plays, h2)
    (re.compile(
        r"^ACT\s+(?:[IVXLCDM]+|\d+)"
        r"(?:\.?\s*[-—:.]?\s*(.+))?$",
        re.IGNORECASE,
    ), 2),
    # CHAPTER level (h2) — "CHAPTER I.", "CHAPTER XIV", "CHAPTER 3"
    (re.compile(
        r"^CHAPTER\s+(?:[IVXLCDM]+|\d+)\.?"
        r"(?:\s*[-—:.]?\s*(.+))?$",
        re.IGNORECASE,
    ), 2),
    # "Chapter 1" style Title Case
    (re.compile(
        r"^Chapter\s+(?:[IVXLCDM]+|\d+)\.?"
        r"(?:\s*[-—:.]?\s*(.+))?$",
    ), 2),
    # SCENE (for plays, h3)
    (re.compile(
        r"^SCENE\s+(?:[IVXLCDM]+|\d+)"
        r"(?:\.?\s*[-—:.]?\s*(.+))?$",
        re.IGNORECASE,
    ), 3),
    # LETTER I / LETTER 1 / "Letter 1" (epistolary novels)
    (re.compile(
        r"^Letter\s+(?:[IVXLCDM]+|\d+)"
        r"(?:\.?\s*[-—:.]?\s*(.+))?$",
        re.IGNORECASE,
    ), 2),
    # Bible book headings: "The First Book of Moses: Called Genesis",
    # "The Book of Joshua", "The Gospel According to Saint Matthew", etc.
    (re.compile(
        r"^The\s+(?:First|Second|Third|Fourth|Fifth)\s+Book\s+of\s+.+$",
    ), 2),
    (re.compile(
        r"^The\s+(?:Book\s+of|Gospel\s+According|Epistle|General\s+Epistle|"
        r"Revelation|Acts|Song|Lamentations)\s+.+$",
    ), 2),
    # Testament dividers (Bible)
    (re.compile(
        r"^The\s+(?:Old|New)\s+Testament.*$",
    ), 2),
    # STAVE I / STAVE 1 (A Christmas Carol)
    (re.compile(
        r"^STAVE\s+(?:[IVXLCDM]+|\d+)"
        r"(?:\.?\s*[-—:.]?\s*(.+))?$",
        re.IGNORECASE,
    ), 2),
    # "I. A SCANDAL IN BOHEMIA" — Roman numeral + period + ALL CAPS TITLE
    (re.compile(
        r"^([IVXLCDM]{1,6})\.\s+([A-Z][A-Z\s\-',:]{2,60})$",
    ), 2),
    # Roman numeral standalone: "I.", "II.", "XIV." (section breaks within stories)
    # Must have a period to distinguish "I." from "I think..."
    (re.compile(
        r"^([IVXLCDM]{1,6})\.\s*$",
    ), 3),
    # Standalone ALL-CAPS heading (at least 3 chars, max ~60, not a sentence)
    (re.compile(
        r"^([A-Z][A-Z\s\-',:]{2,60})$",
    ), 3),
]

# Illustration markers to clean up
ILLUSTRATION_RE = re.compile(r"\[Illustration[^\]]*\]")

# Lines to skip when they appear right after the start marker
FRONT_MATTER_SKIP = re.compile(
    r"^(?:Produced by|Transcribed by|E-text prepared by|"
    r"Updated editions will|This etext was|"
    r"Distributed Proofreaders|"
    r"\*\*\*)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def slugify(title: str) -> str:
    """Convert a title to a filesystem-friendly slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug


def fetch_url(url: str, retries: int = 3, backoff: float = 2.0) -> str:
    """Fetch a URL with retries and exponential backoff."""
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
    return ""


# ---------------------------------------------------------------------------
# Gutenberg OPDS Metadata
# ---------------------------------------------------------------------------

def fetch_metadata(ebook_id: int) -> dict:
    """Fetch book metadata from the Gutenberg OPDS feed."""
    url = GUTENBERG_OPDS_URL.format(ebook_id=ebook_id)
    xml_text = fetch_url(url)
    root = ET.fromstring(xml_text)

    entry = root.find("atom:entry", NS)
    if entry is None:
        return {"ebook_id": ebook_id}

    meta = {"ebook_id": ebook_id}

    # Title
    title_el = entry.find("atom:title", NS)
    if title_el is not None and title_el.text:
        meta["title"] = title_el.text.strip()

    # Author
    author_el = entry.find("atom:author/atom:name", NS)
    if author_el is not None and author_el.text:
        # Gutenberg uses "Last, First" — reverse it
        name = author_el.text.strip()
        parts = [p.strip() for p in name.split(",", 1)]
        meta["author"] = " ".join(reversed(parts)) if len(parts) == 2 else name

    # Published date
    pub_el = entry.find("atom:published", NS)
    if pub_el is not None and pub_el.text:
        meta["published"] = pub_el.text.strip()[:10]

    # Rights
    rights_el = entry.find("atom:rights", NS)
    if rights_el is not None and rights_el.text:
        meta["rights"] = rights_el.text.strip()

    # Subjects from <category> elements
    subjects = []
    for cat in entry.findall("atom:category", NS):
        term = cat.get("term", "")
        if term:
            subjects.append(term)
    if subjects:
        meta["subjects"] = subjects

    # Language
    lang_el = entry.find("dcterms:language", NS)
    if lang_el is not None and lang_el.text:
        meta["language"] = lang_el.text.strip()

    # Summary and other details from content block
    content_el = entry.find("atom:content", NS)
    if content_el is not None:
        # The content is XHTML — extract text from <p> elements
        div = content_el.find("xhtml:div", NS)
        if div is not None:
            for p in div.findall("xhtml:p", NS):
                text = "".join(p.itertext()).strip()
                if text.startswith("Summary:"):
                    meta["summary"] = text[len("Summary:"):].strip()
                elif text.startswith("Note:"):
                    meta["note"] = text[len("Note:"):].strip()

    meta["gutenberg_url"] = GUTENBERG_PAGE_URL.format(ebook_id=ebook_id)
    return meta


def search_gutenberg(query: str, max_results: int = 25) -> list[dict]:
    """Search Gutenberg via the OPDS feed. Returns list of book dicts."""
    params = urllib.request.quote(query)
    url = f"{GUTENBERG_SEARCH_URL}?query={params}"
    xml_text = fetch_url(url)
    root = ET.fromstring(xml_text)

    results = []
    for entry in root.findall("atom:entry", NS):
        entry_id = entry.find("atom:id", NS)
        if entry_id is None or entry_id.text is None:
            continue

        # Skip non-book entries (Authors, Subjects facets)
        id_text = entry_id.text
        if "/authors/" in id_text or "/subjects/" in id_text:
            continue

        # Extract ebook ID from the entry id URL
        m = re.search(r"/ebooks/(\d+)", id_text)
        if not m:
            # Try the urn format
            m = re.search(r"gutenberg:(\d+)", id_text)
        if not m:
            continue

        ebook_id = int(m.group(1))
        title_el = entry.find("atom:title", NS)
        title = title_el.text.strip() if title_el is not None and title_el.text else f"Unknown (#{ebook_id})"

        # In search results, author is in <content type="text">, not <author>
        author = ""
        author_el = entry.find("atom:author/atom:name", NS)
        if author_el is not None and author_el.text:
            name = author_el.text.strip()
            parts = [p.strip() for p in name.split(",", 1)]
            author = " ".join(reversed(parts)) if len(parts) == 2 else name
        if not author:
            content_el = entry.find("atom:content", NS)
            if content_el is not None and content_el.text:
                text = content_el.text.strip()
                # Filter out download count strings like "996 downloads"
                if not re.match(r"^\d+\s+downloads?$", text, re.IGNORECASE):
                    author = text

        # Subjects
        subjects = []
        for cat in entry.findall("atom:category", NS):
            term = cat.get("term", "")
            if term:
                subjects.append(term)

        results.append({
            "ebook_id": ebook_id,
            "title": title,
            "author": author,
            "subjects": subjects,
        })

        if len(results) >= max_results:
            break

    return results


# ---------------------------------------------------------------------------
# Boilerplate Stripping
# ---------------------------------------------------------------------------

def strip_boilerplate(text: str) -> str:
    """Remove Project Gutenberg header and footer boilerplate."""
    start = START_MARKER.search(text)
    end = END_MARKER.search(text)

    if start:
        text = text[start.end():]
    if end:
        end2 = END_MARKER.search(text)
        if end2:
            text = text[:end2.start()]

    return text.strip() + "\n"


# ---------------------------------------------------------------------------
# Text → Markdown Conversion
# ---------------------------------------------------------------------------

def _is_heading(line: str) -> tuple[int, str] | None:
    """Check if a line is a structural heading.

    Returns (level, heading_text) or None.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return None

    # Reference the last two patterns by index for special handling
    all_caps_pattern = HEADING_PATTERNS[-1][0]
    roman_standalone_pattern = HEADING_PATTERNS[-2][0]
    roman_titled_pattern = HEADING_PATTERNS[-3][0]

    for pattern, level in HEADING_PATTERNS:
        m = pattern.match(stripped)
        if not m:
            continue

        # ALL-CAPS standalone: reject sentence-like lines
        if pattern is all_caps_pattern:
            if len(stripped) > 60 or stripped.endswith(",") or stripped.endswith(";"):
                continue
            words = stripped.split()
            if len(words) > 8:
                continue

        # Bare roman numeral "IV." — sub-section divider
        if pattern is roman_standalone_pattern:
            roman = m.group(1)
            if not re.match(r"^[IVXLCDM]+$", roman):
                continue
            return (level, f"{roman}.")

        # "I. A SCANDAL IN BOHEMIA" — roman + titled
        if pattern is roman_titled_pattern:
            roman = m.group(1)
            if not re.match(r"^[IVXLCDM]+$", roman):
                continue
            title_part = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
            heading = f"{roman}. {title_part}".strip()
            return (level, heading)

        return (level, stripped)
    return None


def _skip_front_matter(lines: list[str], start_idx: int) -> int:
    """Skip producer/transcriber credits that appear before the actual text."""
    i = start_idx
    # Skip blank lines
    while i < len(lines) and not lines[i].strip():
        i += 1
    # Skip credit blocks (usually end with a blank line)
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            break
        if FRONT_MATTER_SKIP.match(line):
            # Skip until we hit a blank line
            while i < len(lines) and lines[i].strip():
                i += 1
            # Skip the blank lines after
            while i < len(lines) and not lines[i].strip():
                i += 1
        else:
            break
    return i


def _detect_toc(lines: list[str], start: int, end: int) -> tuple[int, int] | None:
    """Detect a table of contents block and return its (start, end) indices."""
    toc_start = None
    for i in range(start, min(start + 200, end)):
        line = lines[i].strip().upper()
        if line in ("CONTENTS", "CONTENTS.", "TABLE OF CONTENTS", "TABLE OF CONTENTS."):
            toc_start = i
            break

    if toc_start is None:
        return None

    # TOC ends at the first substantial paragraph or heading after a blank section
    i = toc_start + 1
    blank_count = 0
    while i < min(toc_start + 300, end):
        line = lines[i].strip()
        if not line:
            blank_count += 1
            if blank_count >= 3:
                return (toc_start, i)
        else:
            if blank_count >= 2 and len(line) > 60:
                return (toc_start, i)
            blank_count = 0
        i += 1

    return (toc_start, i)


def text_to_markdown(text: str, meta: dict) -> str:
    """Convert plain Gutenberg text to structured Markdown.

    Strategy:
    1. Add YAML-style front matter from metadata
    2. Detect and convert chapter/section headings to Markdown headings
    3. Preserve paragraph structure
    4. Skip table of contents (redundant with heading structure)
    """
    lines = text.split("\n")
    total = len(lines)

    # Skip producer credits at the very start
    start_idx = _skip_front_matter(lines, 0)

    # Detect and skip table of contents
    toc = _detect_toc(lines, start_idx, min(start_idx + 200, total))
    toc_range = range(toc[0], toc[1]) if toc else range(0)

    # Build the markdown
    md_lines = []

    # Front matter: title as h1
    title = meta.get("title", "Untitled")
    author = meta.get("author", "Unknown")
    md_lines.append(f"# {title}")
    md_lines.append("")
    md_lines.append(f"**{author}**")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    prev_blank = True
    prev_was_heading = False
    in_paragraph = False

    i = start_idx
    while i < total:
        # Skip TOC region
        if i in toc_range:
            i += 1
            continue

        line = lines[i]
        stripped = line.strip()

        # Blank line
        if not stripped:
            if not prev_blank:
                md_lines.append("")
            prev_blank = True
            prev_was_heading = False
            in_paragraph = False
            i += 1
            continue

        # Strip illustration markers
        stripped = ILLUSTRATION_RE.sub("", stripped).strip()
        if not stripped:
            if not prev_blank:
                md_lines.append("")
            prev_blank = True
            i += 1
            continue

        # Check for heading
        heading = _is_heading(stripped)
        if heading and prev_blank:
            level, heading_text = heading

            # Look ahead for subtitle / multi-line chapter title:
            # "CHAPTER I." followed by "HOW MANY KINDS OF..." on next line(s)
            subtitle_lines = []
            j = i + 1
            # Skip blank lines between heading and potential subtitle
            while j < total and not lines[j].strip():
                j += 1
            if j < total:
                next_line = lines[j].strip()
                next_line_clean = ILLUSTRATION_RE.sub("", next_line).strip()
                # Multi-line ALL CAPS title continuation (e.g. The Prince)
                # But NOT bare roman numerals like "I." — those are sub-sections
                is_bare_roman = bool(re.match(r"^[IVXLCDM]+\.\s*$", next_line_clean))
                if (next_line_clean and next_line_clean.isupper()
                        and heading_text.isupper()
                        and len(next_line_clean) < 100
                        and not is_bare_roman):
                    subtitle_lines.append(next_line_clean)
                    k = j + 1
                    while k < total and lines[k].strip() and lines[k].strip().isupper():
                        subtitle_lines.append(lines[k].strip())
                        k += 1
                    heading_text = heading_text + " " + " ".join(subtitle_lines)
                    j = k
                # Short, Title-Case subtitle (not a paragraph start)
                # Must be very short (< 50 chars) and look like a title
                elif (next_line_clean and len(next_line_clean) < 50
                        and not _is_heading(next_line_clean)
                        and not next_line_clean[0].islower()
                        and next_line_clean[0].isupper()
                        and not next_line_clean[-1] in ".!?;,"):
                    subtitle_lines.append(next_line_clean)
                    j = j + 1

            md_lines.append(f"{'#' * level} {heading_text}")
            if subtitle_lines and not subtitle_lines[0].isupper():
                md_lines.append("")
                md_lines.append(f"*{subtitle_lines[0]}*")
            md_lines.append("")
            i = j if subtitle_lines else i + 1
            prev_blank = True
            prev_was_heading = True
            continue

        # Normal text line
        md_lines.append(stripped)
        prev_blank = False
        prev_was_heading = False
        in_paragraph = True
        i += 1

    return "\n".join(md_lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Reference File Generation
# ---------------------------------------------------------------------------

def write_reference(book_dir: str, meta: dict) -> str:
    """Write a reference.md file with Gutenberg metadata."""
    ref_path = os.path.join(book_dir, "reference.md")

    lines = [
        f"# Reference: {meta.get('title', 'Unknown')}",
        "",
        "## Source",
        "",
        f"- **Project Gutenberg ID**: {meta.get('ebook_id', '?')}",
        f"- **URL**: {meta.get('gutenberg_url', 'N/A')}",
        f"- **Rights**: {meta.get('rights', 'Public domain in the USA.')}",
        "",
    ]

    if meta.get("author"):
        lines += [
            "## Author",
            "",
            f"- **Name**: {meta['author']}",
            "",
        ]

    if meta.get("published"):
        lines += [f"- **Gutenberg Published**: {meta['published']}", ""]

    if meta.get("language"):
        lines += [
            "## Language",
            "",
            f"- {meta['language']}",
            "",
        ]

    if meta.get("subjects"):
        lines += ["## Subjects", ""]
        for s in meta["subjects"]:
            lines.append(f"- {s}")
        lines.append("")

    if meta.get("summary"):
        lines += [
            "## Summary",
            "",
            meta["summary"],
            "",
        ]

    if meta.get("note"):
        lines += [
            "## Notes",
            "",
            meta["note"],
            "",
        ]

    content = "\n".join(lines)
    with open(ref_path, "w", encoding="utf-8") as f:
        f.write(content)

    return ref_path


# ---------------------------------------------------------------------------
# Download Orchestration
# ---------------------------------------------------------------------------

def download_book(ebook_id: int, title: str | None = None) -> str:
    """Download a book, convert to Markdown, and save with reference."""
    # Fetch metadata
    print(f"  Fetching metadata for Gutenberg #{ebook_id}...")
    meta = fetch_metadata(ebook_id)
    title = title or meta.get("title") or f"Book_{ebook_id}"
    meta["title"] = title

    book_dir = os.path.join(REPO_ROOT, title)
    os.makedirs(book_dir, exist_ok=True)

    slug = slugify(title)
    out_path = os.path.join(book_dir, f"{slug}.md")

    # Download plain text
    print(f"  Downloading: {title} (Gutenberg #{ebook_id})")
    url = GUTENBERG_TXT_URL.format(ebook_id=ebook_id)
    raw_text = fetch_url(url)

    # Strip boilerplate
    clean_text = strip_boilerplate(raw_text)

    # Convert to structured Markdown
    markdown = text_to_markdown(clean_text, meta)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(markdown)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"  Saved: {out_path} ({size_kb:.1f} KB)")

    # Write reference file
    ref_path = write_reference(book_dir, meta)
    print(f"  Saved: {ref_path}")

    return out_path


def parse_catalog(catalog_path: str) -> list[tuple[int, str | None]]:
    """Parse a catalog file. Each line: <ebook_id>[\\t<title>]"""
    entries = []
    with open(catalog_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            try:
                ebook_id = int(parts[0].strip())
            except ValueError:
                print(f"  Warning: skipping non-numeric ID on line {line_num}: {parts[0]!r}")
                continue
            title = parts[1].strip() if len(parts) >= 2 else None
            entries.append((ebook_id, title))
    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_search(args):
    """Handle the 'search' subcommand."""
    # Build query string — Gutenberg OPDS uses plain keyword search,
    # not field-specific prefixes
    parts = []
    if args.author:
        parts.append(args.author)
    if args.title:
        parts.append(args.title)
    if args.subject:
        parts.append(args.subject)
    if args.language:
        parts.append(f"l.{args.language}")
    if args.query:
        parts.append(args.query)

    if not parts:
        print("Error: Provide at least one search term (--author, --title, --subject, or keyword).")
        sys.exit(1)

    query = " ".join(parts)
    print(f"Searching Gutenberg for: {query}\n")

    results = search_gutenberg(query, max_results=args.max_results)
    if not results:
        print("No results found.")
        return

    # Display results
    print(f"{'ID':>6}  {'Title':<55} {'Author':<30}")
    print("-" * 95)
    for r in results:
        title = r["title"][:53]
        author = (r["author"] or "—")[:28]
        subjects = ", ".join(r.get("subjects", [])[:3])
        print(f"{r['ebook_id']:>6}  {title:<55} {author:<30}")
        if subjects:
            print(f"{'':>8}Subjects: {subjects}")

    print(f"\n{len(results)} result(s). Download with: "
          f"python scripts/download_gutenberg.py download <ID>")


def cmd_download(args):
    """Handle the 'download' subcommand."""
    print(f"Downloading Gutenberg #{args.ebook_id}...")
    try:
        path = download_book(args.ebook_id, title=args.title)
        print(f"\nDone. Book saved to: {path}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_catalog(args):
    """Handle the 'catalog' subcommand."""
    entries = parse_catalog(args.catalog_file)
    if not entries:
        print("No valid entries found in catalog file.")
        sys.exit(1)

    print(f"Catalog loaded: {len(entries)} book(s)\n")
    downloaded = []

    for ebook_id, title in entries:
        try:
            path = download_book(ebook_id, title=title)
            downloaded.append(path)
        except Exception as exc:
            print(f"  ERROR downloading #{ebook_id}: {exc}", file=sys.stderr)
        print()

    print(f"Done. {len(downloaded)}/{len(entries)} book(s) downloaded.")


def main():
    parser = argparse.ArgumentParser(
        description="Download and structure books from Project Gutenberg.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- search ---
    sp_search = subparsers.add_parser("search", help="Search the Gutenberg catalog")
    sp_search.add_argument("query", nargs="?", default="", help="General search keywords")
    sp_search.add_argument("--author", "-a", help="Filter by author name")
    sp_search.add_argument("--title", "-t", help="Filter by title keyword")
    sp_search.add_argument("--subject", "-s", help="Filter by subject/topic")
    sp_search.add_argument("--language", "-l", help="Filter by language (e.g. 'en', 'fr')")
    sp_search.add_argument("--max-results", "-n", type=int, default=25, help="Max results (default: 25)")
    sp_search.set_defaults(func=cmd_search)

    # --- download ---
    sp_download = subparsers.add_parser("download", help="Download a book by Gutenberg ID")
    sp_download.add_argument("ebook_id", type=int, help="Project Gutenberg ebook ID")
    sp_download.add_argument("--title", help="Override book title (auto-detected if omitted)")
    sp_download.set_defaults(func=cmd_download)

    # --- catalog ---
    sp_catalog = subparsers.add_parser("catalog", help="Download books from a catalog file")
    sp_catalog.add_argument("catalog_file", help="Path to catalog file (tab-separated: ID\\tTitle)")
    sp_catalog.set_defaults(func=cmd_catalog)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
