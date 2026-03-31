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
    --dry-run            Print actions without executing anything
    --registry PATH      Override registry path

Examples:
    python scripts/ingest.py
    python scripts/ingest.py --genre shakespeare --genre ancient-classical
    python scripts/ingest.py --force-build --genre philosophy
    python scripts/ingest.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(s: str) -> str:
    """Lowercase and replace non-alphanumeric runs with hyphens."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]", "-", s.lower())).strip("-")


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


# ---------------------------------------------------------------------------
# Core per-book logic
# ---------------------------------------------------------------------------

def process_book(
    book_dir: Path,
    genre: str,
    kg_reg: KGRegistry,
    corp_reg: CorpusRegistry,
    opts: IngestOptions,
) -> str:
    """Process one book directory. Returns one of: 'built', 'skipped', 'failed'."""
    book_name = book_dir.name
    slug = slugify(book_name)
    kg_name = f"gutenberg-{genre}-{slug}-doc"
    genre_corpus = f"gutenberg-{genre}"
    dockg_sqlite = book_dir / ".dockg" / "graph.sqlite"

    print(f"  [{book_name}]")

    # --- Build ---
    already_built = dockg_sqlite.exists()
    if already_built and not opts.force_build:
        print("    [=] already built, skipping dockg build")
    else:
        label = "rebuilding" if already_built else "building"
        print(f"    [.] {label} DocKG...")
        if not build_dockg(book_dir, dry_run=opts.dry_run):
            return "failed"

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
            return "failed"

    if entry is None:
        # dry-run path
        return "built"

    # --- Add to corpora ---
    add_to_corpus(corp_reg, genre_corpus, entry, dry_run=opts.dry_run)
    add_to_corpus(corp_reg, TOP_CORPUS, entry, dry_run=opts.dry_run)

    return "built"


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
        "--registry",
        metavar="PATH",
        default=None,
        help="Override registry path",
    )
    return p.parse_args()


def main() -> int:
    """Entry point."""
    args = parse_args()
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
    )

    if opts.dry_run:
        print("[DRY RUN — no changes will be made]\n")

    counts: dict[str, int] = {"built": 0, "skipped": 0, "failed": 0}

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
            for book_dir in book_dirs:
                status = process_book(
                    book_dir=book_dir,
                    genre=genre,
                    kg_reg=kg_reg,
                    corp_reg=corp_reg,
                    opts=opts,
                )
                counts[status] = counts.get(status, 0) + 1
            print()

    # Summary
    total = sum(counts.values())
    print("=== Summary ===")
    print(f"  Total  : {total}")
    print(f"  Built  : {counts.get('built', 0)}")
    print(f"  Skipped: {counts.get('skipped', 0)}")
    print(f"  Failed : {counts.get('failed', 0)}")
    if counts.get("failed", 0) > 0:
        print("\n[!] Some books failed — re-run with --force-build to retry.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
