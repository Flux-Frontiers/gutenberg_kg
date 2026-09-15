# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""The synthesis prompt contract, in one place, for every Python caller.

Four things answer questions over this corpus: the local worker
(:mod:`gutenberg_kg.serve.handler`), the RunPod worker (``runpod/handler.py``),
and the Swift app's two Foundation Models backends. They must be held to the
same rule -- answer only from the passages -- or the same question gives
answers of different trustworthiness depending on which one happened to run.

Keeping that true needs a single definition per prompt and a test that fails
when a copy drifts. Before this module existed there were three copies and one
had already drifted: ``runpod/handler.py`` carried an inlined paraphrase that
had lost both "Do NOT use any prior knowledge" and "Never contradict or
override what the passages say", which are the two sentences that make an
answer citable rather than merely plausible.

:data:`RAG_SYSTEM` is re-exported from ``kg_utils`` rather than restated, so
there is exactly one definition of it in the fleet. :data:`GUIDE_SYSTEM` is
this repo's own, and is mirrored in Swift as
``SynthesisPrompt.guideInstructions``; ``tests/test_synthesis_parity.py``
compares the two texts and fails on any drift.
"""

from __future__ import annotations

from kg_utils.synthesis._text import _IMAGE_REWRITE_SYSTEM, _RAG_SYSTEM

#: The original contract, written for the worker's server-class model.
#: Mirrored verbatim in Swift as ``SynthesisPrompt.ragInstructions``.
RAG_SYSTEM: str = _RAG_SYSTEM

#: Prose to image prompt. Mirrored as ``SynthesisPrompt.imageRewriteInstructions``.
IMAGE_REWRITE_SYSTEM: str = _IMAGE_REWRITE_SYSTEM

#: Written for Apple's on-device and Private Cloud Compute models, which are
#: far smaller than the worker's and answer :data:`RAG_SYSTEM` with one
#: clipped sentence -- measured 2026-09-14: given two verbatim Genesis 19
#: chunks for "pillar of salt", 101 characters.
#:
#: Follows Apple's guidance for the Foundation Models framework: a role in the
#: first sentence, the task stated once, uppercase on the rules that matter,
#: and an explicit shape for the output. The small models obey "two or three
#: short paragraphs" where "Be concise" collapses them to a single line.
#:
#: Deliberately does NOT ask the model to ignore off-topic passages. Tried;
#: a 3B model cannot judge relevance and summarised every passage it was told
#: to skip. Relevance belongs to retrieval and packing.
#:
#: Mirrored in Swift as ``SynthesisPrompt.guideInstructions``.
GUIDE_SYSTEM: str = (
    "You are a literary guide to a library of classic books. A reader has "
    "searched the library for a topic and is shown the passages that "
    "matched. Your job is to explain what those passages say about the "
    "reader's topic.\n"
    "\n"
    "RULES:\n"
    "- Use ONLY the source passages. Do NOT add anything from your own "
    "knowledge. If the passages do not answer the topic, say which part "
    "is missing rather than filling it in.\n"
    '- If the topic is a phrase rather than a question, treat it as "What '
    'do these passages say about this?"\n'
    "- Name the work and author the first time you draw on each one.\n"
    "- Answer in plain prose, two or three short paragraphs. No bullet "
    "points, no headings. Quote at most one sentence at a time.\n"
    "- Be concrete: who, what, where, and what happened, as the passages "
    "tell it."
)

#: Selectable prompts, by the name the ``SYNTH_PROMPT`` environment variable
#: and Swift's ``SynthesisTuning.Instructions`` both use.
PROMPTS: dict[str, str] = {"guide": GUIDE_SYSTEM, "worker": RAG_SYSTEM}

#: What the workers use when ``SYNTH_PROMPT`` is unset.
DEFAULT_PROMPT = "guide"


def system_prompt(name: str | None = None) -> str:
    """Resolve a prompt by name.

    :param name: ``"guide"`` or ``"worker"``; ``None`` selects
        :data:`DEFAULT_PROMPT`. An unknown name falls back to the default
        rather than raising -- a typo in an environment variable should not
        take the worker down mid-query.
    :returns: The system prompt text.
    """
    return PROMPTS.get((name or DEFAULT_PROMPT).strip().lower(), PROMPTS[DEFAULT_PROMPT])


#: Separator between the genre, author and title of a passage header, as both
#: workers and the Swift budgeter write it. ``runpod/handler.py`` used " | "
#: until 2026-09-15, so a RunPod answer saw a different prompt shape from
#: every other engine.
HEADER_SEPARATOR = " · "
