#!/usr/bin/env python3
"""
ingest.py — Build per-book DocKGs for every book in gutenberg_kg, register
them in the KGRAG registry, and add them to genre corpora and gutenberg-all.

Usage:
    python scripts/ingest.py [OPTIONS]

Options:
    --genre GENRE        Process only this genre (repeatable; default: all)
    --force-build        Rebuild even if .dockg already exists
    --force-register     Re-register even if KG name already in registry
    --push               git add + commit + push after each genre completes
    --dry-run            Print actions without executing anything
    --registry PATH      Override registry path

Examples:
    python scripts/ingest.py
    python scripts/ingest.py --genre shakespeare --genre ancient-classical
    python scripts/ingest.py --force-build --genre philosophy
    python scripts/ingest.py --push
    python scripts/ingest.py --dry-run
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from kg_rag.corpus_registry import CorpusRegistry
from kg_rag.primitives import CorpusEntry, KGEntry, KGKind
from kg_rag.registry import KGRegistry, default_registry_path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

ALL_GENRES = [
    "ancient-classical",
    "shakespeare",
    "english-literature",
    "american-literature",
    "french-literature",
    "russian-literature",
    "philosophy",
    "spanish",
    "science-fiction",
]

TOP_CORPUS = "gutenberg-all"


# ---------------------------------------------------------------------------
# Options container
# ---------------------------------------------------------------------------


@dataclass
class IngestOptions:
    """Flags controlling ingest behaviour."""

    force_build: bool = False
    force_register: bool = False
    dry_run: bool = False
    push: bool = False


@dataclass
class BookResult:
    """Timing and outcome for one book."""
    name: str
    genre: str
    status: str        # 'built' | 'skipped' | 'failed'
    elapsed: float = 0.0
    nodes: int = 0
    edges: int = 0


@dataclass
class GenreSummary:
    """Aggregated results for one genre."""
    genre: str
    results: list[BookResult] = field(default_factory=list)

    @property
    def built(self) -> int:
        return sum(1 for r in self.results if r.status == "built")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def elapsed(self) -> float:
        return sum(r.elapsed for r in self.results)

    @property
    def nodes(self) -> int:
        return sum(r.nodes for r in self.results)

    @property
    def edges(self) -> int:
        return sum(r.edges for r in self.results)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(s: str) -> str:
    """Lowercase and replace non-alphanumeric runs with hyphens."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]", "-", s.lower())).strip("-")


def fmt_duration(seconds: float) -> str:
    """Human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def ensure_corpus(
    corp_reg: CorpusRegistry,
    name: str,
    description: str = "",
    dry_run: bool = False,
) -> None:
    """Create corpus if it doesn't exist (idempotent)."""
    if corp_reg.get(name) is not None:
        return
    if dry_run:
        print(f"  [dry] corpus create {name!r}")
        return
    corp_reg.create(CorpusEntry(name=name, description=description))
    print(f"  [+] corpus: {name}")


def is_sqlite_valid(path: Path) -> bool:
    """Return True if path is a readable, non-corrupt SQLite database."""
    import sqlite3
    if not path.exists() or path.stat().st_size < 100:
        return False
    try:
        with sqlite3.connect(path) as con:
            con.execute("SELECT COUNT(*) FROM nodes")
        return True
    except Exception:
        return False


def build_dockg(book_dir: Path, dry_run: bool = False) -> bool:
    """Run dockg build on book_dir. Returns True on success."""
    cmd = ["dockg", "build", "--repo", str(book_dir)]
    if dry_run:
        print(f"    [dry] {' '.join(cmd)}")
        return True
    result = subprocess.run(cmd, check=False, text=True)
    if result.returncode != 0:
        print(f"    [x] dockg build failed (exit {result.returncode})")
        return False
    return True


def register_book(
    kg_reg: KGRegistry,
    name: str,
    book_dir: Path,
    dry_run: bool = False,
) -> KGEntry | None:
    """
    Register a book DocKG. Returns the KGEntry (new or existing).
    Returns None on dry-run or failure.
    """
    sqlite = book_dir / ".dockg" / "graph.sqlite"
    lancedb = book_dir / ".dockg" / "lancedb"
    entry = KGEntry(
        name=name,
        kind=KGKind.from_str("doc"),
        repo_path=book_dir,
        venv_path=book_dir / ".venv",
        sqlite_path=sqlite if sqlite.exists() else None,
        lancedb_path=lancedb if lancedb.exists() else None,
        tags=[date.today().isoformat()],
    )
    if dry_run:
        print(f"    [dry] register {name!r} -> {book_dir}")
        return None
    kg_reg.register(entry)
    return entry


