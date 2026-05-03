#!/usr/bin/env python3
"""Download books from Internet Archive as structured Markdown.

Commands:
    search    - Search IA catalog by query
    download  - Download a book by IA identifier
    catalog   - Download multiple books from a catalog file
    survey    - Show download/ingest status for the corpus

Usage:
    # Search for Audel manuals
    python scripts/download_ia.py search "audel electric"
    python scripts/download_ia.py search "audels electricians plumbers guide"

    # Download a single item by IA identifier
    python scripts/download_ia.py download audelselectriciansguide01ande --genre audel-electric

    # Download with explicit title override
    python scripts/download_ia.py download someidentifier --title "My Title" --genre audel-electric

    # Download multiple books from a catalog file
    python scripts/download_ia.py catalog scripts/catalogs/audel-electric.txt --genre audel-electric

    # Survey what has been downloaded and ingested
    python scripts/download_ia.py survey
    python scripts/download_ia.py survey --genre audel-electric

    # Dry run (print actions without writing)
    python scripts/download_ia.py download someidentifier --genre audel-electric --dry-run

    # Force re-download even if already present
    python scripts/download_ia.py download someidentifier --genre audel-electric --force

Output structure (per book):
    corpus/<genre>/<Title>/
        <slug>.md        - Structured Markdown with section headings
        reference.md     - Internet Archive metadata sidecar

The Markdown output detects chapter/section headings, elevates Q&A pairs
(Ques./Ans. format) to h4 nodes, and cleans common OCR artifacts from
scanned DjVu text layers — making it directly compatible with DocKG's
`dockg build` and KGRAG's corpus ingestion pipelines.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IA_METADATA_URL = "https://archive.org/metadata/{identifier}"
IA_SEARCH_URL   = "https://archive.org/advancedsearch.php"
IA_DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"
IA_DETAILS_URL  = "https://archive.org/details/{identifier}"

REPO_ROOT   = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "corpus"

ALL_GENRES = ["audel-electric"]

# Unicode ligature normalization: OCR commonly mis-encodes these
LIGATURES: dict[str, str] = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}

# ---------------------------------------------------------------------------
# Heading patterns for technical / encyclopedia texts
# Order matters: more specific patterns first.
# Each tuple: (compiled regex, markdown heading level)
# ---------------------------------------------------------------------------

HEADING_PATTERNS = [
    # CHAPTER I / CHAPTER 1 / CHAPTER XIV — optional subtitle after separator
    (re.compile(
        r"^CHAPTER\s+(?:[IVXLCDM]{1,7}|\d+)\.?"
        r"(?:\s*[-—:.]?\s*(.+))?$",
        re.IGNORECASE,
    ), 2),
    # PART ONE / PART I / PART 1 — optional subtitle
    (re.compile(
        r"^PART\s+(?:ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|"
        r"[IVXLCDM]{1,7}|\d+)\.?"
        r"(?:\s*[-—:.]?\s*(.+))?$",
        re.IGNORECASE,
    ), 2),
    # SECTION / DIVISION — numbered
    (re.compile(
        r"^(?:SECTION|DIVISION)\s+(?:[IVXLCDM]{1,7}|\d+)\.?"
        r"(?:\s*[-—:.]?\s*(.+))?$",
        re.IGNORECASE,
    ), 2),
    # Standalone ALL-CAPS heading: 3–60 chars, only uppercase letters/spaces/basic punct
    # e.g. "DIRECT CURRENTS", "OHM'S LAW AND ITS APPLICATIONS"
    (re.compile(r"^([A-Z][A-Z\s\-\',:]{2,59})$"), 3),
    # Q&A format: "Ques. <question text>" — each question becomes an h4 graph node
    (re.compile(r"^Ques\.\s+(.{5,120})$", re.IGNORECASE), 4),
]

# Indices into HEADING_PATTERNS for special handling
_PAT_ALL_CAPS = 3
_PAT_QUES     = 4

# Illustration / figure markers to strip
FIGURE_RE = re.compile(
    r"\[(?:Illustration|Fig\.?|Figure|Plate|Diagram)[^\]]*\]",
    re.IGNORECASE,
)

# Index section detection (strip from here to EOF when near end of doc)
INDEX_HEADING_RE = re.compile(r"^\s*INDEX\s*$", re.IGNORECASE)

# Table of contents heading detection
TOC_HEADING_RE = re.compile(
    r"^\s*(?:TABLE\s+OF\s+)?CONTENTS\.?\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def slugify(title: str) -> str:
    """Convert a title to a filesystem-friendly slug (underscores)."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug.strip("_")


