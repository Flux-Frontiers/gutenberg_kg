"""Propose a literary year for every corpus work (read-only).

Writes a review TSV; nothing in ``corpus/`` is modified. A work's literary
year is when it was first published, performed or (for ancient and sacred
texts) composed. Each work is resolved in this order:

1. ``corpus/pub_dates_overrides.tsv`` -- hand-dated, always wins.
2. A local ``## Publication`` date in ``reference.md`` (Internet Archive works).
3. Two lookups, cross-checked:

   - the year the ``## Summary`` states ("published in 1884");
   - Wikidata (entity API), keyed by the Project Gutenberg ebook ID (P2034),
     following an edition to its work (P629); the earliest of publication
     (P577) and first performance (P1191), else inception (P571). Accepted only
     when the Wikidata label matches the entry's title.

   With neither, Wikidata is searched by title among the author's works
   (author found by Project Gutenberg author ID, P1938).

   Agreement within two years is ``high`` confidence; one source alone is
   ``medium``; disagreement is flagged ``conflict`` for review and takes
   the earlier year that falls within the author's life.
4. With no lookup, an estimate: birth + 40, or death - 10, flagged ``low``.

Then two rules apply: a year after the author's death becomes the death year
(``clamped``), and every volume of a multi-volume set takes its first
volume's year.

Usage::

    python3 -I scripts/lookup_pub_dates.py OUT.tsv CACHE.json [ENTRY ...]

``ENTRY`` is ``genre/Book Folder``; with none, every work in the corpus.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
OVERRIDES = CORPUS / "pub_dates_overrides.tsv"
UA = "gutenberg-kg-pubdate-lookup/0.2 (research script)"
WDAPI = "https://www.wikidata.org/w/api.php"
DATE_PROPS = ("P577", "P571", "P1191")  # publication, inception, first performance
SUMMARY_YEAR = re.compile(
    r"\b(?:published|written|composed|first appeared|first performed|released|appeared)\b"
    r"[^.]{0,40}?\b(\d{3,4}|\d{2}(?=\s*B\.?\s?C))\b(?:\s*[-\u2013]\s*\d{2,4})?(\s*B\.?\s?C\.?(?:E\.?)?)?",
    re.IGNORECASE,
)
VOLUME = re.compile(
    r"(\s*[—-]\s*|,\s*|\.\s*|\s+)(Vol\.?|Volume)\s*(\d+)\b.*$|\s*\(of \d+\)", re.IGNORECASE
)


def _get(url: str) -> dict:
    """Fetch JSON politely: 3 s between requests, honoring Retry-After on 429.

    :param url: The full request URL.
    :return: The decoded JSON body.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(6):
        time.sleep(3)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(int(e.headers.get("Retry-After", "30")) + 1)
    raise RuntimeError("unreachable")


def _field(pattern: str, text: str) -> str | None:
    """Return the first capture group of a multiline match, stripped.

    :param pattern: Regex with one group.
    :param text: Text to search.
    :return: The match or None.
    """
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _int(s: str | None) -> int | None:
    """Parse a signed integer year, or None.

    :param s: Text such as ``1835`` or ``-750``.
    :return: The year or None.
    """
    try:
        return int(s) if s else None
    except ValueError:
        return None


def _words(s: str) -> set[str]:
    """Lowercase content words of a title, for matching.

    :param s: A title.
    :return: Words of three or more letters, minus a few fillers.
    """
    return {
        w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in {"the", "and", "volume", "vol"}
    }


def title_matches(title: str, label: str) -> bool:
    """Whether a Wikidata label names the same work as a corpus title.

    :param title: The entry's title.
    :param label: The Wikidata work label.
    :return: True when most of the shorter title's words are in the longer.
    """
    a, b = _words(title), _words(label)
    if not a or not b:
        return False
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return len(small & big) >= max(1, round(0.6 * len(small)))


def _entity(qid: str, cache: dict) -> dict:
    """One Wikidata entity's English label and claims, cached.

    :param qid: Item id such as ``Q215410``.
    :param cache: Response cache, keyed by request.
    :return: The entity JSON.
    """
    key = f"entity:{qid}"
    if key not in cache:
        q = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "labels|claims",
            "languages": "en",
            "format": "json",
        }
        cache[key] = _get(WDAPI + "?" + urllib.parse.urlencode(q))["entities"][qid]
    return cache[key]


def _work_date(work: dict) -> dict | None:
    """A work entity's literary year, or None when it has no date.

    Publication (P577) or first performance (P1191) beats inception (P571),
    which often marks when writing began (War and Peace: 1863 begun, 1869
    published).

    :param work: Entity JSON.
    :return: Dict with wd_work, wd_year, wd_prec, or None.
    """
    dated = []
    for prop in DATE_PROPS:
        for c in work.get("claims", {}).get(prop, []):
            v = c["mainsnak"].get("datavalue", {}).get("value")
            if v:
                dated.append(
                    (int(re.match(r"([+-]?\d+)-", v["time"]).group(1)), v["precision"], prop)
                )
    if not dated:
        return None
    published = [d for d in dated if d[2] != "P571"]
    year, prec, _ = min(published or dated)
    label = work.get("labels", {}).get("en", {}).get("value", "")
    return {"wd_work": f"{work['id']} {label}", "wd_year": year, "wd_prec": prec}


