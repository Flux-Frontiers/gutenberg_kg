# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""The Swift/Python synthesis contract, enforced rather than commented.

Retrieval parity has had a real gate since the packs existed: ``golden.json``
records what the Python reference returns and ``GoldenParityTests`` replays it
through Swift. Synthesis had nothing of the kind. ``SynthesisPrompt.swift``
asked the reader to "keep this file and _text.py's _RAG_SYSTEM in sync", and
the only test was a substring check that would pass against a prompt rewritten
end to end.

That gap was not hypothetical. ``runpod/handler.py`` carried an inlined
paraphrase of the RAG prompt that had lost "Do NOT use any prior knowledge"
and "Never contradict or override what the passages say", and joined passage
headers with " | " where everything else used " · ". Nothing failed, because
nothing looked.

These tests read the Swift source as text and compare the literals to the
Python constants. They need no toolchain, no corpus and no device, so they run
in ordinary CI on every change to either side.

Deliberate divergences are asserted as divergences, not quietly tolerated:
what must match is pinned, and what must differ is pinned too, so that
collapsing the two engines onto one prompt also fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gutenberg_kg.synthesis_prompts import (
    GUIDE_SYSTEM,
    HEADER_SEPARATOR,
    IMAGE_REWRITE_SYSTEM,
    RAG_SYSTEM,
)

REPO = Path(__file__).resolve().parents[1]
SWIFT = REPO / "app/GutenbergKGKit/Sources/GutenbergKGKit/Synthesis"
PROMPT_SWIFT = SWIFT / "SynthesisPrompt.swift"
BUDGET_SWIFT = SWIFT / "ContextBudgeter.swift"

pytestmark = pytest.mark.skipif(
    not PROMPT_SWIFT.exists(), reason="Swift sources not present in this checkout"
)


def _normalise(text: str) -> str:
    """Strip per-line indentation and trailing space, keeping blank lines.

    Swift multiline literals carry the closing delimiter's indentation on
    every line; Python's implicit concatenation carries none. Comparing the
    two means discarding leading whitespace on both sides -- which is safe
    here because neither prompt uses indentation meaningfully.
    """
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _swift_multiline(name: str, source: str) -> str:
    """Extract a Swift ``static let NAME = \"\"\"…\"\"\"`` literal as its runtime value.

    :param name: The declared constant's name.
    :param source: The full Swift file text.
    :returns: The literal's value with line continuations resolved.
    :raises AssertionError: If the constant is not found, which is itself the
        drift worth reporting -- a renamed constant breaks the contract as
        surely as a reworded one.
    """
    match = re.search(rf'static let {name} = """\n(.*?)\n\s*"""', source, re.S)
    assert match, f"{name} not found in {PROMPT_SWIFT.name} — renamed or removed?"

    # A trailing backslash joins to the next line with no separator inserted.
    joined: list[str] = []
    buffer = ""
    for line in match.group(1).split("\n"):
        stripped = line.strip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1]
        else:
            joined.append(buffer + stripped)
            buffer = ""
    return _normalise("\n".join(joined))


@pytest.fixture(scope="module")
def prompt_source() -> str:
    return PROMPT_SWIFT.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("swift_name", "python_value"),
    [
        ("ragInstructions", RAG_SYSTEM),
        ("guideInstructions", GUIDE_SYSTEM),
        ("imageRewriteInstructions", IMAGE_REWRITE_SYSTEM),
    ],
)
def test_swift_prompt_matches_python(
    swift_name: str, python_value: str, prompt_source: str
) -> None:
    """Every prompt the Swift app uses is the one Python defines, word for word."""
    assert _swift_multiline(swift_name, prompt_source) == _normalise(python_value), (
        f"{swift_name} has drifted from its Python definition in "
        f"gutenberg_kg.synthesis_prompts. Change both or neither."
    )