def fetch_url(url: str, retries: int = 3, backoff: float = 2.0) -> str:
    """Fetch URL with retries and exponential backoff."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AudelKG/1.0 (archive.org research)"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8-sig", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            if attempt == retries - 1:
                raise
            wait = backoff * (2 ** attempt)
            print(f"  Retry {attempt + 1}/{retries} after error: {exc}  (waiting {wait:.0f}s)")
            time.sleep(wait)
    return ""


# ---------------------------------------------------------------------------
# Internet Archive Metadata
# ---------------------------------------------------------------------------

def _coerce_str(value: object) -> str:
    """Return first element if list, else str; empty string if falsy."""
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value).strip() if value else ""


def _coerce_list(value: object) -> list[str]:
    """Always return a list of stripped strings."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    return [s] if s else []


def fetch_ia_metadata(identifier: str) -> dict:
    """Fetch item metadata from the Internet Archive JSON API.

    Returns a flat dict with keys: identifier, title, author, publisher,
    date, subjects, language, description, volume, series, edition, rights,
    plus '_files' (raw file list for text discovery).
    """
    url = IA_METADATA_URL.format(identifier=identifier)
    raw = fetch_url(url)
    data = json.loads(raw)

    ia = data.get("metadata", {})
    files = data.get("files", [])

    meta: dict = {"identifier": identifier, "_files": files}

    meta["title"]     = _coerce_str(ia.get("title", "")) or identifier
    meta["author"]    = _coerce_str(ia.get("creator", ""))
    meta["publisher"] = _coerce_str(ia.get("publisher", ""))
    meta["volume"]    = _coerce_str(ia.get("volume") or ia.get("volumenumber", ""))
    meta["series"]    = _coerce_str(ia.get("series", ""))
    meta["edition"]   = _coerce_str(ia.get("edition", ""))
    meta["language"]  = _coerce_str(ia.get("language", "eng")) or "eng"
    meta["subjects"]  = _coerce_list(ia.get("subject", []))

    # Date: keep only the year
    raw_date = _coerce_str(ia.get("date", ""))
    meta["date"] = raw_date[:4] if raw_date else ""

    # Description: may contain HTML
    raw_desc = ia.get("description", "")
    if isinstance(raw_desc, list):
        raw_desc = " ".join(raw_desc)
    raw_desc = re.sub(r"<[^>]+>", " ", str(raw_desc))
    meta["description"] = re.sub(r"\s+", " ", raw_desc).strip()

    # Rights
    access = _coerce_str(ia.get("identifier-access") or ia.get("licenseurl", ""))
    if not access or "publicdomain" in access.lower():
        meta["rights"] = "Public domain"
    else:
        meta["rights"] = access

    return meta


def find_text_file(identifier: str, files: list[dict]) -> tuple[str, str] | None:
    """Find the best available plain-text file in an IA item.

    Priority: DjVu Text (_djvu.txt) > plain .txt
    Returns (filename, format_label) or None.
    """
    # DjVu text layer — cleanest OCR output from scanned books
    djvu = [
        f["name"] for f in files
        if f.get("name", "").endswith("_djvu.txt")
    ]
    if djvu:
        return (min(djvu, key=len), "DjVu Text")

    # Fallback: any plain text file that isn't metadata/readme
    txt = [
        f["name"] for f in files
        if (
            f.get("name", "").endswith(".txt")
            and "readme" not in f.get("name", "").lower()
            and "_meta" not in f.get("name", "").lower()
            and "_files" not in f.get("name", "").lower()
        )
    ]
    if txt:
        return (min(txt, key=len), "Plain Text")

    return None