def _search(query: str, cache: dict) -> list[str]:
    """Item ids from a Wikidata CirrusSearch query, cached.

    :param query: Search text, may include ``haswbstatement:`` filters.
    :param cache: Response cache, keyed by request.
    :return: Matching item ids, best first.
    """
    key = f"search:{query}"
    if key not in cache:
        q = {"action": "query", "list": "search", "srsearch": query, "format": "json"}
        cache[key] = [
            h["title"] for h in _get(WDAPI + "?" + urllib.parse.urlencode(q))["query"]["search"]
        ]
    return cache[key]


def short_title(title: str) -> str:
    """A title cut down for searching: no volume, parenthetical, author or subtitle.

    :param title: The entry's title.
    :return: The searchable core of the title.
    """
    t = VOLUME.sub("", title)
    t = re.split(r"\s+\u2014\s+|;|:|\(", t)[0]
    return t.strip(" ,.")


def wikidata_by_author(
    title: str, agent_id: str, born: int | None, died: int | None, cache: dict
) -> dict | None:
    """Find a work on Wikidata by title among its author's works.

    The author is found exactly by Project Gutenberg author ID (P1938); the
    work by title search restricted to that author (P50). A candidate dated
    outside the author's adult life is a later edition or translation, so it
    is skipped and the next one tried.

    :param title: The entry's title.
    :param agent_id: Project Gutenberg agent (author) number.
    :param born: Author's birth year, or None.
    :param died: Author's death year, or None.
    :param cache: Response cache, keyed by request.
    :return: Dict with wd_work, wd_year, wd_prec, or None.
    """
    authors = _search(f"haswbstatement:P1938={agent_id}", cache)
    if not authors:
        return None
    core = short_title(title)
    for qid in _search(f"{core} haswbstatement:P50={authors[0]}", cache)[:5]:
        work = _entity(qid, cache)
        label = work.get("labels", {}).get("en", {}).get("value", "")
        hit = _work_date(work) if title_matches(core, label) else None
        if (
            hit
            and (born is None or hit["wd_year"] >= born + 10)
            and (died is None or hit["wd_year"] <= died)
        ):
            return hit
    return None


def wikidata(pg_id: str, cache: dict) -> dict:
    """Earliest literary date on the Wikidata work for a Gutenberg ebook ID.

    :param pg_id: Project Gutenberg ebook number.
    :param cache: Response cache, keyed by request.
    :return: Dict with wd_work, wd_year, wd_prec (9 year, 8 decade, 7 century).
    """
    key = f"pg:{pg_id}"
    if key not in cache:
        q = {
            "action": "query",
            "list": "search",
            "srsearch": f"haswbstatement:P2034={pg_id}",
            "format": "json",
        }
        cache[key] = [
            h["title"] for h in _get(WDAPI + "?" + urllib.parse.urlencode(q))["query"]["search"]
        ]
    out = {"wd_work": "", "wd_year": None, "wd_prec": None}
    for qid in cache[key]:
        item = _entity(qid, cache)
        works = [
            c["mainsnak"]["datavalue"]["value"]["id"]
            for c in item.get("claims", {}).get("P629", [])
            if "datavalue" in c["mainsnak"]
        ]
        work = _entity(works[0], cache) if works else item
        hit = _work_date(work)
        if hit:
            return hit
    return out


def read_overrides() -> dict[str, dict]:
    """Hand-dated works from the overrides file.

    :return: Rows keyed by entry.
    """
    lines = [
        ln
        for ln in OVERRIDES.read_text(encoding="utf-8").splitlines()
        if ln and not ln.startswith("#")
    ]
    return {r["entry"]: r for r in csv.DictReader(lines, delimiter="\t")}


