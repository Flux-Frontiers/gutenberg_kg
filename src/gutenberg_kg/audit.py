"""audit.py — Verify Project Gutenberg corpus integrity.

Checks each book under ``corpus/`` for the invariants that ``download`` /
``ingest`` / ``build-corpus`` assume, catching the failure modes that are easy
to introduce by hand:

- missing full-text ``.md`` or ``reference.md``;
- a diary whose ``.md`` does not parse with its declared ``.diary_format``
  (wrong/missing format);
- a stray ``.dockg/`` inside a diary directory (diaries must use ``.diarykg/``);
- the same Gutenberg ID assigned to more than one book (a mix-up/swap);
- a catalog title override that differs from the directory name of the book
  already downloaded for that ID (catalog/corpus naming drift);
- a downloaded book that its genre catalog does not list at all;
- a registered KG whose index file no longer exists, or a diary registered to
  a ``.dockg`` index instead of ``.diarykg``.

"Not built" / "not registered" / "not recorded in the catalog" are warnings
(the first two are expected on a fresh clone before ``rebuild-indices``); the
rest are errors.  ``run_audit`` returns a non-zero exit code when any error is
found, so it is CI-friendly.

Note the two catalog checks run in opposite directions and only together cover
membership.  The title check walks catalog entries and looks up books; the
uncatalogued check walks books and looks up catalog entries.  Only the first
existed for a long time, which is how 90 of 243 books came to be missing from
their catalogs while every book audited clean.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from gutenberg_kg.authors import parse_reference
from gutenberg_kg.genres import ALL_GENRES, IA_GENRES
from gutenberg_kg.gutenberg import parse_catalog
from gutenberg_kg.ia import parse_catalog as parse_ia_catalog
from gutenberg_kg.ingest import slugify

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPO_ROOT / "corpus"
CATALOG_ROOT = REPO_ROOT / "scripts" / "catalogs"
DIARIES_GENRE = "diaries"

# Curated catalog titles that intentionally differ from the Gutenberg canonical
# title (a shortened form, or an alternate translation/romanization of the same
# work). These are verified same-work, so the title/content check below
# allowlists them by Gutenberg ID rather than flagging them as swaps.
KNOWN_TITLE_VARIANTS: frozenset[int] = frozenset(
    {
        2147,  # Tales of Mystery and Imagination  ~ The Works of Poe, Vol. 1
        779,  # Doctor Faustus              ~ The Tragical History of Doctor Faustus
        829,  # Gulliver's Travels          ~ ...into Several Remote Nations of the World
        2610,  # The Hunchback of Notre-Dame ~ Notre-Dame de Paris
        2229,  # Faust Part I                ~ Faust: Der Tragödie erster Teil
        6762,  # Politics                    ~ Politics: A Treatise on Government
        2017,  # Dhammapada                  ~ The Dhammapada, a Collection of Verses...
        216,  # Tao Te Ching                ~ The Tao Teh King...
        4094,  # The Analects of Confucius   ~ The Chinese Classics, Vol. 1
        2388,  # The Bhagavad Gita           ~ The Song Celestial
        2800,  # The Quran                   ~ The Koran
        1900,  # Typee: A Peep at ...        ~ Typee: A Romance of the South Seas
        128,  # One Thousand and One Nights ~ The Arabian Nights Entertainments
        674,  # Parallel Lives              ~ Plutarch: Lives of the Noble Grecians and Romans
        8438,  # Nicomachean Ethics          ~ The Ethics of Aristotle
    }
)

_QUOTE_RE = re.compile(r"[\"“”″]([^\"“”″]{2,120})[\"“”″]")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class BookAudit:
    """Audit result for a single book directory."""

    genre: str
    book: str
    is_diary: bool
    ebook_id: int | None = None
    ia_id: str | None = None  # Internet Archive identifier, for IA-genre books
    fmt: str | None = None  # diary parser format
    entries: int | None = None  # diary parsed-entry count
    built: bool = False
    registered: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when the book has no errors *and* no warnings."""
        return not self.errors and not self.warnings

    @property
    def status(self) -> str:
        """One-word status: ERROR / WARN / OK."""
        if self.errors:
            return "ERROR"
        if self.warnings:
            return "WARN"
        return "OK"


@dataclass
class AuditReport:
    """Aggregated audit results plus corpus-wide findings."""

    books: list[BookAudit] = field(default_factory=list)
    registry_orphans: list[str] = field(default_factory=list)
    registry_found: bool = True

    @property
    def n_errors(self) -> int:
        """Number of books with at least one error (+ registry orphans)."""
        return sum(1 for b in self.books if b.errors) + len(self.registry_orphans)

    @property
    def n_warnings(self) -> int:
        """Number of books with warnings but no errors."""
        return sum(1 for b in self.books if b.warnings and not b.errors)