def fetch_text(identifier: str, files: list[dict]) -> str | None:
    """Download the best available text for an IA item. Returns raw text or None."""
    result = find_text_file(identifier, files)
    if result is None:
        print(f"  [!] No text file found for {identifier!r}")
        print(f"  [!] Available formats: {sorted({f.get('format','?') for f in files})}")
        return None

    filename, fmt = result
    url = IA_DOWNLOAD_URL.format(identifier=identifier, filename=urllib.parse.quote(filename))
    print(f"  Downloading {fmt}: {filename}")
    try:
        return fetch_url(url)
    except Exception as exc:
        print(f"  [!] Download failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# OCR Cleaning
# ---------------------------------------------------------------------------

def _detect_running_headers(lines: list[str]) -> frozenset[str]:
    """Return the set of short lines that appear 4+ times — running headers/footers."""
    short = [ln.strip() for ln in lines if 3 < len(ln.strip()) < 80]
    counts = Counter(short)
    # Exclude obvious section headings (they may legitimately repeat at start)
    return frozenset(
        line for line, n in counts.items()
        if n >= 4 and not INDEX_HEADING_RE.match(line)
    )


def clean_ocr(text: str) -> str:
    """Clean common OCR artifacts from Internet Archive DjVu text.

    Steps (in order):
    1. Normalize unicode ligatures and common smart-quote variants
    2. Join hyphenated line-breaks (OCR word-wrap artifact)
    3. Strip bare page-number lines
    4. Remove running headers/footers (lines that repeat 4+ times)
    5. Strip the back-of-book index section
    6. Remove figure/illustration markers
    7. Collapse excessive blank lines
    """
    # 1. Ligatures and smart quotes
    for ligature, replacement in LIGATURES.items():
        text = text.replace(ligature, replacement)
    text = (text
            .replace("’", "'")   # right single quote
            .replace("‘", "'")   # left single quote
            .replace("“", '"')   # left double quote
            .replace("”", '"')   # right double quote
            .replace("­", ""))   # soft hyphen (remove entirely)

    # 2. Join hyphenated line-breaks: "mag-\nnetism" → "magnetism"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # 3. Bare page-number lines (1–4 digit number alone on a line)
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)

    # 4. Running headers / footers
    lines = text.split("\n")
    running = _detect_running_headers(lines)
    if running:
        lines = [ln for ln in lines if ln.strip() not in running]
        text = "\n".join(lines)

    # 5. Strip the index section if it starts in the last 30% of the document
    last_index_match: re.Match | None = None
    for m in INDEX_HEADING_RE.finditer(text):
        last_index_match = m
    if last_index_match and last_index_match.start() > len(text) * 0.70:
        text = text[: last_index_match.start()].rstrip() + "\n"

    # 6. Figure / illustration markers
    text = FIGURE_RE.sub("", text)

    # 7. Collapse 3+ consecutive blank lines to 2
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text


# ---------------------------------------------------------------------------
# Text → Markdown Conversion
# ---------------------------------------------------------------------------

