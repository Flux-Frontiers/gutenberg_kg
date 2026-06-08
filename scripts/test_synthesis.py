#!/usr/bin/env python3
# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Smoke-test kg_utils.synthesis backends without the full KG stack.

Tests text synthesis (list_models, synthesize_rag, rewrite_for_image) across
the three backends in order: oMLX (base case / env default), Ollama, OpenAI.
Each backend is tried independently; connection failures are reported and the
script continues to the next.

Usage
-----
    # base env (oMLX default, Ollama at localhost:11434, OpenAI via OPENAI_API_KEY):
    .venv/bin/python scripts/test_synthesis.py

    # override oMLX endpoint:
    VLLM_ENDPOINT_URL=http://myserver:8080/v1 .venv/bin/python scripts/test_synthesis.py

    # skip a backend:
    SKIP_OMLX=1 .venv/bin/python scripts/test_synthesis.py
"""

from __future__ import annotations

import os
import sys
import textwrap
import time

# Allow running from repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kg_utils.synthesis import TextSynthesizer, text_synthesizer_from_env
from kg_utils.synthesis._config import TextBackend, TextConfig

# ---------------------------------------------------------------------------
# Fixed test fixtures
# ---------------------------------------------------------------------------

QUERY = "What does Marcus Aurelius say about enduring hardship and maintaining virtue?"

SNIPPETS = [
    {
        "content": (
            "Begin the morning by saying to thyself, I shall meet with the busy-body, "
            "the ungrateful, arrogant, deceitful, envious, unsocial. All these things "
            "happen to them by reason of their ignorance of what is good and evil. "
            "But I who have seen the nature of the good that it is beautiful, and of "
            "the bad that it is ugly... I can neither be injured by any of them."
        ),
        "genre": "philosophy",
        "author": "Marcus Aurelius",
        "title": "Meditations",
        "score": 0.891,
    },
    {
        "content": (
            "Never esteem anything as of advantage to you that will make you break your "
            "word or lose your self-respect. If a man has no inner life, the outer world "
            "profits him little. The impediment to action advances action. What stands in "
            "the way becomes the way."
        ),
        "genre": "philosophy",
        "author": "Marcus Aurelius",
        "title": "Meditations",
        "score": 0.874,
    },
    {
        "content": (
            "Seek not the good in external things; seek it in thyself. Thou hast power "
            "over thy mind, not outside events. Realise this, and you will find strength. "
            "Very little is needed to make a happy life; it is all within yourself, in "
            "your way of thinking."
        ),
        "genre": "philosophy",
        "author": "Marcus Aurelius",
        "title": "Meditations",
        "score": 0.861,
    },
    {
        "content": (
            "Make the best use of what is in your power, and take the rest as it happens. "
            "It's not what happens to you, but how you react to it that matters. "
            "Men are disturbed not by things, but by the opinions about things."
        ),
        "genre": "philosophy",
        "author": "Epictetus",
        "title": "Enchiridion",
        "score": 0.843,
    },
]

IMAGE_PASSAGE = (
    "The great fire had now got as far as the steele-yard, and in a most horrid, malicious, "
    "bloody flame, not like the fine flame of an ordinary fire. We stayed till, it being "
    "darkish, we saw the fire as only one entire arch of fire above a mile long: it made "
    "me weep to see it."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_W = 72


def _hr(char: str = "─") -> None:
    print(char * _W)


def _header(title: str) -> None:
    print()
    _hr("═")
    print(f"  {title}")
    _hr("═")


def _section(title: str) -> None:
    print(f"\n  ── {title}")


def _wrap(text: str, indent: int = 6) -> str:
    prefix = " " * indent
    return textwrap.fill(text, width=_W, initial_indent=prefix, subsequent_indent=prefix)


def _try_synth(synth: TextSynthesizer, label: str) -> None:
    cfg = synth._cfg

    _section("list_models()")
    t0 = time.perf_counter()
    models = synth.list_models()
    ms = (time.perf_counter() - t0) * 1000
    if models:
        print(
            f"      {len(models)} model(s) in {ms:.0f}ms: {', '.join(models[:4])}"
            + (" ..." if len(models) > 4 else "")
        )
    else:
        print(f"      (none returned or endpoint unreachable)  {ms:.0f}ms")

    _section(f"synthesize_rag()  model={cfg.resolved_model()}")
    print(f"      query: {QUERY[:60]}...")
    t0 = time.perf_counter()
    result = synth.synthesize_rag(QUERY, SNIPPETS, max_k=4)
    ms = (time.perf_counter() - t0) * 1000
    if result:
        print(f"      [{ms:.0f}ms]\n")
        print(_wrap(result))
    else:
        print(f"      [FAILED / no response]  {ms:.0f}ms")

    _section("rewrite_for_image()")
    print(f"      passage: {IMAGE_PASSAGE[:60]}...")
    t0 = time.perf_counter()
    prompt, err = synth.rewrite_for_image(IMAGE_PASSAGE)
    ms = (time.perf_counter() - t0) * 1000
    if err:
        print(f"      [FAILED: {err}]  {ms:.0f}ms")
    else:
        print(f"      [{ms:.0f}ms]\n")
        print(_wrap(prompt))


# ---------------------------------------------------------------------------
# Backend configurations
# ---------------------------------------------------------------------------


def _backends() -> list[tuple[str, TextSynthesizer | None, str]]:
    """Return (label, synthesizer, skip_reason) triples."""
    entries: list[tuple[str, TextSynthesizer | None, str]] = []

    # 1. oMLX — base case, built from env (respects VLLM_ENDPOINT_URL legacy var)
    if os.environ.get("SKIP_OMLX"):
        entries.append(("oMLX  (base case / env default)", None, "SKIP_OMLX set"))
    else:
        synth = text_synthesizer_from_env()
        entries.append(
            (
                f"oMLX  (base case / env default)\n"
                f"    endpoint : {synth._cfg.resolved_endpoint()}\n"
                f"    model    : {synth._cfg.resolved_model()}",
                synth,
                "",
            )
        )

    # 2. Ollama — explicit config, no env side-effects
    if os.environ.get("SKIP_OLLAMA"):
        entries.append(("Ollama", None, "SKIP_OLLAMA set"))
    else:
        cfg = TextConfig(backend=TextBackend.OLLAMA)
        synth = TextSynthesizer(cfg)
        entries.append(
            (
                f"Ollama\n"
                f"    endpoint : {cfg.resolved_endpoint()}\n"
                f"    model    : {cfg.resolved_model()}",
                synth,
                "",
            )
        )

    # 3. OpenAI — requires OPENAI_API_KEY
    if os.environ.get("SKIP_OPENAI"):
        entries.append(("OpenAI", None, "SKIP_OPENAI set"))
    elif not os.environ.get("OPENAI_API_KEY") and not os.environ.get("SYNTH_API_KEY"):
        entries.append(("OpenAI", None, "no OPENAI_API_KEY / SYNTH_API_KEY in env"))
    else:
        cfg = TextConfig(
            backend=TextBackend.OPENAI,
            api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("SYNTH_API_KEY", ""),
        )
        synth = TextSynthesizer(cfg)
        entries.append(
            (
                f"OpenAI\n"
                f"    endpoint : {cfg.resolved_endpoint()}\n"
                f"    model    : {cfg.resolved_model()}",
                synth,
                "",
            )
        )

    return entries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("\nkg_utils.synthesis — backend smoke test")
    print(f"query  : {QUERY[:72]}")
    print(f"snippets: {len(SNIPPETS)} fixture passages (Marcus Aurelius / Epictetus)")

    results: list[tuple[str, str]] = []  # (backend, pass|fail|skip)

    for label, synth, skip_reason in _backends():
        short = label.split("\n")[0]
        _header(label)

        if synth is None:
            print(f"\n  SKIPPED — {skip_reason}")
            results.append((short, "skip"))
            continue

        try:
            _try_synth(synth, short)
            results.append((short, "pass"))
        except Exception as exc:  # noqa: BLE001
            print(f"\n  EXCEPTION: {exc}")
            results.append((short, "fail"))

    # Summary
    print()
    _hr()
    print("  Summary")
    _hr()
    for label, status in results:
        icon = {"pass": "✓", "fail": "✗", "skip": "–"}.get(status, "?")
        print(f"  {icon}  {label}")
    _hr()
    print()

    if any(s == "fail" for _, s in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