# ---------------------------------------------------------------------------
# Registry access (direct SQLite read — no kg_rag dependency)
# ---------------------------------------------------------------------------


def _registry_path(override: str | Path | None = None) -> Path:
    """Return the KGRAG registry path, preferring kg_rag's own default."""
    if override:
        return Path(override)
    try:
        from kg_rag.registry import default_registry_path

        return Path(default_registry_path())
    except Exception:  # noqa: BLE001 - kg_rag optional; fall back to the known default
        return Path.home() / ".kgrag" / "registry.sqlite"


def _load_registry(reg_path: Path) -> dict[str, str | None]:
    """Return ``{kg_name: sqlite_path}`` for every registered KG, or ``{}``."""
    if not reg_path.exists():
        return {}
    try:
        with sqlite3.connect(reg_path) as con:
            return {
                name: sp for name, sp in con.execute("SELECT name, sqlite_path FROM kg_entries")
            }
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# Per-book checks
# ---------------------------------------------------------------------------


def _find_md(book_dir: Path) -> Path | None:
    cands = [p for p in book_dir.glob("*.md") if p.name != "reference.md"]
    return cands[0] if cands else None


def _summary_title(ref_text: str) -> str | None:
    """Return the first quoted title in the ``## Summary`` section, if any.

    The auto-generated summary opens with ``"<real title>" by <author>``, so the
    quoted string reflects the *actual* fetched text (independent of the catalog
    title in the reference header).
    """
    m = re.search(r"##\s*Summary\s*\n+(.+)", ref_text, re.S)
    if not m:
        return None
    q = _QUOTE_RE.search(m.group(1))
    return q.group(1).strip() if q else None


