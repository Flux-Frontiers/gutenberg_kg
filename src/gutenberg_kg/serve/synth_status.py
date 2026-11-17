# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Explain an empty synthesis.

Kept out of handler.py, which starts the worker when it is imported, so the
rule can be tested on its own.
"""

from __future__ import annotations


def empty_synthesis_error(hits: list[dict], model: str, max_k: int) -> str | None:
    """Explain an empty synthesis, or return ``None`` when nothing was asked of the model.

    The synthesizer returns ``None`` for any backend failure, an oMLX refusal to
    load a model among them, so without this the reply is a blank answer with
    no error. When none of the hits synthesis sees carries text, there was
    nothing to synthesize from, and that is not an error.

    :param hits: The hits passed to synthesis.
    :param model: The model synthesis was asked to use.
    :param max_k: How many hits synthesis reads (``SYNTH_MAX_K``).
    :returns: A message for ``synthesis_error``, or ``None``.
    """
    if not any((h.get("content") or "").strip() for h in hits[:max_k]):
        return None
    return (
        f"{model} returned no answer. The LLM server may have refused to load it "
        "(oMLX does when it does not fit in memory), or may be down. "
        "Try a smaller model; `make models` picks one for this Mac."
    )
