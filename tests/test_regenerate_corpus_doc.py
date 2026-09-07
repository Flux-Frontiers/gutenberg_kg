"""Regression test for scripts/regenerate_corpus_doc.py.

GENRE_ORDER is a hardcoded list, not derived from the corpus directory, so a
new genre added to corpus/ is silently skipped by _collect_rows() rather than
raising -- it does not appear in docs/CORPUS.md and is not counted in the
totals. This happened for real: "curiosities" shipped in the corpus a full
release before anyone noticed docs/CORPUS.md still said "252 books across 20
genres" instead of 253 across 21.

Loaded via importlib rather than imported as a package: scripts/ is not on
sys.path (pyproject.toml pins pythonpath to ["src"] only), matching the
pattern RUNBOOK.md documents for export_embedder.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "corpus"

# Directories under corpus/ that are not genres.
_NON_GENRE_DIRS = {"authors"}


def _load_module():
    src = REPO_ROOT / "scripts" / "regenerate_corpus_doc.py"
    spec = importlib.util.spec_from_file_location("regenerate_corpus_doc", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_genre_order_covers_every_genre_directory_on_disk() -> None:
    mod = _load_module()
    on_disk = {
        p.name
        for p in CORPUS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in _NON_GENRE_DIRS
    }
    missing = on_disk - set(mod.GENRE_ORDER)
    assert not missing, (
        f"corpus/ has genre directories not in GENRE_ORDER: {sorted(missing)} -- "
        "add them to both GENRE_ORDER and GENRE_LABELS in "
        "scripts/regenerate_corpus_doc.py or they vanish from docs/CORPUS.md"
    )


def test_every_genre_order_entry_has_a_label() -> None:
    mod = _load_module()
    missing = set(mod.GENRE_ORDER) - set(mod.GENRE_LABELS)
    assert not missing, f"GENRE_ORDER entries with no GENRE_LABELS entry: {sorted(missing)}"
