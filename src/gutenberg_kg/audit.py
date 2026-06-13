"""audit.py — Verify Project Gutenberg corpus integrity.

Checks each book under ``corpus/`` for the invariants that ``download`` /
``ingest`` / ``build-corpus`` assume, catching the failure modes that are easy
to introduce by hand:

- missing full-text ``.md`` or ``reference.md``;
- a diary whose ``.md`` does not parse with its declared ``.diary_format``
  (wrong/missing format);
- a stray ``.dockg/`` inside a diary directory (diaries must use ``.diarykg/``);
- the same Gutenberg ID assigned to more than one book (a mix-up/swap);
- a registered KG whose index file no longer exists, or a diary registered to
  a ``.dockg`` index instead of ``.diarykg``.

"Not built" / "not registered" are warnings (expected on a fresh clone before
``rebuild-indices``); the rest are errors.  ``run_audit`` returns a non-zero
exit code when any error is found, so it is CI-friendly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from gutenberg_kg.authors import parse_reference
from gutenberg_kg.genres import ALL_GENRES
from gutenberg_kg.ingest import slugify

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = REPO_ROOT / "corpus"
DIARIES_GENRE = "diaries"


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
        if res.ebook_id is None:
            res.warnings.append("no Gutenberg ID in reference.md")

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
