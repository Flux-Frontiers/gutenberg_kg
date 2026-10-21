# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Entmoot: two books from the corpus hold a conversation.

Each book is a :class:`Tree`. On its turn a tree retrieves passages from its
own book only (the worker's ``corpus="<genre>/<book>"`` scope), answers the
other tree from those passages through a local model, and cites them with
``[sN]`` tags. A grounding check verifies the tags against the passages it
was given this turn, and its quoted phrases against every passage its own book
has given it during the moot. A tree may also quote the other tree, tagging the
words ``[oN]`` with the turn they were spoken in; those quotes are checked and
reported separately and never count toward grounding.

This module is pure logic: the worker client and the text synthesizer are
passed in, so tests run with fakes and no network. The ``gutenkg converse``
command wires in the real ones. Nothing here writes to any graph; a moot's
only output is its transcript.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

#: The model a moot uses unless ``--model`` overrides it. 4B models run about
#: three times faster but quote far less reliably.
DEFAULT_MODEL = "Qwen3.8-27B-4bit"

#: Every ``complete`` call is capped here; the persona's word limit alone does
#: not hold a 4B model.
MAX_TOKENS = 250

#: Rebuild the rolling summary before every turn whose index is a multiple of this.
SUMMARY_EVERY = 4

#: How many of the latest utterances each tree sees verbatim.
RECENT_TURNS = 3

# [s1]  [s1, s3]  [s1][s3]  (s1) -- the forms small models produce. [oN] tags
# quote the other tree's turn N and take the same forms.
_TAG_GROUP = re.compile(r"[\[(]\s*([so]\d+(?:\s*,\s*[so]\d+)*)\s*[\])]", re.IGNORECASE)
_TAG = re.compile(r"[so]\d+", re.IGNORECASE)
_QUOTE = re.compile(r'"([^"]+)"')
_QUOTE_CHARS = str.maketrans(
    {
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
    }
)
_QUOTE_MIN_WORDS = 3
# An ellipsis inside a quote marks an elision; each side is checked on its own.
_ELLIPSIS = re.compile(r"\.\.\.|\u2026")

#: Quoted phrases per turn the persona asks for. Guidance only, not enforced.
MAX_QUOTES = 4
_EDGE_PUNCT = " .,;:!?'"


class MootError(RuntimeError):
    """Raised when a moot cannot continue, such as when the model returns nothing."""


@dataclass
class Tree:
    """One book taking part in a moot.

    :param key: The book's catalog key, ``"<genre>/<book>"``.
    :param title: Book title.
    :param author: Book author, or ``""`` when unknown.
    :param genre: Genre name.
    """

    key: str
    title: str
    author: str
    genre: str


@dataclass
class Passage:
    """One retrieved passage, tagged for citation.

    :param tag: Citation tag, ``s1`` .. ``sk``.
    :param label: Section label: the entry date for a diary, the chunk name
        (``chunk:0166``) for a book.
    :param node_id: The passage's node id in its knowledge graph.
    :param content: Passage text.
    """

    tag: str
    label: str
    node_id: str
    content: str


@dataclass
class Utterance:
    """One line of the moot.

    :param turn: Turn number in the transcript, from 1. ``[oN]`` tags name it.
    :param speaker: The speaking tree's key.
    :param title: The speaking tree's title.
    :param text: What it said.
    :param cited: Valid ``sN`` tag -> node id, for each passage tag the reply cited.
    :param quotes: Each double-quoted span of 3+ words: ``{"text", "found", "source"}``,
        where ``source`` is ``"own"`` or ``"other"``.
    :param grounding: The :func:`check_grounding` result for the kept reply.
    :param grounded: Whether the kept reply passed the grounding check.
    :param attempts: 1, or 2 when the first reply failed and the turn was retried.
    :param query: The retrieval query that produced this turn's passages.
    :param retrieved: ``{"tag", "label", "node_id"}`` for every passage given this turn.
    """

    turn: int
    speaker: str
    title: str
    text: str
    cited: dict[str, str]
    quotes: list[dict]
    grounding: dict
    grounded: bool
    attempts: int
    query: str
    retrieved: list[dict]


@dataclass
class Transcript:
    """A finished moot.

    :param trees: The trees, in speaking order.
    :param topic: The seed topic, or ``None``.
    :param model: Model id used for every call.
    :param settings: The run's settings (turns, k, temperature, max_tokens).
    :param utterances: Every utterance, in order.
    :param summaries: ``{"before_turn", "text"}`` for each rolling summary built,
        ``before_turn`` being a turn number.
    """

    trees: list[Tree]
    topic: str | None
    model: str
    settings: dict
    utterances: list[Utterance] = field(default_factory=list)
    summaries: list[dict] = field(default_factory=list)

    def stats(self) -> dict:
        """Grounding totals across the moot.

        :returns: Counts and rates. ``quote_found_rate`` covers quotes of the
            speaker's own book; ``other_quote_valid_rate`` covers ``[oN]``
            quotes of the other tree, which never count toward grounding. A
            rate is ``None`` when there was nothing to count.
        """
        n = len(self.utterances)
        quoted = sum(
            u.grounding["quotes_total"] + u.grounding["other_quotes_total"] for u in self.utterances
        )
        tags_valid = sum(1 for u in self.utterances if u.grounding["tags_valid"])
        cited = sum(1 for u in self.utterances if u.grounding["tags_cited"] > 0)
        found = sum(u.grounding["quotes_found"] for u in self.utterances)
        total = sum(u.grounding["quotes_total"] for u in self.utterances)
        o_found = sum(u.grounding["other_quotes_found"] for u in self.utterances)
        o_total = sum(u.grounding["other_quotes_total"] for u in self.utterances)
        return {
            "turns": n,
            "tags_valid_turns": tags_valid,
            "tags_valid_rate": round(tags_valid / n, 3) if n else None,
            "turns_citing": cited,
            "quotes_found": found,
            "quotes_total": total,
            "quote_found_rate": round(found / total, 3) if total else None,
            "grounded_turns": sum(1 for u in self.utterances if u.grounded),
            "retried_turns": sum(1 for u in self.utterances if u.attempts > 1),
            "other_quotes_found": o_found,
            "other_quotes_total": o_total,
            "other_quote_valid_rate": round(o_found / o_total, 3) if o_total else None,
            "quotes_per_turn": round(quoted / n, 2) if n else None,
        }

    def to_dict(self) -> dict:
        """The transcript as plain JSON-ready data.

        :returns: Trees, topic, model, settings, utterances, summaries and stats.
        """
        return {
            "trees": [asdict(t) for t in self.trees],
            "topic": self.topic,
            "model": self.model,
            "settings": self.settings,
            "utterances": [asdict(u) for u in self.utterances],
            "summaries": self.summaries,
            "stats": self.stats(),
        }


def _book_name(key: str) -> str:
    """The book part of a ``"<genre>/<book>"`` key."""
    return key.split("/", 1)[1] if "/" in key else key


def tree_from_hits(key: str, hits: list[dict]) -> Tree:
    """Build a tree from the first hit of an opening retrieval.

    Enrichment puts ``title``, ``author`` and ``genre`` on every hit. With no
    hits, the title falls back to the book part of the key.

    :param key: The book's catalog key.
    :param hits: Hits from a query scoped to that key.
    :returns: The tree.
    """
    first = hits[0] if hits else {}
    return Tree(
        key=key,
        title=first.get("title") or _book_name(key),
        author=first.get("author") or "",
        genre=first.get("genre") or key.split("/", 1)[0],
    )


def passages_from_hits(hits: list[dict]) -> list[Passage]:
    """Tag hits ``s1..sk`` for citation.

    A diary hit is labeled with its entry date, so Pepys cites days. A book
    hit is labeled with its chunk name, since hits carry no section title.

    :param hits: Worker hits, best first.
    :returns: One passage per hit.
    """
    passages = []
    for i, h in enumerate(hits, start=1):
        ts = h.get("timestamp")
        label = str(ts).split("T", 1)[0] if ts else (h.get("name") or "")
        passages.append(
            Passage(
                tag=f"s{i}",
                label=label,
                node_id=h.get("node_id") or "",
                content=h.get("content") or h.get("summary") or "",
            )
        )
    return passages


def retrieve(client, tree: Tree, text: str, k: int) -> list[Passage]:
    """Retrieve passages from the tree's own book.

    :param client: A ``WorkerClient`` (anything with a compatible ``query``).
    :param tree: The tree whose book is searched.
    :param text: Retrieval query.
    :param k: Passages to retrieve.
    :returns: Tagged passages, best first.
    """
    return passages_from_hits(client.query(text, corpus=tree.key, k=k).get("hits", []))


def retrieval_query(topic: str | None, incoming: str) -> str:
    """The anchor rule: keep every retrieval tied to the moot's topic.

    :param topic: The seed topic, or ``None``.
    :param incoming: The other tree's last line.
    :returns: ``topic + " " + incoming``, or ``incoming`` alone with no topic.
    """
    return f"{topic} {incoming}" if topic else incoming


def persona(tree: Tree, other: Tree, topic: str | None) -> str:
    """The system prompt for one tree.

    :param tree: The speaking tree.
    :param other: The tree it is talking to.
    :param topic: The seed topic, or ``None``.
    :returns: The system prompt.
    """
    by = f" by {tree.author}" if tree.author else ""
    framing = f"The moot has gathered to discuss: {topic}. " if topic else ""
    return (
        f"You are the book {tree.title}{by}, speaking as an old, slow tree in a moot "
        f"with another book, {other.title}. {framing}"
        "You speak only from the passages given to you this turn. "
        "Cite every claim with its passage tag, for example [s2]. "
        "Quote short phrases from your passages exactly, in double quotes, at most "
        f"{MAX_QUOTES} quoted phrases in a turn. Paraphrase the rest, still with its "
        "[sN] tag. "
        "To quote the other tree, put its exact words in double quotes followed by "
        "[oN], where N is the number of the turn it spoke them in, for example [o3]. "
        "Never tag the other tree's words with an [sN] tag. "
        "If no passage bears on what was said, say so plainly and turn the "
        "conversation toward something your passages do cover. "
        f"At most 120 words. No lists. Address the other tree as {other.title}."
    )


def build_messages(
    tree: Tree,
    other: Tree,
    topic: str | None,
    passages: list[Passage],
    summary: str,
    recent: list[Utterance],
    incoming: Utterance | None,
) -> list[dict]:
    """Assemble the chat messages for one turn.

    :param tree: The speaking tree.
    :param other: The tree it is talking to.
    :param topic: The seed topic, or ``None``.
    :param passages: This turn's passages.
    :param summary: The rolling summary so far, or ``""``.
    :param recent: The utterances before ``incoming``, oldest first.
    :param incoming: The other tree's last utterance, or ``None`` when opening.
    :returns: OpenAI-style messages.
    """
    parts = ["Your passages for this turn:"]
    for p in passages:
        parts.append(f"[{p.tag}] ({p.label})\n{p.content}")
    if summary:
        parts.append(f"The moot so far, in brief: {summary}")
    if recent:
        lines = "\n".join(f"Turn {u.turn}, {u.title}: {u.text}" for u in recent)
        parts.append("Most recent lines:\n" + lines)
    if incoming is None:
        opening = f"on {topic}" if topic else "by introducing yourself"
        parts.append(f"Open the moot {opening}, speaking to {other.title}.")
    else:
        parts.append(
            f"Turn {incoming.turn}, {other.title} has just said: {incoming.text}"
            f"\n\nReply to {other.title}."
        )
    return [
        {"role": "system", "content": persona(tree, other, topic)},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _normalize(text: str) -> str:
    """Fold case, map curly quotes to ASCII and collapse whitespace."""
    return " ".join(text.translate(_QUOTE_CHARS).casefold().split())


def parse_tags(text: str) -> list[str]:
    """Every citation tag in a reply, in order, lower-cased.

    :param text: The reply.
    :returns: Tags such as ``["s1", "s3", "o2"]``; repeats are kept.
    """
    return [t.lower() for group in _TAG_GROUP.findall(text) for t in _TAG.findall(group)]


def _quote_spans(text: str) -> list[tuple[str, int, int]]:
    """Every double-quoted span with its position, in ``text`` with curly quotes mapped."""
    return [(m.group(1).strip(_EDGE_PUNCT), m.start(), m.end()) for m in _QUOTE.finditer(text)]


def find_quotes(text: str) -> list[str]:
    """Every double-quoted span of 3 or more words in a reply.

    Curly quotes count as double quotes. Leading and trailing punctuation
    inside the quote marks is dropped.

    :param text: The reply.
    :returns: The quoted spans.
    """
    spans = _quote_spans(text.translate(_QUOTE_CHARS))
    return [q for q, _, _ in spans if len(q.split()) >= _QUOTE_MIN_WORDS]


def _other_turns(text: str, spans: list[tuple[str, int, int]], i: int) -> list[int]:
    """The ``[oN]`` turn numbers attached to quote ``i``, or ``[]`` for an own quote.

    A quote's tag group is the first one after it, which also covers
    ``"a" and "b" [s2]``. Only a quote with no tag after it falls back to the
    last group before it, the ``[o1] "quote"`` form.
    """
    _, start, end = spans[i]
    groups = list(_TAG_GROUP.finditer(text))
    after = [g for g in groups if g.start() >= end]
    before = [g for g in groups if g.end() <= start]
    group = after[0] if after else (before[-1] if before else None)
    if group is None:
        return []
    return [int(t[1:]) for t in _TAG.findall(group.group(1).lower()) if t.startswith("o")]


def _quote_in(quote: str, sources: list[str]) -> bool:
    """Whether a quote appears in the source its tag points to.

    A quote with an ellipsis is split on it, and every fragment of 3 or more
    words must appear in that source; shorter fragments are ignored. With no
    fragment that long, the quote is checked whole.

    :param quote: The quoted span.
    :param sources: The source as normalized texts: every passage in the
        speaker's own-book pool, or the other tree's tagged turns.
    :returns: ``True`` when the quote is found.
    """
    fragments = [
        _normalize(f.strip(_EDGE_PUNCT))
        for f in _ELLIPSIS.split(quote)
        if len(f.split()) >= _QUOTE_MIN_WORDS
    ] or [_normalize(quote)]
    return all(any(f in src for src in sources) for f in fragments)


def check_grounding(
    text: str,
    passages: list[Passage],
    pool: list[Passage] | None = None,
    others: dict[int, str] | None = None,
) -> dict:
    """Check a reply's citations and quotes.

    ``[sN]`` tags must name a passage given this turn. A quote of the
    speaker's own book is found when it appears, after normalization, in any
    passage of that book retrieved during the moot (``pool``); a quote with
    an ellipsis is checked fragment by fragment (see :func:`_quote_in`). A quote tagged
    ``[oN]`` is a quote of the other tree: it is valid when it appears in the
    other tree's turn ``N``, and it is reported separately, never counting
    toward grounding. A quote of the other tree under an ``[sN]`` tag is
    checked as an own quote, so it is a miss. A reply with no tags has
    ``tags_valid`` true, so ``tags_cited`` is reported to make that visible.

    :param text: The reply.
    :param passages: The passages given this turn.
    :param pool: Every passage of the speaker's own book retrieved during the
        moot; defaults to ``passages``.
    :param others: The other tree's utterances so far, turn number -> text.
    :returns: ``{"tags_valid", "tags_cited", "quotes_found", "quotes_total",
        "other_quotes_found", "other_quotes_total", "quotes"}``, where
        ``quotes`` lists ``{"text", "found", "source"}`` per quote.
    """
    by_tag = {p.tag for p in passages}
    s_tags = [t for t in parse_tags(text) if t.startswith("s")]
    haystacks = [_normalize(p.content) for p in (pool if pool is not None else passages)]
    others = others or {}
    flat = text.translate(_QUOTE_CHARS)
    spans = _quote_spans(flat)
    quotes = []
    for i, (q, _, _) in enumerate(spans):
        if len(q.split()) < _QUOTE_MIN_WORDS:
            continue
        turns = _other_turns(flat, spans, i)
        if turns:
            sources = [_normalize(others[n]) for n in turns if n in others]
            quotes.append({"text": q, "found": _quote_in(q, sources), "source": "other"})
        else:
            quotes.append({"text": q, "found": _quote_in(q, haystacks), "source": "own"})
    own = [q for q in quotes if q["source"] == "own"]
    other = [q for q in quotes if q["source"] == "other"]
    return {
        "tags_valid": all(t in by_tag for t in s_tags),
        "tags_cited": len(s_tags),
        "quotes_found": sum(1 for q in own if q["found"]),
        "quotes_total": len(own),
        "other_quotes_found": sum(1 for q in other if q["found"]),
        "other_quotes_total": len(other),
        "quotes": quotes,
    }


def _passes(grounding: dict) -> bool:
    return grounding["tags_valid"] and grounding["quotes_found"] == grounding["quotes_total"]


def _reminder(passages: list[Passage]) -> str:
    tags = ", ".join(p.tag for p in passages)
    return (
        "That reply did not hold to your passages. Cite only the tags you were "
        f"given ({tags}), and put in double quotes only words copied exactly from "
        f"your passages, at most {MAX_QUOTES} quoted phrases; paraphrase the rest with "
        "its [sN] tag. Words of the other tree take an [oN] tag, never an [sN] tag. "
        "Give your reply again."
    )


def turn(
    synth,
    tree: Tree,
    other: Tree,
    topic: str | None,
    passages: list[Passage],
    summary: str,
    recent: list[Utterance],
    incoming: Utterance | None,
    *,
    number: int,
    pool: list[Passage],
    others: dict[int, str],
    query: str,
    model: str | None,
    temperature: float,
) -> Utterance:
    """Speak one turn: complete, check grounding, retry once on failure.

    :param synth: A ``TextSynthesizer`` (anything with a compatible ``complete``).
    :param tree: The speaking tree.
    :param other: The tree it is talking to.
    :param topic: The seed topic, or ``None``.
    :param passages: This turn's passages, already retrieved.
    :param summary: The rolling summary so far.
    :param recent: The utterances before ``incoming``.
    :param incoming: The other tree's last utterance, or ``None`` when opening.
    :param number: This turn's number in the transcript, from 1.
    :param pool: Every passage of this tree's book retrieved during the moot,
        including ``passages``.
    :param others: The other tree's utterances so far, turn number -> text.
    :param query: The retrieval query that produced ``passages`` (recorded only).
    :param model: Model id override, or ``None`` for the synthesizer's default.
    :param temperature: Sampling temperature.
    :returns: The utterance. A reply that fails twice is kept and marked ungrounded.
    :raises MootError: When the model returns no text on both attempts.
    """
    messages = build_messages(tree, other, topic, passages, summary, recent, incoming)
    reply = synth.complete(messages, model=model, max_tokens=MAX_TOKENS, temperature=temperature)
    attempts = 1
    grounding = check_grounding(reply or "", passages, pool, others)
    if not reply or not _passes(grounding):
        attempts = 2
        retry = list(messages)
        if reply:
            retry.append({"role": "assistant", "content": reply})
        retry.append({"role": "user", "content": _reminder(passages)})
        second = synth.complete(retry, model=model, max_tokens=MAX_TOKENS, temperature=temperature)
        if second:
            reply = second
            grounding = check_grounding(reply, passages, pool, others)
    if not reply:
        raise MootError(f"the model returned no text for {tree.title}; is the endpoint up?")
    by_tag = {p.tag: p.node_id for p in passages}
    return Utterance(
        turn=number,
        speaker=tree.key,
        title=tree.title,
        text=reply,
        cited={t: by_tag[t] for t in dict.fromkeys(parse_tags(reply)) if t in by_tag},
        quotes=grounding.pop("quotes"),
        grounding=grounding,
        grounded=_passes(grounding),
        attempts=attempts,
        query=query,
        retrieved=[{"tag": p.tag, "label": p.label, "node_id": p.node_id} for p in passages],
    )


def summarize(synth, summary: str, utterances: list[Utterance], *, model: str | None) -> str:
    """Rebuild the rolling summary with one ``complete`` call.

    :param synth: The text synthesizer.
    :param summary: The previous summary, or ``""``.
    :param utterances: Every utterance so far.
    :param model: Model id override, or ``None``.
    :returns: The new summary, or the previous one if the model returned nothing.
    """
    lines = "\n".join(f"{u.title}: {u.text}" for u in utterances)
    prior = f"Earlier summary: {summary}\n\n" if summary else ""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a neutral narrator. Summarize the conversation in at most "
                "80 words. Add no facts that are not in it."
            ),
        },
        {"role": "user", "content": f"{prior}Conversation:\n{lines}"},
    ]
    return synth.complete(messages, model=model, max_tokens=MAX_TOKENS, temperature=0.2) or summary


