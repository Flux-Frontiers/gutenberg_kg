"""Shared diary metadata and slug derivation for handler workers."""

from __future__ import annotations

# Static author/title/genre for each DiaryKG — keyed by slug.
# Add a new entry here whenever a new diary is ingested.
DIARY_META: dict[str, dict] = {
    "pepys-complete": {
        "author": "Samuel Pepys",
        "title": "The Diary of Samuel Pepys — Complete",
        "genre": "diaries",
    },
    "evelyn-volume-1": {
        "author": "John Evelyn",
        "title": "The Diary of John Evelyn — Volume 1",
        "genre": "diaries",
    },
    "evelyn-volume-2": {
        "author": "John Evelyn",
        "title": "The Diary of John Evelyn — Volume 2",
        "genre": "diaries",
    },
    "johnson": {
        "author": "James Boswell",
        "title": "The Journal of a Tour to the Hebrides with Samuel Johnson",
        "genre": "diaries",
    },
}


def diary_slug(directory_name: str) -> str:
    """Derive a stable slug from a diary directory name.

    :param directory_name: Directory name, e.g. ``"The Diary of Samuel Pepys — Complete"``.
    :returns: Kebab-case slug, e.g. ``"pepys-complete"``.
    """
    return (
        directory_name.lower()
        .replace("the diary of ", "")
        .replace("the journal of a tour to the hebrides with ", "")
        .replace("samuel pepys", "pepys")
        .replace("john evelyn", "evelyn")
        .replace("samuel johnson", "johnson")
        .replace("—", "")
        .replace("  ", " ")
        .strip()
        .replace(" ", "-")
    )
