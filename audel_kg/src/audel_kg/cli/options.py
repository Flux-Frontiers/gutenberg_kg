"""Shared constants for the audelkg CLI."""

from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent.parent.parent  # audel_kg/
CORPUS_ROOT = REPO_ROOT / "corpus"

ALL_GENRES = [
    "audel-electric",
]
