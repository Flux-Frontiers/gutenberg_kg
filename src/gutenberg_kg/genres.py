"""Genre registry — loads from corpus/genres.json; falls back to built-in defaults.

To add a genre without touching code:
    gutenkg genres add <name> --source gutenberg|ia

To seed corpus/genres.json for the first time:
    gutenkg genres init
"""

import json
from pathlib import Path

# corpus/genres.json sits at repo-root/corpus/genres.json
_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "corpus" / "genres.json"

_DEFAULTS: dict[str, list[str]] = {
    "gutenberg": [
        "ancient-classical",
        "shakespeare",
        "english-literature",
        "american-literature",
        "french-literature",
        "russian-literature",
        "philosophy",
        "spanish",
        "science-fiction",
    ],
    "ia": [
        "audel-electric",
    ],
}


def _load() -> dict[str, list[str]]:
    if _REGISTRY_PATH.exists():
        return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return {k: list(v) for k, v in _DEFAULTS.items()}


def _save(data: dict[str, list[str]]) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def seed_registry(force: bool = False) -> bool:
    """Write corpus/genres.json from built-in defaults.

    :param force: Overwrite even if the file already exists.
    :return: True if the file was written, False if it already existed and force=False.
    """
    if _REGISTRY_PATH.exists() and not force:
        return False
    _save(_DEFAULTS)
    return True


def add_genre(name: str, source: str) -> bool:
    """Append *name* to the registry under *source*.

    :param name: Genre slug (e.g. ``"my-genre"``).
    :param source: ``"gutenberg"`` or ``"ia"``.
    :return: True if added, False if already present.
    """
    data = _load()
    lst = data.setdefault(source, [])
    if name in lst:
        return False
    lst.append(name)
    _save(data)
    return True


# ---------------------------------------------------------------------------
# Module-level exports consumed by the rest of the package
# ---------------------------------------------------------------------------

_registry = _load()
GUTENBERG_GENRES: list[str] = _registry.get("gutenberg", list(_DEFAULTS["gutenberg"]))
IA_GENRES: list[str] = _registry.get("ia", list(_DEFAULTS["ia"]))
ALL_GENRES: list[str] = GUTENBERG_GENRES + IA_GENRES
