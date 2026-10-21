# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Each author's voice for a moot: gender and a coarse accent, from Wikidata.

A moot's tree speaks as its book's author, so the forest picks a voice of
the author's gender and, where the browser has one, the author's accent.
Neither is in the corpus, so this module looks them up on Wikidata and keeps
them in ``corpus/authors/voices.json``, beside the author pages and apart
from ingestion:

- ``gender``: ``"male"``, ``"female"`` or ``None``, from sex or gender (P21).
- ``accent``: ``"en-US"``, ``"en-GB"`` or ``None``, from country of
  citizenship (P27). An American citizenship gives ``en-US``; a British,
  Irish or Commonwealth one ``en-GB``; anything else, including every
  translated author, ``None``, which leaves the accent to the system.

Each entry also records the Wikidata item and the citizenship labels, so
the table can be reviewed, and its ``source``. An entry whose source is
``"manual"`` is never overwritten; the others are filled in once and kept
unless refreshed.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from gutenberg_kg.authors import AUTHORS_DIR, _slugify

VOICES_PATH = AUTHORS_DIR / "voices.json"
_USER_AGENT = "gutenberg-kg author-voices (https://github.com/Flux-Frontiers/gutenberg_kg)"
_BATCH = 50

# Wikidata items for sex or gender (P21).
_GENDER = {
    "Q6581097": "male",
    "Q2449503": "male",  # trans man
    "Q6581072": "female",
    "Q1052281": "female",  # trans woman
}
_US = {"Q30"}
# The United Kingdom and its predecessors, Ireland, and English-speaking Commonwealth countries.
_GB = {
    "Q145", "Q174193", "Q161885", "Q179876", "Q230791", "Q21", "Q22", "Q25", "Q27",
    "Q215530", "Q8680", "Q408", "Q664", "Q258",
}  # fmt: skip

# Author names that name no one; they are never looked up and get no voice.
PLACEHOLDERS = frozenset({"various", "anonymous", "unknown"})

# A fetcher takes a URL and returns the decoded JSON; tests pass a fake.
Fetch = Callable[[str], dict]


def fetch_json(url: str) -> dict:
    """GET ``url`` from a Wikimedia API with a descriptive User-Agent.

    :param url: The API URL.
    :returns: The decoded JSON.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 -- fixed https hosts
        return json.load(resp)


def gender_of(ids: list[str]) -> str | None:
    """``"male"``, ``"female"`` or ``None`` for an author's P21 values."""
    return next((_GENDER[i] for i in ids if i in _GENDER), None)


def accent_of(ids: list[str]) -> str | None:
    """``"en-US"``, ``"en-GB"`` or ``None`` for an author's P27 values; American wins."""
    if _US & set(ids):
        return "en-US"
    if _GB & set(ids):
        return "en-GB"
    return None


def author_pages(authors_dir: Path = AUTHORS_DIR) -> dict[str, dict]:
    """Every author page: slug -> ``{"name", "title"}``.

    ``title`` is the Wikipedia article title from the page's Wikipedia link,
    or ``None`` when the page has none.

    :param authors_dir: ``corpus/authors``.
    """
    pages = {}
    for page in sorted(authors_dir.glob("*/author.md")):
        text = page.read_text(encoding="utf-8")
        heading = re.search(r"^# (.+)$", text, re.MULTILINE)
        link = re.search(r"\*\*Wikipedia\*\*: https?://en\.wikipedia\.org/wiki/(\S+)", text)
        pages[page.parent.name] = {
            "name": heading.group(1).strip() if heading else page.parent.name,
            "title": urllib.parse.unquote(link.group(1)).replace("_", " ") if link else None,
        }
    return pages


def _claim_ids(entity: dict, prop: str) -> list[str]:
    ids = []
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and "id" in value:
            ids.append(value["id"])
    return ids