def _add_to_pool(pool: dict[str, Passage], passages: list[Passage]) -> None:
    """Add passages to a tree's pool, keyed by node id so repeats are kept once."""
    for p in passages:
        pool.setdefault(p.node_id, p)


def run_moot(
    client,
    synth,
    keys: list[str],
    topic: str | None,
    turns: int,
    *,
    k: int = 6,
    model: str | None = None,
    model_name: str = "",
    temperature: float = 0.6,
    on_utterance=None,
) -> Transcript:
    """Hold a moot between two books.

    Both trees first retrieve on the topic alone (or on their own book name
    with no topic); that opening retrieval names each tree, and the first
    speaker opens from its passages. Every later turn retrieves on
    :func:`retrieval_query`. Each tree keeps a pool of every passage its own
    book has returned during the moot, against which its quotes are checked.
    The rolling summary is rebuilt before every turn whose index is a
    positive multiple of :data:`SUMMARY_EVERY`.

    :param client: A ``WorkerClient`` (anything with a compatible ``query``).
    :param synth: A ``TextSynthesizer`` (anything with a compatible ``complete``).
    :param keys: The two books' catalog keys, in speaking order.
    :param topic: The seed topic, or ``None``.
    :param turns: Total utterances.
    :param k: Passages per turn.
    :param model: Model id passed to ``complete``, or ``None`` for the
        synthesizer's default.
    :param model_name: Model id recorded in the transcript.
    :param temperature: Sampling temperature.
    :param on_utterance: Optional callback, called with each utterance as it lands.
    :returns: The transcript.
    :raises ValueError: When the same book key is given twice.
    """
    if len(set(keys)) != len(keys):
        raise ValueError(f"a moot needs two different books, got {keys[0]!r} twice")
    opening: list[list[Passage]] = []
    trees: list[Tree] = []
    pools: dict[str, dict[str, Passage]] = {key: {} for key in keys}
    opening_queries = [topic or _book_name(key) for key in keys]
    for key, opening_query in zip(keys, opening_queries, strict=True):
        hits = client.query(opening_query, corpus=key, k=k).get("hits", [])
        trees.append(tree_from_hits(key, hits))
        opening.append(passages_from_hits(hits))
        _add_to_pool(pools[key], opening[-1])

    transcript = Transcript(
        trees=trees,
        topic=topic,
        model=model_name or model or "",
        settings={"turns": turns, "k": k, "temperature": temperature, "max_tokens": MAX_TOKENS},
    )
    summary = ""
    for i in range(turns):
        speaker, other = trees[i % 2], trees[(i + 1) % 2]
        if i and i % SUMMARY_EVERY == 0:
            summary = summarize(synth, summary, transcript.utterances, model=model)
            transcript.summaries.append({"before_turn": i + 1, "text": summary})
        incoming = transcript.utterances[-1] if transcript.utterances else None
        if incoming is None:
            passages, query = opening[0], opening_queries[0]
        else:
            query = retrieval_query(topic, incoming.text)
            passages = retrieve(client, speaker, query, k)
            _add_to_pool(pools[speaker.key], passages)
        utterance = turn(
            synth,
            speaker,
            other,
            topic,
            passages,
            summary,
            transcript.utterances[-(RECENT_TURNS + 1) : -1],
            incoming,
            number=i + 1,
            pool=list(pools[speaker.key].values()),
            others={u.turn: u.text for u in transcript.utterances if u.speaker == other.key},
            query=query,
            model=model,
            temperature=temperature,
        )
        transcript.utterances.append(utterance)
        if on_utterance is not None:
            on_utterance(utterance)
    return transcript
