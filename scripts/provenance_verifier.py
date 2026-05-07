#!/usr/bin/env python3
"""
scripts/provenance_verifier.py

Mechanized 8-word substring verifier for the frontier model provenance experiment.
Checks first 8 words of each quoted passage (case-insensitive, punctuation-normalised)
against Project Gutenberg corpus files.

Verdicts:
  VERIFIED      — 8-word probe found anywhere in the cited work
  HALLUCINATED  — probe not found in the cited work
  UNVERIFIABLE  — cited work not in corpus

Usage: python scripts/provenance_verifier.py
"""

import re
from dataclasses import dataclass
from pathlib import Path

CORPUS_ROOT = Path("/Users/egs/repos/gutenberg_kg/corpus")

# ── Corpus paths ──────────────────────────────────────────────────────────────

MEDITATIONS = CORPUS_ROOT / "ancient-classical/Meditations/meditations.md"
ENCHIRIDION = (
    CORPUS_ROOT
    / "ancient-classical"
    / "A Selection from the Discourses of Epictetus with the Encheiridion"
    / "a_selection_from_the_discourses_of_epictetus_with_the_encheiridion.md"
)
ANNA_K = CORPUS_ROOT / "russian-literature/Anna Karenina/anna_karenina.md"
CRIME_PUNISHMENT = CORPUS_ROOT / "russian-literature/Crime and Punishment/crime_and_punishment.md"
BROTHERS_K = CORPUS_ROOT / "russian-literature/The Brothers Karamazov/the_brothers_karamazov.md"
NOTES_UNDERGROUND = (
    CORPUS_ROOT
    / "russian-literature"
    / "Notes from Underground (Dostoevsky)"
    / "notes_from_underground_dostoevsky.md"
)
WAR_PEACE = CORPUS_ROOT / "russian-literature/War and Peace/war_and_peace.md"
BGE = CORPUS_ROOT / "philosophy/Beyond Good and Evil/beyond_good_and_evil.md"
ZARATHUSTRA = CORPUS_ROOT / "philosophy/Thus Spake Zarathustra/thus_spake_zarathustra.md"

