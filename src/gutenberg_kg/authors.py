"""Author provenance — build ``corpus/authors/`` from ``reference.md`` files.

Entry point for callers: :func:`build`. The CLI wrapper lives at
``gutenberg_kg.cli.cmd_authors`` and exposes this as ``gutenkg authors``.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path

from gutenberg_kg.cli.options import CORPUS_ROOT, REPO_ROOT

AUTHORS_DIR = CORPUS_ROOT / "authors"


# ---------------------------------------------------------------------------
# Author names
# ---------------------------------------------------------------------------

#: Ranks that mark a catalog heading as a peerage, as in "Byron, George Gordon
#: Byron, Baron". The heading word is then the title's name, not a surname, and
#: the title stays in the display name because it is how readers know the
#: person. "Earl of", "Duke of" and the like are caught by their trailing "of".
_PEERAGE_RANKS = frozenset({"Baron", "Baroness", "Viscount", "Viscountess"})


def display_name(heading: str) -> str:
    """Turn a Gutenberg catalog heading into a name in reading order.

    Gutenberg files names library-style, ``"Surname, Forenames, Title"``.
    Splitting on the first comma alone turned "Tolstoy, Leo, graf" into
    "Leo, graf Tolstoy" and "Marcus Aurelius, Emperor of Rome" into
    "Emperor of Rome Marcus Aurelius". The rules, from the corpus's own names:

    - A parenthesized fuller form is dropped: "Wells, H. G. (Herbert George)"
      is "H. G. Wells".
    - A part with a date in it is dropped: "Sunzi, active 6th century B.C."
      is "Sunzi".
    - A peerage keeps its title: "Byron, George Gordon Byron, Baron" is
      "George Gordon Byron, Baron Byron".
    - Any other trailing title is dropped: "Tolstoy, Leo, graf" is
      "Leo Tolstoy".
    - A second part starting lowercase is an epithet and follows the name:
      "Pliny, the Younger" is "Pliny the Younger".
    - A second part containing " of " is a title: "Marcus Aurelius, Emperor of
      Rome" is "Marcus Aurelius".
    - Otherwise the forenames come first: "Dumas, Alexandre" is
      "Alexandre Dumas".

    :param heading: A name as Gutenberg's RDF or OPDS feed gives it.
    :return: The name in reading order; the heading unchanged when nothing
        in it survives the rules.
    """
    name = re.sub(r"\s*\([^)]*\)", "", heading)
    parts = [
        part.strip()
        for part in name.split(",")
        if part.strip()
        and not re.search(r"\d", part)
        and not part.strip().startswith(("active ", "fl. "))
    ]
    if not parts:
        return heading.strip()
    head, rest = parts[0], parts[1:]
    if not rest:
        return head
    given, extra = rest[0], rest[1:]
    peerage = next((p for p in extra if p in _PEERAGE_RANKS or p.endswith(" of")), None)
    if peerage:
        return f"{given}, {peerage} {head}"
    if given[0].islower():
        return f"{head} {given}"
    if " of " in given:
        return head
    return f"{given} {head}"


def credit(names: list[str]) -> str:
    """Join author names into one byline.

    :param names: Display names, primary author first.
    :return: ``"A"``, ``"A and B"``, or ``"A, B, and C"``; ``""`` for none.
    """
    if len(names) <= 2:
        return " and ".join(names)
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def author_lines(meta: dict) -> list[str]:
    """The list lines of a ``reference.md`` ``## Author`` section.

    The first author gets the Name line and the provenance lines, which
    describe that one person. Each further author gets a Co-author line.

    :param meta: Book metadata. ``authors`` is used when present, else a
        single ``author``.
    :return: The lines, without the heading; empty when there is no author.
    """
    authors = meta.get("authors") or ([meta["author"]] if meta.get("author") else [])
    if not authors:
        return []
    lines = [f"- **Name**: {authors[0]}"]
    if meta.get("author_birth"):
        lines.append(f"- **Born**: {meta['author_birth']}")
    if meta.get("author_death"):
        lines.append(f"- **Died**: {meta['author_death']}")
    if meta.get("author_url"):
        lines.append(f"- **Wikipedia**: {meta['author_url']}")
    if meta.get("author_agent_id"):
        lines.append(f"- **Gutenberg Agent ID**: {meta['author_agent_id']}")
    lines += [f"- **Co-author**: {name}" for name in authors[1:]]
    return lines


# ---------------------------------------------------------------------------
# reference.md parser
# ---------------------------------------------------------------------------


def _field(pattern: str, text: str) -> str | None:
    """Return the first capture group of *pattern* in *text*, or None if no match.

    :param pattern: Regex pattern with a single capture group.
    :param text: Text to search.
    :return: Stripped capture group, or None.
    """
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def parse_reference(path: Path) -> dict:
    """Extract author + book metadata from a ``reference.md`` file."""
    text = path.read_text(encoding="utf-8")
    meta: dict = {"_path": path}

    meta["title"] = _field(r"^# Reference:\s*(.+)$", text) or path.parent.name
    eid = _field(r"\*\*Project Gutenberg ID\*\*:\s*(\d+)", text)
    meta["ebook_id"] = int(eid) if eid else None

    # Internet Archive items have an identifier here instead of a Gutenberg ID.
    # It is a string, globally unique and immutable, so it keys an IA book the
    # same way ebook_id keys a Gutenberg one -- for download idempotence, for
    # the catalog, and for duplicate detection. ia.write_reference has always
    # written it; nothing read it until now, which is why every IA-facing check
    # had to exempt itself rather than key on something.
    meta["ia_id"] = _field(r"\*\*Internet Archive ID\*\*:\s*(\S+)", text)

    # Genre is the grandparent dir name (corpus/<genre>/<book>/reference.md)
    meta["genre"] = path.parent.parent.name

    # "author" is the byline every consumer displays; "authors" lists the
    # people, first author first, for the per-author index.
    name = _field(r"\*\*Name\*\*:\s*(.+)$", text)
    co_authors = re.findall(r"^- \*\*Co-author\*\*:\s*(.+?)\s*$", text, re.MULTILINE)
    meta["authors"] = ([name] if name else []) + co_authors
    meta["author"] = credit(meta["authors"]) or None
    meta["author_birth"] = _field(r"\*\*Born\*\*:\s*(.+)$", text)
    meta["author_death"] = _field(r"\*\*Died\*\*:\s*(.+)$", text)
    meta["author_url"] = _field(r"\*\*Wikipedia\*\*:\s*(.+)$", text)
    aid = _field(r"\*\*Gutenberg Agent ID\*\*:\s*(\d+)", text)
    meta["author_agent_id"] = int(aid) if aid else None

    return meta


# ---------------------------------------------------------------------------
# reference.md rewriter
# ---------------------------------------------------------------------------

_AUTHOR_LINE = re.compile(r"^- \*\*(Name|Born|Died|Wikipedia|Gutenberg Agent ID|Co-author)\*\*:")


def rewrite_author_section(path: Path, meta: dict, dry_run: bool = False) -> bool:
    """Replace the ``## Author`` list in a ``reference.md`` with *meta*'s.

    Only the run of author lines starting at ``- **Name**:`` is replaced; the
    rest of the file, including the Gutenberg Published line that follows the
    section, is left byte for byte. A file with no Name line, or a *meta* with
    no author (a failed fetch returns none), is never touched, so a network
    error cannot erase an author.

    :param path: The ``reference.md`` to update.
    :param meta: Fresh metadata, as ``gutenberg._fetch_rdf_author`` returns it.
    :param dry_run: Report the change without writing it.
    :return: True iff the file was (or would be) changed.
    """
    new = author_lines(meta)
    if not new:
        return False
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("- **Name**:")), None)
    if start is None:
        return False
    end = start
    while end < len(lines) and _AUTHOR_LINE.match(lines[end]):
        end += 1
    if lines[start:end] == new:
        return False
    lines[start:end] = new
    if not dry_run:
        path.write_text("\n".join(lines), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Author page + index writers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert an author name to a filesystem-safe, underscore-separated slug.

    :param name: Author name (e.g. ``"Jane Austen"``).
    :return: Lowercased slug (e.g. ``"jane_austen"``).
    """
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

    births = {b["author_birth"] for b in books if b.get("author_birth")}
    deaths = {b["author_death"] for b in books if b.get("author_death")}
    urls = {b["author_url"] for b in books if b.get("author_url")}
    agents = {b["author_agent_id"] for b in books if b.get("author_agent_id")}

    birth = next(iter(births), None)
    death = next(iter(deaths), None)
    url = next(iter(urls), None)
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
        slug = _slugify(author)
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