def add_to_corpus(
    corp_reg: CorpusRegistry,
    corpus_name: str,
    kg_entry: KGEntry,
    dry_run: bool = False,
) -> bool:
    """Add kg_entry to corpus_name (idempotent via add_kg's dedup)."""
    if dry_run:
        print(f"    [dry] corpus add {corpus_name!r} {kg_entry.name!r}")
        return True
    result = corp_reg.add_kg(corpus_name, kg_entry.id)
    if result is None:
        print(f"    [!] corpus not found: {corpus_name!r}")
        return False
    return True


def git_commit_push_genre(genre_dir: Path, genre: str, dry_run: bool = False) -> None:
    """Stage genre_dir, commit, and push. Skips silently if nothing to commit."""
    if dry_run:
        print(f"  [dry] git add {genre_dir}/ && git commit && git push")
        return

    subprocess.run(["git", "add", str(genre_dir) + "/"], check=True, cwd=REPO_ROOT)

    # Check if there's anything staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        check=False,
        cwd=REPO_ROOT,
    )
    if result.returncode == 0:
        print(f"  [=] {genre}: nothing to commit, skipping push")
        return

    n_files = int(subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"],
        cwd=REPO_ROOT,
        text=True,
    ).strip().count("\n")) + 1

    msg = f"chore(dockg): rebuild {genre} DocKG indices ({n_files} files)"
    subprocess.run(["git", "commit", "-m", msg], check=True, cwd=REPO_ROOT)
    subprocess.run(["git", "push"], check=True, cwd=REPO_ROOT)
    print(f"  [↑] {genre}: pushed {n_files} file(s)")


def _sqlite_counts(book_dir: Path) -> tuple[int, int]:
    """Return (node_count, edge_count) from the book's graph.sqlite, or (0, 0)."""
    import sqlite3
    db = book_dir / ".dockg" / "graph.sqlite"
    if not db.exists():
        return 0, 0
    try:
        with sqlite3.connect(db) as con:
            nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return nodes, edges
    except Exception:
        return 0, 0


# ---------------------------------------------------------------------------
# Core per-book logic
# ---------------------------------------------------------------------------

