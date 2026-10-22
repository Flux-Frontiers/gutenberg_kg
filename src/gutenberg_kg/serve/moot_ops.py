# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Live moots for the Knowledge Press Forest: the worker holds each moot.

The forest starts a moot with ``moot_start``, asks for each turn with
``moot_turn`` and plays it as it lands, and may end it with ``moot_stop``. The
worker keeps the :class:`~gutenberg_kg.serve.entmoot.Moot` between requests
because a turn needs each book's passage pool, its cited passages and the
rolling summary; sending those back and forth would be large, and a browser
could send a doctored pool and pass the grounding check.

Everything here takes its search, synthesizer and clock as arguments, so it is
tested without the handler, which opens stores and loads the embedder when it
is imported (see :mod:`gutenberg_kg.serve.scope`).

Sessions live in memory: a worker restart ends every moot. At most
:data:`MAX_SESSIONS` are held; a session idle for :data:`IDLE_SECONDS` is
dropped, and when the table is full the least recently used one makes room.
"""

from __future__ import annotations

import hmac
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from gutenberg_kg.export_web_moots import moot_id, pack_tree, pack_turn
from gutenberg_kg.serve.entmoot import Moot, resolve_model

#: The ops this module answers.
MOOT_OPS = frozenset({"moot_start", "moot_turn", "moot_stop"})
#: Live moots held at once.
MAX_SESSIONS = 4
#: A moot nobody has asked for a turn in this long is dropped.
IDLE_SECONDS = 30 * 60
#: Bounds on a moot's length and passages per turn, the CLI's own.
TURNS_RANGE = (2, 40)
K_RANGE = (1, 20)
DEFAULT_TURNS = 8
DEFAULT_K = 6
DEFAULT_TEMPERATURE = 0.6


def authorized(inp: dict, *, moot_token: str, handler_secret: str) -> bool:
    """Whether a moot request may run.

    ``MOOT_TOKEN`` exists so a browser never holds ``HANDLER_SECRET``. When it
    is set, a moot op passes with that token; the handler secret also passes,
    for scripts. When neither is set, every moot op passes, as every other op
    does on a worker with no secret.

    :param inp: The request's ``input``.
    :param moot_token: ``MOOT_TOKEN``, or ``""``.
    :param handler_secret: ``HANDLER_SECRET``, or ``""``.
    :returns: ``True`` when the request may run.
    """
    if moot_token and hmac.compare_digest(str(inp.get("token", "")), moot_token):
        return True
    if handler_secret:
        return hmac.compare_digest(str(inp.get("secret", "")), handler_secret)
    return not moot_token


class _Session:
    """One live moot and when it was last asked for."""

    def __init__(self, moot: Moot, run: dict, last_used: float) -> None:
        self.moot = moot
        self.run = run
        self.last_used = last_used


class MootSessions:
    """The live moots one worker holds.

    :param client: Retrieval: anything with ``query(text, corpus=, k=)``
        returning ``{"hits": [...]}``, as ``WorkerClient`` does.
    :param synth: The worker's text synthesizer.
    :param backend: The synthesizer's backend name, e.g. ``"omlx"``; picks the
        default model as the CLI does.
    :param is_book: Whether a key names one book or diary the worker serves.
    :param voices: The author voice table, for each tree's ``voice``.
    :param clock: Seconds, monotonic; a seam for tests.
    """

    def __init__(
        self,
        client,
        synth,
        backend: str,
        is_book: Callable[[str], bool],
        voices: dict[str, dict],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client, self.synth, self.backend = client, synth, backend
        self.is_book, self.voices, self.clock = is_book, voices, clock
        self.sessions: dict[str, _Session] = {}

    def handle(self, op: str, inp: dict) -> dict:
        """Answer one moot op.

        :param op: One of :data:`MOOT_OPS`.
        :param inp: The request's ``input``.
        :returns: The op's result, or ``{"error": ...}``.
        """
        self._expire()
        if op == "moot_start":
            return self._start(inp)
        if op == "moot_turn":
            return self._turn(inp)
        if op == "moot_stop":
            return {"stopped": self.sessions.pop(str(inp.get("moot_id", "")), None) is not None}
        return {"error": f"unknown moot op {op!r}"}

    def _expire(self) -> None:
        now = self.clock()
        for key in [k for k, s in self.sessions.items() if now - s.last_used > IDLE_SECONDS]:
            del self.sessions[key]

    def _start(self, inp: dict) -> dict:
        books = inp.get("books")
        if (
            not isinstance(books, list)
            or len(books) != 2
            or not all(isinstance(b, str) and b for b in books)
        ):
            return {"error": "moot_start needs books: two catalog keys"}
        if books[0] == books[1]:
            return {"error": "a moot needs two different books"}
        unknown = [b for b in books if not self.is_book(b)]
        if unknown:
            return {"error": f"unknown book {unknown[0]!r}; use a <genre>/<book> catalog key"}
        try:
            turns = int(inp.get("turns", DEFAULT_TURNS))
            k = int(inp.get("k", DEFAULT_K))
            temperature = float(inp.get("temperature", DEFAULT_TEMPERATURE))
        except (TypeError, ValueError):
            return {"error": "turns and k must be integers, temperature a number"}
        if not TURNS_RANGE[0] <= turns <= TURNS_RANGE[1]:
            return {"error": f"turns must be {TURNS_RANGE[0]}-{TURNS_RANGE[1]}"}
        if not K_RANGE[0] <= k <= K_RANGE[1]:
            return {"error": f"k must be {K_RANGE[0]}-{K_RANGE[1]}"}
        topic = str(inp.get("topic") or "").strip() or None
        call_model, model_name = resolve_model(
            self.backend, str(inp.get("model") or "").strip() or None, self.synth
        )
        moot = Moot(
            self.client,
            self.synth,
            books,
            topic,
            turns,
            k=k,
            model=call_model,
            model_name=model_name,
            temperature=temperature,
        )
        try:
            transcript = moot.start()
        except Exception as exc:  # noqa: BLE001 -- retrieval failed; nothing is held
            return {"error": f"{type(exc).__name__}: {exc}"}
        if len(self.sessions) >= MAX_SESSIONS:
            oldest = min(self.sessions, key=lambda key: self.sessions[key].last_used)
            del self.sessions[oldest]
        session_id = uuid.uuid4().hex
        run = {"started": datetime.now(UTC).isoformat(), "backend": self.backend}
        self.sessions[session_id] = _Session(moot, run, self.clock())
        data = transcript.to_dict()
        return {
            "moot_id": session_id,
            "id": moot_id(data),
            "topic": topic,
            "date": run["started"][:10],
            "model": model_name,
            "backend": self.backend,
            "turns": turns,
            "trees": [pack_tree(t, self.voices) for t in data["trees"]],
        }

    def _turn(self, inp: dict) -> dict:
        session = self.sessions.get(str(inp.get("moot_id", "")))
        if session is None:
            return {"error": "no such moot; it may have ended or the worker restarted"}
        session.last_used = self.clock()
        moot = session.moot
        if moot.done:
            return {"error": "the moot is over"}
        try:
            moot.next_turn()
        except Exception as exc:  # noqa: BLE001 -- a backend failure; the moot can be asked again
            return {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            session.last_used = self.clock()
        transcript = moot.transcript
        assert transcript is not None  # started in _start
        side = {t.key: i for i, t in enumerate(transcript.trees)}
        data = transcript.to_dict()
        result: dict = {"turn": pack_turn(data["utterances"][-1], side), "done": moot.done}
        if moot.done:
            result["stats"] = data["stats"]
            del self.sessions[str(inp["moot_id"])]
        return result