def _is_heading(line: str) -> tuple[int, str] | None:
    """Check if a stripped line is a structural heading.

    Returns (level, heading_text) or None.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return None

    for idx, (pattern, level) in enumerate(HEADING_PATTERNS):
        m = pattern.match(stripped)
        if not m:
            continue

        if idx == _PAT_ALL_CAPS:
            # Reject sentence-like lines and noise
            if stripped.endswith((".", "!", "?", ",", ";")):
                continue
            if len(stripped) > 60:
                continue
            words = stripped.split()
            if len(words) > 8:
                continue
            # Reject single very short words (OCR noise)
            if len(words) == 1 and len(stripped) < 5:
                continue
            # Must contain at least one alphabetic char
            if not any(c.isalpha() for c in stripped):
                continue

        # For Ques. pattern, return the full line as heading text
        if idx == _PAT_QUES:
            return (level, stripped)

        return (level, stripped)

    return None


def _find_toc_range(lines: list[str]) -> range:
    """Detect a table-of-contents block near the top and return its line range."""
    for i, line in enumerate(lines[:300]):
        if TOC_HEADING_RE.match(line.strip()):
            # TOC ends at 3+ consecutive blank lines or 400 lines later
            blank_run = 0
            for j in range(i + 1, min(i + 400, len(lines))):
                if not lines[j].strip():
                    blank_run += 1
                    if blank_run >= 3:
                        return range(i, j)
                else:
                    blank_run = 0
            return range(i, min(i + 400, len(lines)))
    return range(0)


def text_to_markdown(text: str, meta: dict) -> str:
    """Convert IA OCR text to structured Markdown.

    Pipeline:
    1. Clean OCR artifacts (ligatures, hyphenation, running headers, index)
    2. Add title / author / publisher front matter
    3. Skip table-of-contents region
    4. Detect headings (CHAPTER, PART, SECTION, ALL-CAPS, Ques.)
    5. For CHAPTER headings, absorb an ALL-CAPS subtitle on the next line
    6. Preserve paragraph structure; suppress extra blank lines
    """
    text = clean_ocr(text)
    lines = text.split("\n")
    total = len(lines)

    toc_range = _find_toc_range(lines)

    # --- Front matter ---
    md: list[str] = []
    title     = meta.get("title", "Untitled")
    author    = meta.get("author", "")
    publisher = meta.get("publisher", "")
    pub_date  = meta.get("date", "")
    series    = meta.get("series", "")
    volume    = meta.get("volume", "")

    md.append(f"# {title}")
    md.append("")
    if author:
        md.append(f"**{author}**")
        md.append("")
    pub_line_parts = [publisher, pub_date]
    pub_line = ", ".join(p for p in pub_line_parts if p)
    if pub_line:
        md.append(f"*{pub_line}*")
        md.append("")
    if series:
        series_line = series
        if volume:
            series_line += f", Vol. {volume}"
        md.append(f"*{series_line}*")
        md.append("")
    md.append("---")
    md.append("")

    # --- Body conversion ---
    prev_blank = True
    i = 0
    while i < total:
        if i in toc_range:
            i += 1
            continue

        stripped = lines[i].strip()

        # Blank line
        if not stripped:
            if not prev_blank:
                md.append("")
            prev_blank = True
            i += 1
            continue

        # Strip residual figure markers
        stripped = FIGURE_RE.sub("", stripped).strip()
        if not stripped:
            if not prev_blank:
                md.append("")
            prev_blank = True
            i += 1
            continue

        # Heading detection (only fire after a blank line)
        heading = _is_heading(stripped)
        if heading and prev_blank:
            level, heading_text = heading

            # For CHAPTER headings: check if next non-blank line is an ALL-CAPS
            # subtitle (e.g. "CHAPTER I." followed by "DIRECT CURRENTS")
            j = i + 1
            if level == 2 and re.match(r"^CHAPTER\b", stripped, re.IGNORECASE):
                while j < total and not lines[j].strip():
                    j += 1
                if j < total:
                    next_s = lines[j].strip()
                    next_s = FIGURE_RE.sub("", next_s).strip()
                    if (
                        next_s
                        and next_s == next_s.upper()
                        and len(next_s) < 80
                        and not _is_heading(next_s)
                        and not re.match(r"^\d", next_s)
                    ):
                        heading_text = heading_text + " — " + next_s
                        j += 1  # consume subtitle line
                    else:
                        j = i + 1  # no subtitle, reset
            else:
                j = i + 1

            md.append(f"{'#' * level} {heading_text}")
            md.append("")
            prev_blank = True
            i = j
            continue

        # Normal text line
        md.append(stripped)
        prev_blank = False
        i += 1

    return "\n".join(md).strip() + "\n"


# ---------------------------------------------------------------------------
# Reference File Generation
# ---------------------------------------------------------------------------

def write_reference(book_dir: Path, meta: dict) -> Path:
    """Write a reference.md sidecar with Internet Archive metadata."""
    ref_path = book_dir / "reference.md"

    lines = [
        f"# Reference: {meta.get('title', 'Unknown')}",
        "",
        "## Source",
        "",
        f"- **Internet Archive ID**: {meta.get('identifier', '?')}",
        f"- **URL**: {IA_DETAILS_URL.format(identifier=meta.get('identifier', '?'))}",
        f"- **Rights**: {meta.get('rights', 'Public domain')}",
        "",
    ]

    author    = meta.get("author", "")
    publisher = meta.get("publisher", "")
    pub_date  = meta.get("date", "")
    edition   = meta.get("edition", "")

    if author or publisher or pub_date:
        lines += ["## Publication", ""]
        if author:
            lines.append(f"- **Author**: {author}")
        if publisher:
            lines.append(f"- **Publisher**: {publisher}")
        if pub_date:
            lines.append(f"- **Date**: {pub_date}")
        if edition:
            lines.append(f"- **Edition**: {edition}")
        lines.append("")

    series = meta.get("series", "")
    volume = meta.get("volume", "")
    if series or volume:
        lines += ["## Series", ""]
        if series:
            lines.append(f"- **Series**: {series}")
        if volume:
            lines.append(f"- **Volume**: {volume}")
        lines.append("")

    lang = meta.get("language", "")
    if lang:
        lines += ["## Language", "", f"- {lang}", ""]

    subjects = meta.get("subjects", [])
    if subjects:
        lines += ["## Subjects", ""]
        for s in subjects:
            lines.append(f"- {s}")
        lines.append("")

    desc = meta.get("description", "")
    if desc:
        lines += ["## Summary", "", desc, ""]

    ref_path.write_text("\n".join(lines), encoding="utf-8")
    return ref_path


# ---------------------------------------------------------------------------
# Download Orchestration
# ---------------------------------------------------------------------------

def download_book(
    identifier: str,
    title: str | None = None,
    genre: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> str | None:
    """Download an IA item, convert to Markdown, write reference.md.

    Returns path to the .md file on success, None on failure.
    """
    print(f"  Fetching metadata for {identifier!r}...")
    try:
        meta = fetch_ia_metadata(identifier)
    except Exception as exc:
        print(f"  [!] Metadata fetch failed: {exc}")
        return None

    if title:
        meta["title"] = title
    item_title = meta.get("title") or identifier
    files = meta.pop("_files", [])

    # Resolve output directory
    base = CORPUS_ROOT / genre if genre else CORPUS_ROOT
    book_dir = base / item_title
    slug = slugify(item_title)
    md_path = book_dir / f"{slug}.md"

    if md_path.exists() and not force:
        print(f"  [=] Already exists: {md_path} (use --force to re-download)")
        return str(md_path)

    if dry_run:
        print(f"  [dry] Would write: {md_path}")
        print(f"  [dry] Would write: {book_dir / 'reference.md'}")
        return str(md_path)

    # Download text
    text = fetch_text(identifier, files)
    if text is None:
        return None

    print(f"  Converting {len(text):,} chars to Markdown...")
    markdown = text_to_markdown(text, meta)

    # Write files
    book_dir.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    print(f"  [✓] Markdown: {md_path}  ({len(markdown):,} chars)")

    write_reference(book_dir, meta)
    print(f"  [✓] Reference: {book_dir / 'reference.md'}")

    return str(md_path)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_ia(query: str, max_results: int = 25) -> list[dict]:
    """Search Internet Archive texts. Returns list of result dicts."""
    params = urllib.parse.urlencode(
        {
            "q": query,
            "mediatype": "texts",
            "output": "json",
            "rows": str(max_results),
            "fl[]": ["identifier", "title", "creator", "date", "publisher"],
            "sort[]": "date desc",
        },
        doseq=True,
    )
    url = f"{IA_SEARCH_URL}?{params}"
    raw = fetch_url(url)
    data = json.loads(raw)

    results = []
    for doc in data.get("response", {}).get("docs", []):
        creator = doc.get("creator", "")
        if isinstance(creator, list):
            creator = ", ".join(creator)
        date_str = str(doc.get("date", ""))
        results.append({
            "identifier": doc.get("identifier", ""),
            "title":      doc.get("title", ""),
            "author":     creator.strip(),
            "date":       date_str[:4] if date_str else "",
            "publisher":  _coerce_str(doc.get("publisher", "")),
        })

    return results


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> int:
    query = " ".join(args.query)
    print(f"Searching Internet Archive: {query!r}\n")
    try:
        results = search_ia(query, max_results=args.n)
    except Exception as exc:
        print(f"Search failed: {exc}", file=sys.stderr)
        return 1

    if not results:
        print("No results.")
        return 0

    id_w = max(len(r["identifier"]) for r in results) + 2
    print(f"{'Identifier':<{id_w}} {'Year':<6} Title")
    print("-" * (id_w + 60))
    for r in results:
        print(f"{r['identifier']:<{id_w}} {r['date']:<6} {r['title']}")
    print(f"\n{len(results)} result(s).")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    result = download_book(
        identifier=args.identifier,
        title=args.title,
        genre=args.genre,
        force=args.force,
        dry_run=args.dry_run,
    )
    return 0 if result else 1


def cmd_catalog(args: argparse.Namespace) -> int:
    catalog_path = Path(args.catalog)
    if not catalog_path.exists():
        print(f"ERROR: catalog not found: {catalog_path}", file=sys.stderr)
        return 1

    entries: list[tuple[str, str | None]] = []
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t", 1)
        identifier = parts[0].strip()
        title = parts[1].strip() if len(parts) > 1 else None
        if identifier:
            entries.append((identifier, title))

    if not entries:
        print("No entries in catalog.")
        return 0

    print(f"Processing {len(entries)} item(s) from {catalog_path.name}...\n")
    failures = 0
    for identifier, title in entries:
        print(f"[{identifier}]")
        result = download_book(
            identifier=identifier,
            title=title,
            genre=args.genre,
            force=args.force,
            dry_run=args.dry_run,
        )
        if result is None:
            failures += 1
        if not args.dry_run:
            time.sleep(1.5)  # polite delay between IA requests
        print()

    ok = len(entries) - failures
    print(f"Done: {ok}/{len(entries)} succeeded, {failures} failed.")
    return 0 if failures == 0 else 1


def cmd_survey(args: argparse.Namespace) -> int:
    genres = [args.genre] if args.genre else ALL_GENRES

    total_md = total_ref = total_kg = 0
    for genre in genres:
        genre_dir = CORPUS_ROOT / genre
        if not genre_dir.is_dir():
            print(f"  {genre}: (no directory)")
            continue

        book_dirs = sorted(
            p for p in genre_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
        print(f"\n=== {genre} ({len(book_dirs)} books) ===")
        print(f"  {'Book':<50} {'MD':>3} {'REF':>4} {'KG':>4}")
        print(f"  {'-' * 62}")
        for bd in book_dirs:
            has_md  = any(
                f for f in bd.glob("*.md") if f.name != "reference.md"
            )
            has_ref = (bd / "reference.md").exists()
            has_kg  = (bd / ".dockg" / "graph.sqlite").exists()
            md_m    = "✓" if has_md  else "-"
            ref_m   = "✓" if has_ref else "-"
            kg_m    = "✓" if has_kg  else "-"
            total_md  += int(has_md)
            total_ref += int(has_ref)
            total_kg  += int(has_kg)
            print(f"  {bd.name:<50} {md_m:>3} {ref_m:>4} {kg_m:>4}")

    print(f"\nTotals — md: {total_md}  ref: {total_ref}  kg: {total_kg}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Download Internet Archive books as structured Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="command", required=True)

    # search
    sp = sub.add_parser("search", help="Search Internet Archive for texts")
    sp.add_argument("query", nargs="+", help="Search terms")
    sp.add_argument("-n", type=int, default=25, metavar="N", help="Max results (default 25)")

    # download
    sp = sub.add_parser("download", help="Download a single IA item by identifier")
    sp.add_argument("identifier", help="Internet Archive identifier")
    sp.add_argument("--title",   help="Override the book title (affects directory name)")
    sp.add_argument("--genre",   choices=ALL_GENRES, help="Genre subdirectory")
    sp.add_argument("--force",   action="store_true", help="Re-download if already exists")
    sp.add_argument("--dry-run", action="store_true", help="Print actions without writing files")

    # catalog
    sp = sub.add_parser("catalog", help="Download all items from a catalog file")
    sp.add_argument("catalog", help="Path to catalog .txt file (tab-separated id [title])")
    sp.add_argument("--genre",   choices=ALL_GENRES, help="Genre for all items")
    sp.add_argument("--force",   action="store_true")
    sp.add_argument("--dry-run", action="store_true")

    # survey
    sp = sub.add_parser("survey", help="Show download/ingest status for corpus")
    sp.add_argument("--genre", choices=ALL_GENRES, help="Filter to one genre")

    return p


def main() -> int:
    args = build_parser().parse_args()
    dispatch = {
        "search":   cmd_search,
        "download": cmd_download,
        "catalog":  cmd_catalog,
        "survey":   cmd_survey,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