def process_book(
    book_dir: Path,
    genre: str,
    kg_reg: KGRegistry,
    corp_reg: CorpusRegistry,
    opts: IngestOptions,
) -> BookResult:
    """Process one book directory. Returns a BookResult with timing and graph stats."""
    book_name = book_dir.name
    slug = slugify(book_name)
    kg_name = f"gutenberg-{genre}-{slug}-doc"
    genre_corpus = f"gutenberg-{genre}"
    dockg_sqlite = book_dir / ".dockg" / "graph.sqlite"

    print(f"  [{book_name}]")
    t0 = time.perf_counter()

    # --- Build ---
    dockg_dir = book_dir / ".dockg"
    already_built = dockg_sqlite.exists()

    # Auto-wipe if sqlite exists but is corrupt or empty
    if already_built and not is_sqlite_valid(dockg_sqlite):
        print("    [!] corrupt/empty graph.sqlite — wiping and rebuilding")
        if not opts.dry_run:
            shutil.rmtree(dockg_dir)
        already_built = False

    if already_built and not opts.force_build:
        print("    [=] already built, skipping dockg build")
        status = "skipped"
    else:
        if already_built and opts.force_build:
            if not opts.dry_run:
                shutil.rmtree(dockg_dir)
                print("    [~] wiped .dockg")
            else:
                print("    [dry] rm -rf .dockg")
        label = "rebuilding" if already_built else "building"
        print(f"    [.] {label} DocKG...")
        if not build_dockg(book_dir, dry_run=opts.dry_run):
            elapsed = time.perf_counter() - t0
            return BookResult(name=book_name, genre=genre, status="failed", elapsed=elapsed)
        status = "built"

    # --- Register ---
    existing = kg_reg.get(kg_name)
    if existing is not None and not opts.force_register:
        print(f"    [=] already registered: {kg_name}")
        entry = existing
    else:
        verb = "re-registering" if existing else "registering"
        print(f"    [.] {verb}: {kg_name}")
        entry = register_book(kg_reg, kg_name, book_dir, dry_run=opts.dry_run)
        if entry is None and not opts.dry_run:
            elapsed = time.perf_counter() - t0
            return BookResult(name=book_name, genre=genre, status="failed", elapsed=elapsed)

    if entry is not None:
        add_to_corpus(corp_reg, genre_corpus, entry, dry_run=opts.dry_run)
        add_to_corpus(corp_reg, TOP_CORPUS, entry, dry_run=opts.dry_run)

    elapsed = time.perf_counter() - t0
    nodes, edges = _sqlite_counts(book_dir)
    print(f"    [✓] {fmt_duration(elapsed)}  nodes={nodes:,}  edges={edges:,}")
    return BookResult(name=book_name, genre=genre, status=status, elapsed=elapsed, nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

W = 74  # box width

def _row(label: str, value: str) -> str:
    return f"  {label:<28}  {value}"


def print_summary(
    genre_summaries: list[GenreSummary],
    opts: IngestOptions,
    registry_path: Path,
    wall_start: datetime,
    wall_elapsed: float,
) -> None:
    """Print a rich job summary to stdout."""
    thick = "═" * W
    thin  = "─" * W

    total_built   = sum(g.built   for g in genre_summaries)
    total_skipped = sum(g.skipped for g in genre_summaries)
    total_failed  = sum(g.failed  for g in genre_summaries)
    total_books   = sum(g.total   for g in genre_summaries)
    total_nodes   = sum(g.nodes   for g in genre_summaries)
    total_edges   = sum(g.edges   for g in genre_summaries)

    if opts.dry_run:
        status_icon, status_text = "⚪", "DRY RUN — no changes made"
    elif total_failed == 0:
        status_icon, status_text = "✅", "SUCCESS — all books ingested"
    else:
        status_icon, status_text = "⚠️ ", f"PARTIAL — {total_failed} book(s) failed"

    flags = " ".join(f for f in [
        "--force-build"    if opts.force_build    else "",
        "--force-register" if opts.force_register else "",
        "--push"           if opts.push           else "",
        "--dry-run"        if opts.dry_run         else "",
    ] if f) or "(none)"

    print()
    print("╔" + thick + "╗")
    print(f"║  {'Gutenberg KG Ingest  —  Job Summary':<{W - 2}}║")
    print("╠" + thick + "╣")

    print(f"║{'':{W}}║")
    print(f"║{_row('Started', wall_start.strftime('%Y-%m-%d  %H:%M:%S UTC')):<{W}}║")
    print(f"║{_row('Elapsed', fmt_duration(wall_elapsed)):<{W}}║")
    print(f"║{_row('Host', socket.gethostname()):<{W}}║")
    print(f"║{_row('Platform', f'{platform.system()} {platform.release()}  /  {platform.machine()}'):<{W}}║")
    print(f"║{_row('Python', sys.version.split()[0]):<{W}}║")
    print(f"║{_row('Registry', str(registry_path)):<{W}}║")
    print(f"║{_row('Flags', flags):<{W}}║")
    print(f"║{'':{W}}║")

    print("╠" + thin + "╣")
    print(f"║  {'Totals':<{W - 2}}║")
    print("╠" + thin + "╣")
    print(f"║{'':{W}}║")
    print(f"║{_row('Genres processed', str(len(genre_summaries))):<{W}}║")
    print(f"║{_row('Books total', str(total_books)):<{W}}║")
    print(f"║{_row('Built / rebuilt', str(total_built)):<{W}}║")
    print(f"║{_row('Skipped (up-to-date)', str(total_skipped)):<{W}}║")
    print(f"║{_row('Failed', str(total_failed)):<{W}}║")
    print(f"║{_row('Total nodes', f'{total_nodes:,}'):<{W}}║")
    print(f"║{_row('Total edges', f'{total_edges:,}'):<{W}}║")
    print(f"║{_row('Status', f'{status_icon}  {status_text}'):<{W}}║")
    print(f"║{'':{W}}║")

    print("╠" + thin + "╣")
    print(f"║  {'Per-Genre Breakdown':<{W - 2}}║")
    print("╠" + thin + "╣")
    print(f"║  {'Genre':<22}{'Books':>6}{'Built':>7}{'Skip':>6}{'Fail':>6}{'Nodes':>8}{'Edges':>8}{'Time':>8}  ║")
    print(f"║  {'─' * 68}  ║")
    for g in genre_summaries:
        fail_flag = " !" if g.failed else ""
        print(
            f"║  {g.genre:<22}{g.total:>6}{g.built:>7}{g.skipped:>6}{g.failed:>6}"
            f"{g.nodes:>8,}{g.edges:>8,}{fmt_duration(g.elapsed):>8}{fail_flag:<3}║"
        )
    print(f"║{'':{W}}║")

    all_failed = [r for g in genre_summaries for r in g.results if r.status == "failed"]
    if all_failed:
        print("╠" + thin + "╣")
        print(f"║  {'Failed Books':<{W - 2}}║")
        print("╠" + thin + "╣")
        print(f"║{'':{W}}║")
        for r in all_failed:
            print(f"║  ✗  {r.genre}/{r.name:<{W - 8}}║")
        print(f"║{'':{W}}║")
        print(f"║  {'Tip: re-run with --force-build to retry failed books.':<{W - 2}}║")
        print(f"║{'':{W}}║")

    print("╚" + thick + "╝")
    print()


def save_summary(
    genre_summaries: list[GenreSummary],
    opts: IngestOptions,
    registry_path: Path,
    wall_start: datetime,
    wall_elapsed: float,
) -> Path:
    """Write a Markdown ingest report to reports/ and return its path."""
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)

    ts = wall_start.strftime("%Y-%m-%d_%H%M%S")
    report_path = reports_dir / f"ingest_{ts}.md"

    total_built   = sum(g.built   for g in genre_summaries)
    total_skipped = sum(g.skipped for g in genre_summaries)
    total_failed  = sum(g.failed  for g in genre_summaries)
    total_books   = sum(g.total   for g in genre_summaries)
    total_nodes   = sum(g.nodes   for g in genre_summaries)
    total_edges   = sum(g.edges   for g in genre_summaries)

    if opts.dry_run:
        status = "DRY RUN — no changes made"
    elif total_failed == 0:
        status = "SUCCESS — all books ingested"
    else:
        status = f"PARTIAL — {total_failed} book(s) failed"

    flags = " ".join(f for f in [
        "--force-build"    if opts.force_build    else "",
        "--force-register" if opts.force_register else "",
        "--push"           if opts.push           else "",
        "--dry-run"        if opts.dry_run         else "",
    ] if f) or "(none)"

    lines = [
        "# Gutenberg KG Ingest Report",
        "",
        f"**Date:** {wall_start.strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Elapsed:** {fmt_duration(wall_elapsed)}  ",
        f"**Host:** {socket.gethostname()} / {platform.system()} {platform.release()} / {platform.machine()}  ",
        f"**Python:** {sys.version.split()[0]}  ",
        f"**Registry:** `{registry_path}`  ",
        f"**Flags:** `{flags}`  ",
        f"**Status:** {status}",
        "",
        "## Totals",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Genres processed | {len(genre_summaries)} |",
        f"| Books total | {total_books} |",
        f"| Built / rebuilt | {total_built} |",
        f"| Skipped (up-to-date) | {total_skipped} |",
        f"| Failed | {total_failed} |",
        f"| Total nodes | {total_nodes:,} |",
        f"| Total edges | {total_edges:,} |",
        "",
        "## Per-Genre Breakdown",
        "",
        "| Genre | Books | Built | Skipped | Failed | Nodes | Edges | Time |",
        "|-------|------:|------:|--------:|-------:|------:|------:|------|",
    ]

    for g in genre_summaries:
        lines.append(
            f"| {g.genre} | {g.total} | {g.built} | {g.skipped} | {g.failed} "
            f"| {g.nodes:,} | {g.edges:,} | {fmt_duration(g.elapsed)} |"
        )

    # Per-genre book detail
    lines += ["", "## Book Detail", ""]
    for g in genre_summaries:
        lines += [f"### {g.genre}", "", "| Book | Status | Nodes | Edges | Time |",
                  "|------|--------|------:|------:|------|"]
        for r in g.results:
            icon = "✓" if r.status == "built" else ("=" if r.status == "skipped" else "✗")
            lines.append(
                f"| {r.name} | {icon} {r.status} | {r.nodes:,} | {r.edges:,} | {fmt_duration(r.elapsed)} |"
            )
        lines.append("")

    all_failed = [r for g in genre_summaries for r in g.results if r.status == "failed"]
    if all_failed:
        lines += ["## Failed Books", ""]
        for r in all_failed:
            lines.append(f"- `{r.genre}/{r.name}`")
        lines += ["", "_Re-run with `--force-build` to retry._", ""]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(
        description="Build, register, and corpus-add per-book DocKGs for gutenberg_kg.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--list-genres",
        action="store_true",
        help="Print all known genres and exit",
    )
    p.add_argument(
        "--genre",
        dest="genres",
        action="append",
        metavar="GENRE",
        help="Process only this genre (repeatable; default: all)",
    )
    p.add_argument(
        "--force-build",
        action="store_true",
        help="Rebuild even if .dockg already exists",
    )
    p.add_argument(
        "--force-register",
        action="store_true",
        help="Re-register even if already in registry",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without executing",
    )
    p.add_argument(
        "--push",
        action="store_true",
        help="git add + commit + push after each genre completes",
    )
    p.add_argument(
        "--registry",
        metavar="PATH",
        default=None,
        help="Override registry path",
    )
    return p.parse_args()