def gather(entry: str, overrides: dict, cache: dict) -> dict:
    """Collect every candidate year for one entry.

    :param entry: ``genre/Book Folder`` relative to the corpus root.
    :param overrides: Hand-dated rows keyed by entry.
    :param cache: Wikidata response cache.
    :return: One row of raw evidence.
    """
    text = (CORPUS / entry / "reference.md").read_text(encoding="utf-8")
    summary = _field(r"^## Summary\s*\n+(.+)$", text) or ""
    m = SUMMARY_YEAR.search(summary)
    row = {
        "entry": entry,
        "title": _field(r"^# Reference:\s*(.+)$", text) or entry.split("/")[-1],
        "born": _int(_field(r"^- \*\*Born\*\*:\s*(\S+)", text)),
        "died": _int(_field(r"^- \*\*Died\*\*:\s*(\S+)", text)),
        "override": _int(overrides[entry]["year"]) if entry in overrides else None,
        "local_year": _int(_field(r"^## Publication[\s\S]*?^- \*\*Date\*\*:\s*(\d{3,4})", text)),
        "summary_year": (-int(m.group(1)) if m.group(2) else int(m.group(1))) if m else None,
        "wd_work": "",
        "wd_year": None,
        "wd_prec": None,
    }
    pg_id = _field(r"^- \*\*Project Gutenberg ID\*\*:\s*(\d+)", text)
    if pg_id and row["override"] is None and row["local_year"] is None:
        row.update(wikidata(pg_id, cache))
        if row["wd_year"] is not None and not title_matches(
            row["title"], row["wd_work"].split(" ", 1)[-1]
        ):
            row["wd_rejected"] = row.pop("wd_work")
            row["wd_work"], row["wd_year"] = "", None
    agent_id = _field(r"^- \*\*Gutenberg Agent ID\*\*:\s*(\d+)", text)
    if (
        agent_id
        and row["override"] is None
        and row["local_year"] is None
        and row["wd_year"] is None
        and row["summary_year"] is None
    ):
        hit = wikidata_by_author(row["title"], agent_id, row["born"], row["died"], cache)
        if hit:
            row.update(hit)
            row["wd_route"] = "author+title"
    return row


def resolve(row: dict) -> dict:
    """Pick one year from a row's evidence and say how sure it is.

    :param row: Output of ``gather``.
    :return: The row with year, source, confidence and flags added.
    """
    flags = []
    if row["override"] is not None:
        year, source, conf = row["override"], "override", "hand"
    elif row["local_year"] is not None:
        year, source, conf = row["local_year"], "local", "high"
    else:
        s, w = row["summary_year"], row["wd_year"]
        if s is not None and w is not None:
            if abs(s - w) <= 2:
                year, source, conf = w, "summary+wikidata", "high"
            else:
                # Prefer the earlier year inside the author's life: composition
                # before posthumous publication, and never a modern edition.
                b = row["born"] + 10 if row["born"] is not None else -(10**6)
                d = row["died"] if row["died"] is not None else 10**6
                alive = [y for y in (s, w) if b <= y <= d]
                year = min(alive or (s, w))
                source, conf = ("summary" if year == s else "wikidata"), "conflict"
        elif w is not None:
            year, source, conf = w, "wikidata", "medium"
        elif s is not None:
            year, source, conf = s, "summary", "medium"
        elif row["born"] is not None:
            year, source, conf = row["born"] + 40, "estimate", "low"
        elif row["died"] is not None:
            year, source, conf = row["died"] - 10, "estimate", "low"
        else:
            year, source, conf = None, "none", "needs-override"
        if (
            row["wd_prec"] is not None
            and row["wd_prec"] < 9
            and source.startswith(("wikidata", "summary+"))
        ):
            flags.append("approx")
        if year is not None and row["died"] is not None and year > row["died"]:
            flags.append(f"clamped-from-{year}")
            year = row["died"]
        if year is not None and row["born"] is not None and year < row["born"] + 10:
            flags.append("before-age-10")
    return {**row, "year": year, "source": source, "confidence": conf, "flags": " ".join(flags)}


def first_volume(rows: list[dict]) -> None:
    """Give every volume of a multi-volume set its lowest volume's year, in place.

    :param rows: Resolved rows.
    """
    sets: dict[str, list[tuple[int, dict]]] = {}
    for r in rows:
        name = r["entry"]
        m = re.search(r"(?:Vol\.?|Volume)\s*(\d+)", name, re.IGNORECASE)
        if m:
            sets.setdefault(VOLUME.sub("", name), []).append((int(m.group(1)), r))
    for members in sets.values():
        if len(members) < 2:
            continue
        lead = min(members, key=lambda t: t[0])[1]
        for _, r in members:
            if r is not lead and r["source"] != "override" and r["year"] != lead["year"]:
                r["flags"] = (r["flags"] + f" first-volume-from-{r['year']}").strip()
                r["year"] = lead["year"]


def main() -> None:
    """Resolve the named entries (or the whole corpus) and write the review TSV."""
    out, cache_path, entries = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    if not entries:
        entries = sorted(str(p.parent.relative_to(CORPUS)) for p in CORPUS.glob("*/*/reference.md"))
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    overrides = read_overrides()
    rows = []
    for i, e in enumerate(entries):
        try:
            rows.append(resolve(gather(e, overrides, cache)))
        except (
            OSError,
            KeyError,
            ValueError,
        ) as exc:  # network, missing field or bad JSON: report, go on
            rows.append({"entry": e, "source": "error", "flags": repr(exc)})
        cache_path.write_text(json.dumps(cache))
        print(
            f"{i + 1}/{len(entries)} {rows[-1].get('year')} {rows[-1].get('source')} {e}",
            file=sys.stderr,
        )
    first_volume([r for r in rows if r.get("source") != "error"])
    cols = [
        "entry",
        "year",
        "source",
        "confidence",
        "flags",
        "summary_year",
        "wd_year",
        "wd_prec",
        "wd_work",
        "wd_route",
        "wd_rejected",
        "born",
        "died",
        "title",
    ]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