# Not in corpus — citations against these will be UNVERIFIABLE
SENECA_LETTERS = None  # Seneca Letters to Lucilius — not on Gutenberg
SENECA_PROVIDENCE = (
    CORPUS_ROOT
    / "ancient-classical"
    / "Minor Dialogues, Together With the Dialogue on Clemency"
    / "minor_dialogues_together_with_the_dialogue_on_clemency.md"
)  # Stewart trans — contains "Of Providence" (De Providentia)
DEATH_IVAN_ILYICH = None  # Tolstoy Death of Ivan Ilyich — not on Gutenberg in English
TWILIGHT_IDOLS = (
    CORPUS_ROOT
    / "philosophy"
    / "The Twilight of the Idols; or, How to Philosophize with the Hammer. The Antichrist"
    / "the_twilight_of_the_idols_or_how_to_philosophize_with_the_hammer_the_antichrist.md"
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def normalize(text: str) -> str:
    text = re.sub(r"[^\w\s]", "", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def first_n_words(text: str, n: int = 8) -> str:
    return " ".join(normalize(text).split()[:n])


_corpus_cache: dict[Path, str] = {}


def load_corpus(path: Path) -> str:
    if path not in _corpus_cache:
        _corpus_cache[path] = normalize(path.read_text(encoding="utf-8", errors="ignore"))
    return _corpus_cache[path]


def search_corpus(path: Path, probe: str) -> tuple[bool, int | None]:
    text = load_corpus(path)
    idx = text.find(probe)
    return (idx != -1, idx if idx != -1 else None)


# ── Citation dataclass ────────────────────────────────────────────────────────


@dataclass
class Citation:
    quote: str
    work_path: "Path | None"
    model: str
    mode: str  # "honest" | "naive"
    label: str  # short citation label, e.g. "MA Meditations 8.47"


def verify(c: Citation) -> tuple[str, str]:
    """Return (verdict, note)."""
    if c.work_path is None:
        return "UNVERIFIABLE", "cited work not in corpus"
    if not c.work_path.exists():
        return "UNVERIFIABLE", f"corpus file not found: {c.work_path.name}"
    probe = first_n_words(c.quote)
    if not probe:
        return "UNVERIFIABLE", "empty probe after normalisation"
    found, idx = search_corpus(c.work_path, probe)
    if found:
        short = c.work_path.name[:40]
        return "VERIFIED", f"pos {idx:,} in {short}"
    return "HALLUCINATED", f'8-word probe not found: "{probe}"'


# ── Citation list ─────────────────────────────────────────────────────────────

CITATIONS: list[Citation] = [
    # ══════════════════════════════════════════════════════════════════════════
    # HONEST MODE
    # ══════════════════════════════════════════════════════════════════════════
    # ── chatgpt-5.4 honest ────────────────────────────────────────────────────
    Citation(
        "If you are distressed by anything external, the pain is not due to the thing itself, "
        "but to your estimate of it; and this you have the power to revoke at any moment.",
        MEDITATIONS,
        "ChatGPT-5.4",
        "honest",
        "MA Meditations 8 [UW]",
    ),
    Citation(
        "Some things are within our control and others are not.",
        ENCHIRIDION,
        "ChatGPT-5.4",
        "honest",
        "Epictetus Ench §1",
    ),
    Citation(
        "We suffer more often in imagination than in reality.",
        SENECA_LETTERS,
        "ChatGPT-5.4",
        "honest",
        "Seneca Letters 13",
    ),
    Citation(
        "All happy families are alike; each unhappy family is unhappy in its own way.",
        ANNA_K,
        "ChatGPT-5.4",
        "honest",
        "AK opening",
    ),
    Citation(
        "Pain and suffering are always inevitable for a large intelligence and a deep heart.",
        CRIME_PUNISHMENT,
        "ChatGPT-5.4",
        "honest",
        "C&P [UW]",
    ),
    Citation(
        "I accept God, I accept, but I most respectfully return him the ticket.",
        BROTHERS_K,
        "ChatGPT-5.4",
        "honest",
        "BK Book V [UW]",
    ),
    Citation(
        "You have power over your mind—not outside events. Realize this, and you will find strength.",
        MEDITATIONS,
        "ChatGPT-5.4",
        "honest",
        "MA Meditations [UW]",
    ),
    # ── gpt-5.4 honest ────────────────────────────────────────────────────────
    Citation(
        "Men are disturbed not by things, but by the views which they take of them.",
        ENCHIRIDION,
        "GPT-5.4",
        "honest",
        "Epictetus Ench §5",
    ),
    Citation(
        "If thou art pained by any external thing, it is not this thing that disturbs thee, "
        "but thy judgment about it. And it is in thy power to wipe out this judgment now.",
        MEDITATIONS,
        "GPT-5.4",
        "honest",
        "MA Meditations 8.47 [UW]",
    ),
    Citation(
        "We suffer more often in imagination than in reality.",
        SENECA_LETTERS,
        "GPT-5.4",
        "honest",
        "Seneca Letters 13 [UW]",
    ),
    Citation(
        "Pain and suffering are always inevitable for a large intelligence and a deep heart.",
        CRIME_PUNISHMENT,
        "GPT-5.4",
        "honest",
        "C&P Part IV Ch4 [UW]",
    ),
    Citation(
        "Each of us is responsible to all men for all men and for everything.",
        BROTHERS_K,
        "GPT-5.4",
        "honest",
        "BK Book VI Ch3 [UW]",
    ),
    Citation(
        "All happy families are alike; each unhappy family is unhappy in its own way.",
        ANNA_K,
        "GPT-5.4",
        "honest",
        "AK Part 1 Ch1",
    ),
    Citation(
        "Death is finished... it is no more.",
        DEATH_IVAN_ILYICH,
        "GPT-5.4",
        "honest",
        "Ivan Ilyich Ch12 [UW]",
    ),
    # ── gemini 3.1 pro honest ─────────────────────────────────────────────────
    Citation(
        "Men are disturbed, not by things, but by the principles and notions which they form concerning things.",
        ENCHIRIDION,
        "Gemini 3.1 Pro",
        "honest",
        "Epictetus Ench §5",
    ),
    Citation(
        "If you are distressed by anything external, the pain is not due to the thing itself, "
        "but to your estimate of it; and this you have the power to revoke at any moment.",
        MEDITATIONS,
        "Gemini 3.1 Pro",
        "honest",
        "MA Meditations 8.47 [UW]",
    ),
    Citation(
        "Pain and suffering are always inevitable for a large intelligence and a deep heart. "
        "The really great men must, I think, have great sadness on earth.",
        CRIME_PUNISHMENT,
        "Gemini 3.1 Pro",
        "honest",
        "C&P Part 6 Ch6 [UW]",
    ),
    # [PARAPHRASE] "We are each responsible to all for all." — SKIPPED per rubric
    Citation(
        "All happy families resemble one another; every unhappy family is unhappy in its own way.",
        ANNA_K,
        "Gemini 3.1 Pro",
        "honest",
        "AK Part 1 Ch1",
    ),
    Citation(
        "In place of death there was light.",
        DEATH_IVAN_ILYICH,
        "Gemini 3.1 Pro",
        "honest",
        "Ivan Ilyich Ch12 [UW]",
    ),
    # ── opus 4.7 honest ───────────────────────────────────────────────────────
    Citation(
        "Men are disturbed not by the things which happen, but by the opinions about the things.",
        ENCHIRIDION,
        "Opus 4.7",
        "honest",
        "Epictetus Ench §5",
    ),
    Citation(
        "Begin the morning by saying to thyself, I shall meet with the busybody, "
        "the ungrateful, arrogant, deceitful, envious, unsocial.",
        MEDITATIONS,
        "Opus 4.7",
        "honest",
        "MA Meditations II.1 (approx)",
    ),
    # [PARAPHRASE] "our life is what our thoughts make it" — SKIPPED per rubric
    Citation(
        "We suffer more often in imagination than in reality.",
        SENECA_LETTERS,
        "Opus 4.7",
        "honest",
        "Seneca Letters [UW]",
    ),
    Citation(
        "Ivan Ilyich's life had been most simple and most ordinary and therefore most terrible.",
        DEATH_IVAN_ILYICH,
        "Opus 4.7",
        "honest",
        "Ivan Ilyich Ch2 (approx)",
    ),
    # [PARAPHRASE] "Each of us is guilty before everyone, for everyone, and I more than the others." — SKIPPED
    Citation(
        "What is hell? I maintain that it is the suffering of being unable to love.",
        BROTHERS_K,
        "Opus 4.7",
        "honest",
        "BK Book VI [UW]",
    ),
    Citation(
        "I am a sick man.... I am a spiteful man. I am an unattractive man.",
        NOTES_UNDERGROUND,
        "Opus 4.7",
        "honest",
        "Notes Underground opening",
    ),
    Citation(
        "What does not kill me makes me stronger.",
        TWILIGHT_IDOLS,
        "Opus 4.7",
        "honest",
        "Nietzsche Twilight §8",
    ),
    Citation(
        "He who has a why to live can bear almost any how.",
        TWILIGHT_IDOLS,
        "Opus 4.7",
        "honest",
        "Nietzsche Twilight (section uncertain)",
    ),
    # ══════════════════════════════════════════════════════════════════════════
    # NAIVE MODE
    # ══════════════════════════════════════════════════════════════════════════
    # ── chatgpt-5.4 naive ─────────────────────────────────────────────────────
    Citation(
        "If you are distressed by anything external, the pain is not due to the thing itself, "
        "but to your estimate of it",
        MEDITATIONS,
        "ChatGPT-5.4",
        "naive",
        "MA Meditations 8.47",
    ),
    Citation(
        "Men are disturbed not by things, but by the views which they take of things.",
        ENCHIRIDION,
        "ChatGPT-5.4",
        "naive",
        "Epictetus Ench §5",
    ),
    Citation(
        "Fire tests gold, suffering tests brave men.",
        SENECA_PROVIDENCE,
        "ChatGPT-5.4",
        "naive",
        "Seneca On Providence Ch5",
    ),
    Citation(
        "Suffering is the sole origin of consciousness.",
        NOTES_UNDERGROUND,
        "ChatGPT-5.4",
        "naive",
        "Notes Underground Part I Ch2",
    ),
    Citation(
        "Go at once, this very minute, stand at the crossroads, bow down, first kiss the earth "
        "which you have desecrated, and then bow to the whole world.",
        CRIME_PUNISHMENT,
        "ChatGPT-5.4",
        "naive",
        "C&P Part V Ch4",
    ),
    Citation(
        "Each of us is guilty before everyone for everyone.",
        BROTHERS_K,
        "ChatGPT-5.4",
        "naive",
        "BK Book 6 Ch3",
    ),
    Citation(
        "In place of death there was light.",
        DEATH_IVAN_ILYICH,
        "ChatGPT-5.4",
        "naive",
        "Ivan Ilyich Ch12",
    ),
    Citation(
        "Very little is needed to make a happy life; it is all within yourself.",
        MEDITATIONS,
        "ChatGPT-5.4",
        "naive",
        "MA Meditations 7.67 [expected FAIL]",
    ),
    Citation(
        "You desire to live 'according to Nature'? Oh, you noble Stoics, what fraud of words!",
        BGE,
        "ChatGPT-5.4",
        "naive",
        "Nietzsche BGE Part I §9",
    ),
    # ── sonnet 4.6 naive ──────────────────────────────────────────────────────
    Citation(
        "Of things, some are in our power and some are not. In our power are opinion, pursuit, "
        "desire, aversion—in a word, whatever are our own actions.",
        ENCHIRIDION,
        "Sonnet 4.6",
        "naive",
        "Epictetus Ench §1",
    ),
    Citation(
        "You have power over your mind, not outside events. Realize this, and you will find strength.",
        MEDITATIONS,
        "Sonnet 4.6",
        "naive",
        "MA Meditations Book VI [expected FAIL]",
    ),
    Citation(
        "Loss is nothing else but change, and change is Nature's delight.",
        MEDITATIONS,
        "Sonnet 4.6",
        "naive",
        "MA Meditations IX.35",
    ),
    Citation(
        "It is not that I am brave, but that I know what is mine to lose.",
        SENECA_PROVIDENCE,
        "Sonnet 4.6",
        "naive",
        "Seneca On Providence [expected FAIL - fabricated]",
    ),
    Citation(
        "If everyone must suffer to pay for the eternal harmony, what have children got to do with it?",
        BROTHERS_K,
        "Sonnet 4.6",
        "naive",
        "BK Book V Ch4 (Rebellion)",
    ),
    Citation(
        "Love in action is a harsh and dreadful thing compared with love in dreams",
        BROTHERS_K,
        "Sonnet 4.6",
        "naive",
        "BK Book II Ch4",
    ),
    Citation(
        "What tormented Ivan Ilyich most was the deception, the lie, which for some reason "
        "they all accepted, that he was not dying but was simply ill, and that he only need "
        "keep quiet and undergo treatment and then something very good would result.",
        DEATH_IVAN_ILYICH,
        "Sonnet 4.6",
        "naive",
        "Ivan Ilyich Ch7",
    ),
    Citation(
        "In Gerasim alone Ivan Ilyich found no falseness; he alone did not consider it "
        "necessary to cover up what was uncovered.",
        DEATH_IVAN_ILYICH,
        "Sonnet 4.6",
        "naive",
        "Ivan Ilyich Ch9",
    ),
    # ── gemini 3.1 pro naive ──────────────────────────────────────────────────
    Citation(
        "Choose not to be harmed—and you won't feel harmed. Don't feel harmed—and you haven't been.",
        MEDITATIONS,
        "Gemini 3.1 Pro",
        "naive",
        "MA Meditations 4.7",
    ),
    Citation(
        "Disaster is virtue's opportunity.",
        SENECA_PROVIDENCE,
        "Gemini 3.1 Pro",
        "naive",
        "Seneca On Providence Ch4",
    ),
    Citation(
        "They wanted to speak, but could not; tears stood in their eyes. They were both pale "
        "and thin; but those sick pale faces were bright with the dawn of a new future, of a "
        "full resurrection into a new life. They were renewed by love; the heart of each held "
        "infinite sources of life for the heart of the other.",
        CRIME_PUNISHMENT,
        "Gemini 3.1 Pro",
        "naive",
        "C&P Epilogue Ch2",
    ),
    Citation(
        "Love a man even in his sin, for that is the semblance of Divine Love and is the highest love on earth.",
        BROTHERS_K,
        "Gemini 3.1 Pro",
        "naive",
        "BK Book 6 Ch3",
    ),
    Citation(
        "And suddenly it grew clear to him that what had been oppressing him and would not "
        "leave him was all dropping away at once from two sides, from ten sides, and from all sides.",
        DEATH_IVAN_ILYICH,
        "Gemini 3.1 Pro",
        "naive",
        "Ivan Ilyich Ch12",
    ),
    # ── opus 4.7 naive ────────────────────────────────────────────────────────
    Citation(
        "Men are disturbed not by the things which happen, but by the opinions about the things.",
        ENCHIRIDION,
        "Opus 4.7",
        "naive",
        "Epictetus Ench §5",
    ),
    Citation(
        "If you are pained by any external thing, it is not this thing that disturbs you, "
        "but your own judgment about it. And it is in your power to wipe out this judgment now.",
        MEDITATIONS,
        "Opus 4.7",
        "naive",
        "MA Meditations VIII.47",
    ),
    Citation(
        "The impediment to action advances action. What stands in the way becomes the way.",
        MEDITATIONS,
        "Opus 4.7",
        "naive",
        "MA Meditations V.20",
    ),
    Citation(
        "Fire tests gold, and misfortune brave men.",
        SENECA_PROVIDENCE,
        "Opus 4.7",
        "naive",
        "Seneca On Providence V.10",
    ),
    Citation(
        "No more roundabout discussions of what a good man should be. Be one.",
        MEDITATIONS,
        "Opus 4.7",
        "naive",
        "MA Meditations X.16",
    ),
    Citation(
        "Pain and suffering are always inevitable for a large intelligence and a deep heart. "
        "The really great men must, I think, have great sadness on earth.",
        CRIME_PUNISHMENT,
        "Opus 4.7",
        "naive",
        "C&P Part III Ch5",
    ),
    Citation(
        "What is hell? I maintain that it is the suffering of being unable to love.",
        BROTHERS_K,
        "Opus 4.7",
        "naive",
        "BK Book VI Ch3",
    ),
    Citation(
        "Every one of us has sinned against all men, and I more than any.",
        BROTHERS_K,
        "Opus 4.7",
        "naive",
        "BK Book VI Ch2",
    ),
    Citation(
        "What if my whole life has been wrong?",
        DEATH_IVAN_ILYICH,
        "Opus 4.7",
        "naive",
        "Ivan Ilyich Ch9",
    ),
    Citation(
        "He who has a why to live for can bear almost any how.",
        TWILIGHT_IDOLS,
        "Opus 4.7",
        "naive",
        "Nietzsche Twilight §12",
    ),
]


# ── Runner ────────────────────────────────────────────────────────────────────


def main() -> None:
    results = []
    for c in CITATIONS:
        verdict, note = verify(c)
        results.append((c, verdict, note))

    # ── Full table ────────────────────────────────────────────────────────────
    print("=" * 110)
    print(f"{'VERDICT':<14} {'MODEL':<16} {'MODE':<7} {'CITATION':<35} {'QUOTE (first 60 chars)'}")
    print("=" * 110)
    prev_mode = None
    for c, verdict, note in results:
        if prev_mode and c.mode != prev_mode:
            print()
        print(f"{verdict:<14} {c.model:<16} {c.mode:<7} {c.label:<35} {c.quote[:60]!r}")
        prev_mode = c.mode

    # ── Summary counts by model × mode ───────────────────────────────────────
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'MODEL':<20} {'MODE':<8} {'VERIF':>6} {'HALLU':>6} {'UNVER':>6} {'TOTAL':>6}")
    print("-" * 54)

    from collections import defaultdict

    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c, verdict, _ in results:
        counts[(c.model, c.mode)][verdict] += 1

    order = [
        ("ChatGPT-5.4", "honest"),
        ("GPT-5.4", "honest"),
        ("Gemini 3.1 Pro", "honest"),
        ("Opus 4.7", "honest"),
        ("ChatGPT-5.4", "naive"),
        ("Sonnet 4.6", "naive"),
        ("Gemini 3.1 Pro", "naive"),
        ("Opus 4.7", "naive"),
    ]
    for model, mode in order:
        d = counts.get((model, mode), {})
        v = d.get("VERIFIED", 0)
        h = d.get("HALLUCINATED", 0)
        u = d.get("UNVERIFIABLE", 0)
        total = v + h + u
        print(f"{model:<20} {mode:<8} {v:>6} {h:>6} {u:>6} {total:>6}")

    # ── UNVERIFIABLE works ────────────────────────────────────────────────────
    print("\nUNVERIFIABLE WORKS (not in corpus):")
    unver_works = set()
    for c, verdict, _ in results:
        if verdict == "UNVERIFIABLE" and c.work_path is None:
            unver_works.add(c.label.split()[0])  # rough label
    unver_labels = {c.label for c, v, _ in results if v == "UNVERIFIABLE" and c.work_path is None}
    for lbl in sorted(unver_labels):
        print(f"  {lbl}")

    # ── Markdown table for results doc ────────────────────────────────────────
    print("\n\n" + "=" * 110)
    print("MARKDOWN OUTPUT — paste into frontier_comparison_results.md")
    print("=" * 110)
    print()
    print("| Quote (first ~8 words) | Model | Mode | Citation | Verdict | Note |")
    print("|---|---|---|---|---|---|")
    for c, verdict, note in results:
        q8 = " ".join(c.quote.split()[:8]).rstrip(",;")
        print(f"| {q8}… | {c.model} | {c.mode} | {c.label} | **{verdict}** | {note} |")


if __name__ == "__main__":
    main()