def main() -> int:
    """Entry point."""
    args = parse_args()

    if args.list_genres:
        print("Known genres:")
        for g in ALL_GENRES:
            print(f"  {g}")
        return 0

    genres = args.genres or ALL_GENRES
    registry_path = Path(args.registry).resolve() if args.registry else default_registry_path()

    unknown = [g for g in genres if g not in ALL_GENRES]
    if unknown:
        print(f"ERROR: unknown genre(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Valid genres: {', '.join(ALL_GENRES)}", file=sys.stderr)
        return 1

    opts = IngestOptions(
        force_build=args.force_build,
        force_register=args.force_register,
        dry_run=args.dry_run,
        push=args.push,
    )

    if opts.dry_run:
        print("[DRY RUN — no changes will be made]\n")

    genre_summaries: list[GenreSummary] = []
    wall_start = datetime.now(timezone.utc)
    wall_t0 = time.perf_counter()

    with KGRegistry(db_path=registry_path) as kg_reg, \
         CorpusRegistry(db_path=registry_path) as corp_reg:

        # Ensure all needed corpora exist up front
        print("--- Ensuring corpora ---")
        for genre in genres:
            ensure_corpus(
                corp_reg,
                f"gutenberg-{genre}",
                description=f"Project Gutenberg — {genre}",
                dry_run=opts.dry_run,
            )
        ensure_corpus(
            corp_reg,
            TOP_CORPUS,
            description="Project Gutenberg — complete library",
            dry_run=opts.dry_run,
        )
        print()

        # Process books
        for genre in genres:
            genre_dir = REPO_ROOT / genre
            if not genre_dir.is_dir():
                print(f"[!] Genre directory not found: {genre_dir} — skipping\n")
                continue

            book_dirs = sorted(
                p for p in genre_dir.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            )
            if not book_dirs:
                print(f"[!] No book directories in {genre_dir} — skipping\n")
                continue

            print(f"=== {genre} ({len(book_dirs)} books) ===")
            genre_summary = GenreSummary(genre=genre)
            for book_dir in book_dirs:
                result = process_book(
                    book_dir=book_dir,
                    genre=genre,
                    kg_reg=kg_reg,
                    corp_reg=corp_reg,
                    opts=opts,
                )
                genre_summary.results.append(result)

            genre_summaries.append(genre_summary)

            if opts.push:
                git_commit_push_genre(genre_dir, genre, dry_run=opts.dry_run)
            print()

    wall_elapsed = time.perf_counter() - wall_t0
    print_summary(genre_summaries, opts, registry_path, wall_start, wall_elapsed)

    report_path = save_summary(genre_summaries, opts, registry_path, wall_start, wall_elapsed)
    print(f"  Report saved: {report_path}\n")

    return 1 if any(g.failed for g in genre_summaries) else 0


if __name__ == "__main__":
    sys.exit(main())
