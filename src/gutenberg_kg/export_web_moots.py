# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Moot packs for the Knowledge Press Forest.

``gutenkg converse --out`` writes a transcript: every turn, its retrieval,
the model's raw reply and the grounding results. The forest needs less and
must not depend on that format, so this module turns transcripts into small
moot packs, version :data:`PACK_VERSION`, and keeps an index of them:

- ``moots/<id>.json``: the trees (with each author's voice: gender and
  accent from ``corpus/authors/voices.json``), topic, date and model, and each turn as
  the reader sees it -- the snapped text, the speaker (0 or 1), the
  passages it cites, whether it was grounded and the corrections made.
- ``moots/index.json``: one entry per moot, merged by id.

A tree is named by its worker key, ``"<genre>/<book>"``, which the forest's
catalog entries also carry as ``genre`` and ``book``. A pack never carries
the raw reply, prompts or retrieval queries.
"""

from __future__ import annotations

import json
from pathlib import Path

from gutenberg_kg.author_voices import read_voices, voice_for
from gutenberg_kg.export_web import KNOWLEDGE_PRESS_DIR
from gutenberg_kg.ingest import slugify

PACK_VERSION = 1
DEFAULT_OUT = KNOWLEDGE_PRESS_DIR / "web" / "public" / "moots"
INDEX_NAME = "index.json"


class MootPackError(ValueError):
    """Raised when a file is not a ``converse --out`` transcript."""


def _book_name(key: str) -> str:
    return key.split("/", 1)[-1]


def moot_id(transcript: dict) -> str:
    """The pack id: a slug of both book names and the topic.

    Re-running a pairing on the same topic gives the same id, so its pack
    replaces the earlier one.

    :param transcript: A ``converse --out`` transcript.
    :returns: e.g. ``"the-diary-of-samuel-pepys-complete-thus-spake-zarathustra-jealousy"``.
    """
    names = [_book_name(t["key"]) for t in transcript["trees"]]
    return slugify(" ".join([*names, transcript.get("topic") or ""]))


def pack_tree(tree: dict, voices: dict[str, dict]) -> dict:
    """One tree as a pack carries it.

    :param tree: A transcript tree, ``{"key", "title", "author", ...}``.
    :param voices: The author voice table.
    :returns: ``{key, title, author, voice}``.
    """
    return {
        "key": tree["key"],
        "title": tree["title"],
        "author": tree["author"],
        "voice": voice_for(tree["author"], voices),
    }


def pack_turn(utterance: dict, side: dict[str, int]) -> dict:
    """One utterance as a pack turn: what the reader sees.

    :param utterance: A transcript utterance.
    :param side: Each tree's key -> 0 or 1, its speaking order.
    :returns: ``{turn, speaker, text, cites, grounded, snaps}``; never the raw
        reply, prompts or retrieval query.
    """
    labels = {r["tag"]: r["label"] for r in utterance.get("retrieved", [])}
    return {
        "turn": utterance["turn"],
        "speaker": side[utterance["speaker"]],
        "text": utterance["text"],
        "cites": [
            {"tag": tag, "label": labels.get(tag, ""), "node_id": node_id}
            for tag, node_id in utterance.get("cited", {}).items()
        ],
        "grounded": utterance["grounded"],
        "snaps": [
            {k: s.get(k) for k in ("text", "action", "to", "reason")}
            for s in utterance.get("snaps", [])
        ],
    }


def moot_pack(transcript: dict, voices: dict[str, dict] | None = None) -> dict:
    """Turn a transcript into a moot pack.

    :param transcript: A ``converse --out`` transcript.
    :param voices: The author voice table; each tree's ``voice`` is
        ``{"gender", "accent"}``, both ``None`` for an author not in it.
    :returns: The pack, JSON-ready.
    :raises MootPackError: When the transcript lacks two trees or any turns.
    """
    trees = transcript.get("trees")
    utterances = transcript.get("utterances")
    if not isinstance(trees, list) or len(trees) != 2 or not utterances:
        raise MootPackError("not a converse transcript: needs two trees and at least one turn")
    side = {t["key"]: i for i, t in enumerate(trees)}
    run = transcript.get("run") or {}
    return {
        "version": PACK_VERSION,
        "id": moot_id(transcript),
        "topic": transcript.get("topic"),
        "date": (run.get("started") or "")[:10],
        "model": transcript.get("model", ""),
        "backend": run.get("backend", ""),
        "trees": [pack_tree(t, voices or {}) for t in trees],
        "turns": [pack_turn(u, side) for u in utterances],
        "stats": transcript.get("stats", {}),
    }


def index_entry(pack: dict) -> dict:
    """One moot's line in ``index.json``.

    :param pack: A moot pack.
    :returns: ``{id, title, topic, trees, turns, date}``.
    """
    titles = " and ".join(t["title"] for t in pack["trees"])
    topic = pack["topic"]
    return {
        "id": pack["id"],
        "title": f"{titles} on {topic}" if topic else titles,
        "topic": topic,
        "trees": [t["key"] for t in pack["trees"]],
        "turns": len(pack["turns"]),
        "date": pack["date"],
    }


def write_moots(
    transcripts: list[Path], out_dir: Path, voices: dict[str, dict] | None = None
) -> list[str]:
    """Write a pack per transcript and merge them into the index.

    :param transcripts: ``converse --out`` transcript files.
    :param out_dir: The forest's ``public/moots`` directory; created if missing.
    :param voices: The author voice table; ``corpus/authors/voices.json`` if omitted.
    :returns: The ids written, in input order.
    :raises MootPackError: When a file is not valid JSON or not a transcript.
    """
    voices = read_voices() if voices is None else voices
    packs = []
    for path in transcripts:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MootPackError(f"{path}: {exc}") from exc
        try:
            packs.append(moot_pack(data, voices))
        except (MootPackError, KeyError, TypeError) as exc:
            raise MootPackError(f"{path}: {exc}") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / INDEX_NAME
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else []
    entries = {e["id"]: e for e in index}
    for pack in packs:
        (out_dir / f"{pack['id']}.json").write_text(
            json.dumps(pack, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        entries[pack["id"]] = index_entry(pack)
    ordered = sorted(entries.values(), key=lambda e: (e["date"], e["id"]), reverse=True)
    index_path.write_text(
        json.dumps(ordered, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return [p["id"] for p in packs]