def _items_for_titles(titles: list[str], fetch: Fetch) -> dict[str, str]:
    """Wikipedia title -> Wikidata item, following redirects."""
    items: dict[str, str] = {}
    for i in range(0, len(titles), _BATCH):
        batch = titles[i : i + _BATCH]
        q = urllib.parse.urlencode(
            {
                "action": "query",
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "redirects": 1,
                "format": "json",
                "titles": "|".join(batch),
            }
        )
        data = fetch(f"https://en.wikipedia.org/w/api.php?{q}").get("query", {})
        renamed = {
            n["from"]: n["to"] for n in data.get("normalized", []) + data.get("redirects", [])
        }
        found = {
            p["title"]: p.get("pageprops", {}).get("wikibase_item")
            for p in data.get("pages", {}).values()
        }
        for title in batch:
            target = title
            while target in renamed:
                target = renamed[target]
            if found.get(target):
                items[title] = found[target]
    return items


def _search_item(name: str, fetch: Fetch) -> str | None:
    """The first Wikidata search hit for an author's name, for pages with no link."""
    q = urllib.parse.urlencode(
        {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "type": "item",
            "format": "json",
        }
    )
    hits = fetch(f"https://www.wikidata.org/w/api.php?{q}").get("search", [])
    return hits[0]["id"] if hits else None


def _entities(ids: list[str], props: str, fetch: Fetch) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(ids), _BATCH):
        q = urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": "|".join(ids[i : i + _BATCH]),
                "props": props,
                "languages": "en",
                "format": "json",
            }
        )
        out.update(fetch(f"https://www.wikidata.org/w/api.php?{q}").get("entities", {}))
    return out


def look_up(pages: dict[str, dict], fetch: Fetch = fetch_json) -> dict[str, dict]:
    """Look each author up on Wikidata.

    :param pages: slug -> ``{"name", "title"}``, as :func:`author_pages` gives.
    :param fetch: The JSON fetcher.
    :returns: slug -> voice entry. An author with no Wikipedia link is found by
        name and marked ``"wikidata-search"`` for review; one not found at all
        gets no gender or accent, and a placeholder such as ``Various`` is
        not looked up.
    """
    placeholder = {s for s, p in pages.items() if p["name"].casefold() in PLACEHOLDERS}
    titled = {s: p["title"] for s, p in pages.items() if p["title"]}
    by_title = _items_for_titles(sorted(set(titled.values())), fetch)
    items: dict[str, tuple[str, str]] = {}
    for slug, page in pages.items():
        if page["title"] and page["title"] in by_title:
            items[slug] = (by_title[page["title"]], "wikidata")
        elif not page["title"] and slug not in placeholder:
            found = _search_item(page["name"], fetch)
            if found:
                items[slug] = (found, "wikidata-search")
    entities = _entities(sorted({q for q, _ in items.values()}), "claims", fetch)
    countries = sorted(
        {c for q, _ in items.values() for c in _claim_ids(entities.get(q, {}), "P27")}
    )
    labels = {
        q: e.get("labels", {}).get("en", {}).get("value", q)
        for q, e in _entities(countries, "labels", fetch).items()
    }
    voices = {}
    for slug, page in pages.items():
        qid, source = items.get(slug, (None, "placeholder" if slug in placeholder else "not found"))
        entity = entities.get(qid, {}) if qid else {}
        citizenship = _claim_ids(entity, "P27")
        voices[slug] = {
            "name": page["name"],
            "gender": gender_of(_claim_ids(entity, "P21")),
            "accent": accent_of(citizenship),
            "citizenship": [labels.get(c, c) for c in citizenship],
            "wikidata": qid,
            "source": source,
        }
    return voices


def merge_voices(
    old: dict[str, dict], new: dict[str, dict], refresh: bool = False
) -> dict[str, dict]:
    """Combine a fresh lookup with the existing table.

    A ``"manual"`` entry always stays. Other existing entries stay unless
    ``refresh``; authors new to the corpus are added.

    :returns: The merged table, sorted by slug.
    """
    merged = dict(new)
    for slug, entry in old.items():
        if entry.get("source") == "manual" or not refresh:
            merged[slug] = entry
    return dict(sorted(merged.items()))


def read_voices(path: Path = VOICES_PATH) -> dict[str, dict]:
    """The voice table, or ``{}`` when it has not been written."""
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def voice_for(author: str, voices: dict[str, dict]) -> dict:
    """``{"gender", "accent"}`` for a catalog author name, both ``None`` when unknown.

    :param author: The author as the catalog names it.
    :param voices: The voice table.
    """
    entry = voices.get(_slugify(author), {})
    return {"gender": entry.get("gender"), "accent": entry.get("accent")}