_NO_PROVENANCE = {
    "author_birth": None,
    "author_death": None,
    "author_url": None,
    "author_agent_id": None,
}


def _author_fields(fresh: dict) -> dict:
    """The author fields ``parse_reference`` returns once *fresh* is written.

    Lets a dry run build the index it would build for real.

    :param fresh: Refreshed author metadata with a non-empty ``authors``.
    :return: ``authors``, ``author`` and the four provenance fields.
    """
    return {
        "authors": fresh["authors"],
        "author": credit(fresh["authors"]),
        **{key: fresh.get(key) for key in _NO_PROVENANCE},
    }


def build(refresh: bool = False, dry_run: bool = False) -> int:
    """Rebuild ``corpus/authors/`` from all ``reference.md`` files.

    :param refresh: If True, re-fetch the Gutenberg RDF for every book with a
        Gutenberg ID and rewrite its ``reference.md`` Author section from it:
        every creator in catalog order (translators and editors excluded), and
        the first creator's Born/Died/Wikipedia/Agent ID. Books whose fetch
        fails, or whose RDF lists no creator, are left as they are.
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
        # Imported here: gutenberg imports this module at load time.
        from gutenberg_kg.gutenberg import _fetch_rdf_author  # noqa: PLC0415

        targets = [m for m in metas if m.get("ebook_id")]
        print(f"--- Refreshing authors from the Gutenberg RDF ({len(targets)} books) ---")
        fetched = rewritten = 0
        for m in targets:
            time.sleep(0.3)  # polite rate-limiting
            fresh = _fetch_rdf_author(m["ebook_id"])
            if not fresh.get("authors"):
                continue
            fetched += 1
            if rewrite_author_section(m["_path"], fresh, dry_run=dry_run):
                rewritten += 1
                print(
                    f"  [{m['title']}] {m.get('author') or '(none)'} -> {credit(fresh['authors'])}"
                )
                m.update(_author_fields(fresh))
        print(f"\n  RDF with creators: {fetched}  reference.md rewritten: {rewritten}\n")

    # 3. Group by author
    # One page per person, so a co-written book is listed under each author.
    # Born/Died/Wikipedia describe the first author only; a co-author's entry
    # drops them rather than borrow another person's dates.
    authors_books: dict[str, list[dict]] = defaultdict(list)
    skipped_no_author = 0
    for m in metas:
        people = m.get("authors") or []
        if not people:
            skipped_no_author += 1
            continue
        for i, person in enumerate(people):
            authors_books[person].append(m if i == 0 else {**m, **_NO_PROVENANCE})

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

    # 5. Remove pages for authors no longer in the corpus, such as a name
    # whose spelling changed. Only a directory holding nothing but a
    # generated author.md is removed; anything else there is left alone.
    live = {_slugify(author) for author in authors_books}
    stale = sorted(
        d
        for d in AUTHORS_DIR.glob("*/")
        if d.name not in live and [f.name for f in d.iterdir()] == ["author.md"]
    )
    for d in stale:
        tag = "[dry]" if dry_run else "[-]"
        print(f"  {tag} stale {d.relative_to(REPO_ROOT)}")
        if not dry_run:
            (d / "author.md").unlink()
            d.rmdir()

    # 6. Write index
    print()
    index_path = write_index(authors_books, dry_run=dry_run)
    tag = "[dry]" if dry_run else "[+]"
    print(f"  {tag} index → {index_path.relative_to(REPO_ROOT)}")
    print(f"\nDone. {len(authors_books)} author pages, {len(metas)} books.\n")
    return 0
