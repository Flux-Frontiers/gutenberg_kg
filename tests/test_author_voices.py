"""Author voices for moots: Wikidata lookup, the table's rules, and moot packs."""

from __future__ import annotations

import json
import urllib.parse

from gutenberg_kg.author_voices import (
    accent_of,
    author_pages,
    gender_of,
    look_up,
    merge_voices,
    voice_for,
)
from gutenberg_kg.export_web_moots import moot_pack


def _page(root, slug, name, wiki=None):
    d = root / slug
    d.mkdir(parents=True)
    link = f"- **Wikipedia**: https://en.wikipedia.org/wiki/{wiki}\n" if wiki else ""
    (d / "author.md").write_text(f"# {name}\n\n*1835 - 1910*\n\n{link}")


def test_gender_and_accent_rules():
    assert gender_of(["Q6581097"]) == "male"
    assert gender_of(["Q6581072"]) == "female"
    assert gender_of(["Q48270"]) is None  # non-binary: no voice gender
    assert accent_of(["Q30"]) == "en-US"
    assert accent_of(["Q174193"]) == "en-GB"  # United Kingdom of Great Britain and Ireland
    assert accent_of(["Q27"]) == "en-GB"  # Ireland
    assert accent_of(["Q30", "Q145"]) == "en-US"  # American wins, as for Henry James
    assert accent_of(["Q183"]) is None  # Germany: a translated author
    assert accent_of([]) is None


def test_author_pages_reads_name_and_wikipedia_title(tmp_path):
    _page(tmp_path, "mark_twain", "Mark Twain", "Mark_Twain")
    _page(tmp_path, "alexandre_dumas", "Alexandre Dumas", "Alexandre_Dumas,_p%C3%A8re")
    _page(tmp_path, "john_jay", "John Jay")
    pages = author_pages(tmp_path)
    assert pages["mark_twain"] == {"name": "Mark Twain", "title": "Mark Twain"}
    assert pages["alexandre_dumas"]["title"] == "Alexandre Dumas, père"
    assert pages["john_jay"] == {"name": "John Jay", "title": None}


class FakeWikimedia:
    """Answers the four API calls look_up makes, from small tables."""

    def __init__(self):
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        if q.get("prop") == "pageprops":
            pages = {"Mark Twain": "Q7245", "Jane Austen": "Q36322"}
            titles = q["titles"].split("|")
            return {
                "query": {
                    "redirects": [{"from": "Twain", "to": "Mark Twain"}]
                    if "Twain" in titles
                    else [],
                    "pages": {
                        str(i): {"title": t, "pageprops": {"wikibase_item": pages[t]}}
                        for i, t in enumerate(pages)
                    },
                }
            }
        if q.get("action") == "wbsearchentities":
            return {"search": [{"id": "Q310847"}] if q["search"] == "John Jay" else []}
        if q.get("props") == "claims":
            claims = {
                "Q7245": (["Q6581097"], ["Q30"]),
                "Q36322": (["Q6581072"], ["Q174193"]),
                "Q310847": (["Q6581097"], ["Q30"]),
            }
            return {
                "entities": {
                    qid: {"claims": {p: [{"mainsnak": {"datavalue": {"value": {"id": v}}}} for v in vals]
                                     for p, vals in (("P21", sex), ("P27", cit))}}
                    for qid, (sex, cit) in claims.items() if qid in q["ids"].split("|")
                }
            }  # fmt: skip
        if q.get("props") == "labels":
            names = {
                "Q30": "United States",
                "Q174193": "United Kingdom of Great Britain and Ireland",
            }
            return {
                "entities": {
                    i: {"labels": {"en": {"value": names[i]}}} for i in q["ids"].split("|")
                }
            }
        raise AssertionError(url)


def test_look_up_follows_links_searches_names_and_skips_placeholders():
    pages = {
        "mark_twain": {"name": "Mark Twain", "title": "Twain"},  # a redirect
        "jane_austen": {"name": "Jane Austen", "title": "Jane Austen"},
        "john_jay": {"name": "John Jay", "title": None},
        "nobody_known": {"name": "Nobody Known", "title": None},
        "various": {"name": "Various", "title": None},
    }
    fake = FakeWikimedia()
    voices = look_up(pages, fake)
    assert voices["mark_twain"] == {
        "name": "Mark Twain",
        "gender": "male",
        "accent": "en-US",
        "citizenship": ["United States"],
        "wikidata": "Q7245",
        "source": "wikidata",
    }
    assert voices["jane_austen"]["gender"] == "female"
    assert voices["jane_austen"]["accent"] == "en-GB"
    assert voices["john_jay"]["source"] == "wikidata-search"
    assert voices["nobody_known"]["source"] == "not found"
    assert voices["various"] == {
        "name": "Various",
        "gender": None,
        "accent": None,
        "citizenship": [],
        "wikidata": None,
        "source": "placeholder",
    }
    assert not any("search=Various" in c for c in fake.calls)  # never looked up


def test_merge_keeps_manual_entries_and_existing_ones_unless_refreshed():
    old = {
        "a": {"gender": "male", "source": "manual"},
        "b": {"gender": "male", "source": "wikidata"},
    }
    new = {
        "a": {"gender": "female", "source": "wikidata"},
        "b": {"gender": "female", "source": "wikidata"},
        "c": {"gender": "female", "source": "wikidata"},
    }
    kept = merge_voices(old, new)
    assert (kept["a"]["gender"], kept["b"]["gender"], kept["c"]["gender"]) == (
        "male",
        "male",
        "female",
    )
    fresh = merge_voices(old, new, refresh=True)
    assert (fresh["a"]["gender"], fresh["b"]["gender"]) == ("male", "female")  # manual survives


def test_voice_for_matches_the_catalog_author_name():
    voices = {"mark_twain": {"gender": "male", "accent": "en-US"}}
    assert voice_for("Mark Twain", voices) == {"gender": "male", "accent": "en-US"}
    assert voice_for("Somebody Else", voices) == {"gender": None, "accent": None}


def test_moot_packs_carry_each_authors_voice():
    transcript = {
        "trees": [
            {"key": "humor/Roughing It", "title": "Roughing It", "author": "Mark Twain"},
            {"key": "x/Unknown", "title": "Unknown", "author": "Nobody"},
        ],
        "utterances": [
            {"turn": 1, "speaker": "humor/Roughing It", "text": "Hi.", "grounded": True},
        ],
    }
    voices = {"mark_twain": {"gender": "male", "accent": "en-US"}}
    pack = moot_pack(transcript, voices)
    assert pack["trees"][0]["voice"] == {"gender": "male", "accent": "en-US"}
    assert pack["trees"][1]["voice"] == {"gender": None, "accent": None}
    json.dumps(pack)  # still plain JSON
