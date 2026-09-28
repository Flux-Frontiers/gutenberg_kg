"""Regression tests for scripts/sync_corpus_docs.py.

At v1.26.0 six files said the corpus had 21 genres after it had 20. The README
intro had been reworded to "**253 texts in 21 genres**", which no pattern in
the script matched, and four other files repeating the count were not synced
at all. The script reported success throughout.

The coverage test reads every surface file as it is on disk and fails on a
genre count that no pattern reaches, so rewording a count without updating
``_PROSE_PATTERNS`` fails here instead of going stale.

Loaded via importlib, like tests/test_regenerate_corpus_doc.py: scripts/ is
not on sys.path.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    src = REPO_ROOT / "scripts" / "sync_corpus_docs.py"
    spec = importlib.util.spec_from_file_location("sync_corpus_docs", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _status(books_by_genre: dict[str, int], nodes: int, edges: int) -> dict:
    return {
        "totals": {"books": sum(books_by_genre.values()), "nodes": nodes, "edges": edges},
        "genres": [{"corpus": f"gutenberg-{g}", "books": n} for g, n in books_by_genre.items()],
    }


def test_patch_prose_updates_every_wording() -> None:
    mod = _load_module()
    # 3 live genres (the empty one is not counted), 2 of them DocKG.
    status = _status({"philosophy": 10, "horror": 5, "diaries": 2, "curiosities": 0}, 1234, 5678)
    text = "\n".join(
        [
            "contains **9 texts in 21 genres**: literature",
            "The UI searches the consolidated **DocKG** (7 books across 20 genres) plus the",
            "indices—**9 books across 21 genres** in all—baked",
            "> **Current corpus:** 9 books across 21 genres. The per-stage",
            "  │   21 genres · 9 books · Markdown + reference.md             │",
            "  9 works across 21 genres — 1 nodes, 2 edges — queryable",
            "The corpus stands at 9 works and over 5 million edges",
            "| `semantic` | 18 genres (230 books) | Sentence-transformer",
            "| `diaries` (4 collections) | Separate",
            "| Prose and technical text | 19 | 242 | DocKG semantic chunking |",
            "| Diaries | 1 | 4 | DiaryKG temporal indexing |",
            "| **Total** | **21** | **253** | |",
        ]
    )
    assert mod._patch_prose(text, status).splitlines() == [
        "contains **17 texts in 3 genres**: literature",
        "The UI searches the consolidated **DocKG** (15 books across 2 genres) plus the",
        "indices—**17 books across 3 genres** in all—baked",
        "> **Current corpus:** 17 books across 3 genres. The per-stage",
        "  │   3 genres · 17 books · Markdown + reference.md             │",
        "  17 works across 3 genres — 1,234 nodes, 5,678 edges — queryable",
        "The corpus stands at 17 works and over 5 million edges",
        "| `semantic` | 2 genres (15 books) | Sentence-transformer",
        "| `diaries` (2 collections) | Separate",
        "| Prose and technical text | 2 | 15 | DocKG semantic chunking |",
        "| Diaries | 1 | 2 | DiaryKG temporal indexing |",
        "| **Total** | **3** | **17** | |",
    ]


def test_patch_prose_leaves_other_numbers_alone() -> None:
    mod = _load_module()
    status = _status({"philosophy": 10}, 1, 2)
    text = "Hamlet is 420 chunks carried on 305 limbs, and 21 genres of trouble."
    assert mod._patch_prose(text, status) == text


def test_every_genre_count_on_disk_is_reached_by_a_pattern() -> None:
    mod = _load_module()
    for path in [mod._README, *mod._PROSE_SURFACES]:
        text = path.read_text(encoding="utf-8")
        covered = [
            m.span() for pattern, _ in mod._PROSE_PATTERNS for m in re.finditer(pattern, text)
        ]
        for m in re.finditer(r"\b\d+ genres\b", text):
            inside = any(a <= m.start() and m.end() <= b for a, b in covered)
            line = text.count("\n", 0, m.start()) + 1
            assert inside, (
                f"{path.relative_to(REPO_ROOT)}:{line} has {m.group()!r}, which no "
                "_PROSE_PATTERNS entry updates"
            )