def _norm_title(s: str) -> str:
    """Normalize a title for comparison: drop parentheticals, an em-dash author
    suffix, apostrophes, punctuation, and common stop-words."""
    s = re.sub(r"\(.*?\)", " ", s)  # "(Forster)", "(James Legge translation)"
    s = re.sub(r"\s+[—–-]\s+.*$", " ", s)  # " — George Bernard Shaw"
    s = s.replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    s = re.sub(r"\b(the|a|an|of|and|or|to)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _titles_agree(header: str, summary: str) -> bool:
    """True when the reference title and the summary's title plausibly name the
    same work (shared significant tokens or high string similarity)."""
    h, s = _norm_title(header), _norm_title(summary)
    if not h or not s:
        return True  # not enough signal to judge — don't flag
    ht, st = set(h.split()), set(s.split())
    short, long = (ht, st) if len(ht) <= len(st) else (st, ht)
    if short and len(short & long) / len(short) >= 0.6:
        return True
    return SequenceMatcher(None, h, s).ratio() >= 0.5


def _title_content_error(ref: Path, meta: dict, book_dir: Path) -> str | None:
    """Return an error string when the reference title and the auto-summary's
    quoted title name clearly different works — the fingerprint of a wrong
    Gutenberg ID that silently mislabels a whole book. ``None`` when they agree,
    when there is no signal, or when the book is an allowlisted title variant.
    """
    ebook_id = meta.get("ebook_id")
    if ebook_id is None or ebook_id in KNOWN_TITLE_VARIANTS:
        return None
    stitle = _summary_title(ref.read_text(encoding="utf-8"))
    ref_title = meta.get("title") or book_dir.name
    if stitle and not _titles_agree(ref_title, stitle):
        return (
            f"title/content mismatch: reference titled '{ref_title}' "
            f"but content is “{stitle}” (wrong Gutenberg ID?)"
        )
    return None


def _audit_book(
    book_dir: Path,
    genre: str,
    registry: dict[str, str | None],
    registry_found: bool,
) -> BookAudit:
    """Audit a single book directory and return its :class:`BookAudit`."""
    is_diary = genre == DIARIES_GENRE
    res = BookAudit(genre=genre, book=book_dir.name, is_diary=is_diary)

    md = _find_md(book_dir)
    ref = book_dir / "reference.md"
    if md is None:
        res.errors.append("missing full-text .md")
    if not ref.exists():
        res.errors.append("missing reference.md")
    else:
        meta = parse_reference(ref)
        res.ebook_id = meta.get("ebook_id")
        res.ia_id = meta.get("ia_id")
        # Internet Archive books have an IA identifier, not a Gutenberg ID.
        if res.ebook_id is None and genre not in IA_GENRES:
            res.warnings.append("no Gutenberg ID in reference.md")
        elif res.ia_id is None and genre in IA_GENRES:
            res.warnings.append("no Internet Archive ID in reference.md")

        # Title <-> content check: a wrong Gutenberg ID silently mislabels a
        # whole book; the auto-summary's quoted title reveals the real text.
        title_err = _title_content_error(ref, meta, book_dir)
        if title_err:
            res.errors.append(title_err)

    if is_diary:
        from gutenberg_kg.diary.chunk import DEFAULT_FORMAT
        from gutenberg_kg.diary.parser import get_parser

        fmt_file = book_dir / ".diary_format"
        res.fmt = fmt_file.read_text(encoding="utf-8").strip() if fmt_file.exists() else None
        if res.fmt is None:
            res.warnings.append(f"no .diary_format (defaulting to {DEFAULT_FORMAT})")
        # The .md must parse to dated entries with the declared format.
        if md is not None:
            fmt = res.fmt or DEFAULT_FORMAT
            try:
                res.entries = sum(1 for _ in get_parser(fmt).parse(md))
            except Exception as exc:  # noqa: BLE001
                res.errors.append(f"diary parse failed ({fmt}): {exc}")
            else:
                if res.entries == 0:
                    res.errors.append(f"diary .md yields 0 entries with format '{fmt}'")
        # Diaries must never carry a standard .dockg/ index.
        if (book_dir / ".dockg").exists():
            res.errors.append("stray .dockg/ in diary dir (diaries use .diarykg/)")
        res.built = (book_dir / ".diarykg" / "graph.sqlite").exists()
        index_kind = ".diarykg"
    else:
        res.built = (book_dir / ".dockg" / "graph.sqlite").exists()
        index_kind = ".dockg"

    if not res.built:
        res.warnings.append("index not built (run rebuild-indices)")

    # Registration check.
    kg_name = f"gutenberg-{genre}-{slugify(book_dir.name)}-doc"
    if not registry_found:
        pass  # registry unavailable — skip (already noted at report level)
    elif kg_name in registry:
        res.registered = True
        sp = registry[kg_name]
        if not sp or not Path(sp).exists():
            res.errors.append("registered but index file is missing")
        elif index_kind not in sp:
            res.errors.append(f"registered to wrong index type (expected {index_kind})")
    else:
        res.warnings.append("not registered in KGRAG")

    return res


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def audit_corpus(
    genres: list[str] | None = None,
    registry: str | Path | None = None,
) -> AuditReport:
    """Audit every book in the selected genres and return an :class:`AuditReport`.

    :param genres: Genres to audit (``None`` = all genres present on disk).
    :param registry: Override KGRAG registry path.
    :return: The populated audit report.
    """
    genres = list(genres) if genres else list(ALL_GENRES)
    reg_path = _registry_path(registry)
    reg_map = _load_registry(reg_path)
    registry_found = reg_path.exists() and bool(reg_map)

    report = AuditReport(registry_found=registry_found)

    for genre in genres:
        genre_dir = CORPUS_ROOT / genre
        if not genre_dir.is_dir():
            continue
        for book_dir in sorted(genre_dir.iterdir()):
            if not book_dir.is_dir() or book_dir.name.startswith("."):
                continue
            report.books.append(_audit_book(book_dir, genre, reg_map, registry_found))

    # Corpus-wide: duplicate Gutenberg IDs.
    by_id: dict[int, list[BookAudit]] = {}
    for b in report.books:
        if b.ebook_id is not None:
            by_id.setdefault(b.ebook_id, []).append(b)
    for eid, group in by_id.items():
        if len(group) > 1:
            others = ", ".join(f"{g.genre}/{g.book}" for g in group)
            for b in group:
                b.errors.append(f"duplicate Gutenberg ID {eid} (shared by: {others})")

    # The same check for IA items. This had no coverage: the check above keys on
    # ebook_id, which is None for every IA book, so two directories holding one
    # IA item both audited clean. Path-keyed idempotence in ia.download_book
    # made that reachable by simply passing a different --title.
    by_ia_id: dict[str, list[BookAudit]] = {}
    for b in report.books:
        if b.ia_id is not None:
            by_ia_id.setdefault(b.ia_id, []).append(b)
    for ia_id, group in by_ia_id.items():
        if len(group) > 1:
            others = ", ".join(f"{g.genre}/{g.book}" for g in group)
            for b in group:
                b.errors.append(f"duplicate Internet Archive ID {ia_id} (shared by: {others})")

    # Corpus-wide: catalog title override ≠ downloaded directory name. The
    # download path is keyed on the Gutenberg ID, so drift can no longer
    # duplicate books — but the catalog is the source of truth, and an
    # override that misnames an existing directory is still a lie in it.
    def _nfc(s: str) -> str:
        return unicodedata.normalize("NFC", s)

    by_genre_id = {(b.genre, b.ebook_id): b for b in report.books if b.ebook_id is not None}
    for genre in genres:
        if genre in IA_GENRES:
            continue
        catalog = CATALOG_ROOT / f"{genre}.txt"
        if not catalog.exists():
            continue
        for eid, cat_title in parse_catalog(str(catalog)):
            b = by_genre_id.get((genre, eid))
            if b is None or cat_title is None:
                continue  # not downloaded yet, or no override to compare
            if _nfc(cat_title) != _nfc(b.book):
                b.errors.append(
                    f"catalog title '{cat_title}' ≠ directory '{b.book}' "
                    f"(fix scripts/catalogs/{genre}.txt or rename the dir)"
                )

    # Corpus-wide: a downloaded book its catalog does not list. This direction
    # had no check at all — the block above walks catalog entries and looks up
    # books, so a book absent from the catalog is never examined by any loop.
    # That blind spot is why 90 of 243 books could be uncatalogued while the
    # audit reported every book clean.
    #
    # The cost is reproducibility, not correctness: these books are healthy, but
    # `download catalog` replayed over a fresh clone rebuilds only what the
    # catalogs list, so the uncatalogued ones are silently absent. A warning,
    # not an error, for exactly that reason.
    #
    # IA genres are covered too, keyed on the Internet Archive identifier. A
    # genre is either Gutenberg or IA and never both, so which parser reads its
    # catalog is unambiguous.
    for genre in genres:
        catalog = CATALOG_ROOT / f"{genre}.txt"
        is_ia = genre in IA_GENRES
        if not catalog.exists():
            catalogued: set = set()
        elif is_ia:
            catalogued = {ident for ident, _ in parse_ia_catalog(catalog)}
        else:
            catalogued = {eid for eid, _ in parse_catalog(str(catalog))}
        for b in report.books:
            if b.genre != genre:
                continue
            key = b.ia_id if is_ia else b.ebook_id
            if key is not None and key not in catalogued:
                b.warnings.append(f"not recorded in scripts/catalogs/{genre}.txt")

    # Registered KGs (within the audited genres) whose index file is gone.
    if registry_found:
        prefixes = tuple(f"gutenberg-{g}-" for g in genres)
        for name, sp in reg_map.items():
            if name.startswith(prefixes) and (not sp or not Path(sp).exists()):
                report.registry_orphans.append(name)

    return report


def run_audit(
    genres: list[str] | None = None,
    registry: str | Path | None = None,
    as_json: bool = False,
) -> int:
    """Run the corpus audit and print a report; return a process exit code.

    :param genres: Genres to audit (empty/None = all).
    :param registry: Override KGRAG registry path.
    :param as_json: Emit machine-readable JSON instead of a Rich table.
    :return: 1 if any errors were found, else 0.
    """
    report = audit_corpus(genres, registry)

    if as_json:
        import json

        payload = {
            "registry_found": report.registry_found,
            "errors": report.n_errors,
            "warnings": report.n_warnings,
            "registry_orphans": report.registry_orphans,
            "books": [
                {
                    "genre": b.genre,
                    "book": b.book,
                    "is_diary": b.is_diary,
                    "ebook_id": b.ebook_id,
                    "format": b.fmt,
                    "entries": b.entries,
                    "built": b.built,
                    "registered": b.registered,
                    "status": b.status,
                    "errors": b.errors,
                    "warnings": b.warnings,
                }
                for b in report.books
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1 if report.n_errors else 0

    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="GutenbergKG corpus audit", show_lines=False)
    table.add_column("status", no_wrap=True)
    table.add_column("genre", no_wrap=True)
    table.add_column("book", overflow="fold")
    table.add_column("id", justify="right", no_wrap=True)
    table.add_column("detail", overflow="fold")

    style = {"OK": "green", "WARN": "yellow", "ERROR": "bold red"}
    for b in report.books:
        if b.ok:
            continue  # keep the table to problems only; counts cover the rest
        detail = "; ".join(b.errors + b.warnings)
        table.add_row(
            f"[{style[b.status]}]{b.status}[/]",
            b.genre,
            b.book,
            str(b.ebook_id) if b.ebook_id is not None else "—",
            detail,
        )

    n_ok = sum(1 for b in report.books if b.ok)
    if table.row_count:
        console.print(table)
    else:
        console.print("[green]All audited books are clean.[/]")

    if not report.registry_found:
        console.print("[yellow]note:[/] KGRAG registry not found — registration checks skipped.")
    for name in report.registry_orphans:
        console.print(f"[bold red]ERROR[/] registry orphan: {name} → index file missing")

    console.print(
        f"\n  audited {len(report.books)} books  ·  "
        f"[green]{n_ok} ok[/]  ·  "
        f"[yellow]{report.n_warnings} warn[/]  ·  "
        f"[bold red]{report.n_errors} error[/]"
    )
    return 1 if report.n_errors else 0