def test_the_two_prompts_are_still_different() -> None:
    """The guide prompt exists because the small models need different words.

    Pinned so that "converging" the two by deleting one is a test failure and
    not a silent loss of the ability to compare engines under identical
    instructions.
    """
    assert GUIDE_SYSTEM != RAG_SYSTEM
    assert "Be concise and specific" in RAG_SYSTEM
    # The phrase that collapsed a 3B model to one sentence, absent by design.
    assert "concise" not in GUIDE_SYSTEM.lower()


def test_guide_prompt_keeps_the_grounding_rule() -> None:
    """Whatever else is reworded, the answer stays tied to the passages."""
    assert "Use ONLY the source passages" in GUIDE_SYSTEM
    assert "Do NOT add anything from your own knowledge" in GUIDE_SYSTEM


def test_rag_prompt_keeps_the_grounding_rule() -> None:
    """The two sentences ``runpod/handler.py`` had already lost."""
    assert "ONLY the provided source passages" in RAG_SYSTEM
    assert "Do NOT use any prior knowledge" in RAG_SYSTEM
    assert "Never contradict or override" in RAG_SYSTEM


def _synth_max_k(relative: str) -> int:
    """Read a handler's ``SYNTH_MAX_K`` default out of its source.

    Parsed rather than imported on purpose. ``serve/handler.py`` imports
    ``runpod``, an optional dependency absent from the dev environment and
    from CI, and these tests exist precisely because they need no runtime --
    no toolchain, no corpus, no device, no optional extras.

    :param relative: Repo-relative path to a handler module.
    :returns: The integer default.
    """
    source = (REPO / relative).read_text(encoding="utf-8")
    match = re.search(r'SYNTH_MAX_K = int\(os\.environ\.get\("SYNTH_MAX_K", "(\d+)"\)\)', source)
    assert match, f"SYNTH_MAX_K default not found in {relative}"
    return int(match.group(1))


def test_worker_budget_matches_synth_max_k() -> None:
    """Swift's worker-parity budget still equals the workers' ``SYNTH_MAX_K``.

    The Swift constant is a hand-written mirror of a Python one, so this is
    the check that turns a stale comment into a failure.
    """
    budget = BUDGET_SWIFT.read_text(encoding="utf-8")
    match = re.search(r"static let worker = Budget\((.*?)\)", budget, re.S)
    assert match, "Budget.worker not found in ContextBudgeter.swift"
    max_passages = re.search(r"maxPassages:\s*(\d+)", match.group(1))
    assert max_passages, "Budget.worker has no maxPassages"

    expected = _synth_max_k("src/gutenberg_kg/serve/handler.py")
    assert int(max_passages.group(1)) == expected, (
        f"Budget.worker.maxPassages={max_passages.group(1)} but "
        f"SYNTH_MAX_K={expected}. The Swift mirror is stale."
    )


def test_both_handlers_agree_on_synth_max_k() -> None:
    """The local worker and the RunPod worker feed the model the same amount."""
    assert _synth_max_k("runpod/handler.py") == _synth_max_k("src/gutenberg_kg/serve/handler.py")


def test_no_handler_inlines_its_own_rag_prompt() -> None:
    """A fourth copy of the prompt is how the RunPod drift happened.

    Both handlers must reach the text through ``synthesis_prompts``; an
    inlined "You are a literary guide…" string is the exact shape of the bug
    this module was written to end.
    """
    for relative in ("runpod/handler.py", "src/gutenberg_kg/serve/handler.py"):
        source = (REPO / relative).read_text(encoding="utf-8")
        body = "\n".join(line for line in source.split("\n") if not line.lstrip().startswith("#"))
        assert "You are a literary guide" not in body, (
            f"{relative} inlines a system prompt. Import it from "
            f"gutenberg_kg.synthesis_prompts instead."
        )


def test_passage_header_separator_is_shared() -> None:
    """Swift, the workers and ``_text.py`` all build the same header shape."""
    assert HEADER_SEPARATOR == " · "
    budget = BUDGET_SWIFT.read_text(encoding="utf-8")
    assert '" · "' in budget or "·" in budget, "ContextBudgeter no longer joins headers with ' · '"
