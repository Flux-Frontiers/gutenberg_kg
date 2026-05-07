# Gutenberg Provenance Verifier — Handoff

**Date:** 2026-05-06
**Task:** Mechanized 8-word substring verifier for the frontier model provenance experiment
**Source:** `/Users/egs/repos/kgrag_priv/` — results at `analysis/frontier_comparison_results.md`

---

## What Needs Doing

The frontier model comparison experiment (`kgrag_priv/analysis/frontier_comparison_results.md`) was hand-scored against memory of canonical translations. The doc says explicitly:

> *"The mechanized substring-against-Gutenberg verifier from the experiment appendix has not been run yet — these numbers are best-effort estimates pending that script."*

Write and run the verifier. Update the results doc with mechanized verdicts. The spec is in `kgrag_priv/docs/experiment_frontier_comparison.md` under **Appendix: Suggested Verifier Workflow**.

---

## Verifier Rule

For each quotation claimed as direct:

1. Take the first 8 words of the quoted text.
2. Search the full corpus text of the cited work (case-insensitive, punctuation-normalised).
3. Verdict:
   - **VERIFIED** — 8-word substring found anywhere in the work
   - **MISLOCATED** — found, but not within ±200 chars of the cited location (chapter/section marker)
   - **HALLUCINATED** — not found anywhere in the work
   - **UNVERIFIABLE** — cited work not in corpus (flag for download)

Put the script at `scripts/provenance_verifier.py`. Run it against all essays. Write verdicts back into `kgrag_priv/analysis/frontier_comparison_results.md` as a new **Mechanized Verdicts** section.

---

## Corpus Paths

All texts are in `/Users/egs/repos/gutenberg_kg/corpus/`. The relevant files:

| Work | Corpus path |
|---|---|
| Marcus Aurelius *Meditations* | `corpus/ancient-classical/Meditations/meditations.md` |
| Epictetus *Enchiridion* | `corpus/ancient-classical/A Selection from the Discourses of Epictetus with the Encheiridion/a_selection_from_the_discourses_of_epictetus_with_the_encheiridion.md` |
| Tolstoy *Anna Karenina* | `corpus/russian-literature/Anna Karenina/anna_karenina.md` |
| Dostoevsky *Crime and Punishment* | `corpus/russian-literature/Crime and Punishment/crime_and_punishment.md` |
| Dostoevsky *Brothers Karamazov* | `corpus/russian-literature/The Brothers Karamazov/the_brothers_karamazov.md` |
| Dostoevsky *Notes from Underground* | `corpus/russian-literature/Notes from Underground (Dostoevsky)/notes_from_underground_(dostoevsky).md` |
| Tolstoy *War and Peace* | `corpus/russian-literature/War and Peace/war_and_peace.md` |
| Nietzsche *Beyond Good and Evil* | `corpus/philosophy/Beyond Good and Evil/beyond_good_and_evil.md` |
| Nietzsche *Thus Spake Zarathustra* | `corpus/philosophy/Thus Spake Zarathustra/thus_spake_zarathustra.md` |

**Not in corpus — download first or mark UNVERIFIABLE:**
- Seneca *Letters* (any letter, incl. Letter 13)
- Seneca *On Providence* (*De Providentia*)
- Tolstoy *Death of Ivan Ilyich*
- Nietzsche *Twilight of the Idols* (only Zarathustra and BGE are present)

Use `gutenkg download` to fetch missing texts if the Gutenberg IDs are known:
- *Death of Ivan Ilyich*: Gutenberg #600 (part of short stories collection) — check catalog
- Seneca *Letters*: Gutenberg #700 or similar — check `scripts/catalogs/`
- Seneca *On Providence*: may need manual download
- *Twilight of the Idols*: Gutenberg #52263

---

## Essays to Verify

Eight essays in `/Users/egs/repos/kgrag_priv/analysis/`:

**Honest-mode (with `[UNCERTAIN WORDING]` scaffolding):**
- `chatgpt-5.4_stoics_vs_russian_novelists_essay.md`
- `gpt-5.4_stoics_vs_russian_novelists_suffering_redemption.md`
- `stoics_vs_russian_novelists_gemini_3.1_pro.md`
- `stoics_vs_russian_novelists_suffering_redemption_opus4.7.md`

**Naive-mode (no scaffolding):**
- `chat-gpt5.4_naive_russians.md`
- `claude-sonnet-4-6_naive_russians.md`
- `gemini_3.1_pro_naive_russians.md`
- `opus4.7_naive_russians.md`

Only verify quotations the model offered as **direct** (unflagged, or flagged with `[UNCERTAIN WORDING]` but still presented as a real quote). Skip passages explicitly marked `[PARAPHRASE]`.

---

## Known Expected Verdicts (from hand-scoring — verify mechanically)

| Quote (first ~8 words) | Model | Work | Expected |
|---|---|---|---|
| "All happy families are alike; each unhappy family" | all | Anna Karenina | VERIFIED |
| "Some things are in our control and others not" | Gemini/Opus | Enchiridion | VERIFIED |
| "Love in action is a harsh and dreadful thing" | Sonnet naive | Brothers K | VERIFIED |
| "Every one of us has sinned against all men" | Opus naive | Brothers K | VERIFIED |
| "Choose not to be harmed—and you won't feel harmed" | Gemini naive | Meditations | VERIFIED |
| "Pain and suffering are always inevitable for a large" | Sonnet naive | C&P | VERIFIED |
| "If you are distressed by anything external, it is" | ChatGPT | Meditations | EXPECTED FAIL — paraphrase |
| "You have power over your mind, not outside events" | Sonnet naive | Meditations | EXPECTED FAIL — internet paraphrase |
| "Very little is needed to make a happy life" | ChatGPT naive | Meditations | EXPECTED FAIL — hallucination |
| "It is not that I am brave, but that" | Sonnet naive | On Providence | EXPECTED FAIL — fabricated |
| "He who has a why to live for can" | Opus honest | Twilight | UNVERIFIABLE (not in corpus) |
| "Fire tests gold, and misfortune brave men" | Opus naive | On Providence | UNVERIFIABLE (Seneca not in corpus) |

---

## Output

After running the verifier, add a **Mechanized Verdicts** section to `kgrag_priv/analysis/frontier_comparison_results.md` with:

1. A table: `| Quote | Model | Work | Verdict | Notes |`
2. Updated headline metrics correcting any hand-scored counts that shift
3. A note on which works were UNVERIFIABLE and what download would fix it

The results doc already has a "Methodological Caveats" section calling this out — replace caveat #1 with the mechanized results once done.

---

## Suggested Script Structure

```python
# scripts/provenance_verifier.py
# Usage: python scripts/provenance_verifier.py
import re, json
from pathlib import Path

CORPUS_ROOT = Path("/Users/egs/repos/gutenberg_kg/corpus")
ESSAYS_ROOT = Path("/Users/egs/repos/kgrag_priv/analysis")

def normalize(text):
    return re.sub(r"[^\w\s]", "", text.lower())

def first_n_words(quote, n=8):
    return " ".join(normalize(quote).split()[:n])

def search_corpus(corpus_file: Path, first_8: str) -> tuple[bool, int | None]:
    text = normalize(corpus_file.read_text(encoding="utf-8", errors="ignore"))
    idx = text.find(first_8)
    return (idx != -1, idx if idx != -1 else None)

# Define citations: (quote, work_path, citation_hint, model, mode)
CITATIONS = [
    # ... populate from essays
]

for quote, work_path, hint, model, mode in CITATIONS:
    if not work_path.exists():
        verdict = "UNVERIFIABLE"
    else:
        found, idx = search_corpus(work_path, first_n_words(quote))
        if not found:
            verdict = "HALLUCINATED"
        elif hint and not near(idx, hint, work_path):
            verdict = "MISLOCATED"
        else:
            verdict = "VERIFIED"
    print(f"{verdict:15} | {model:20} | {quote[:60]}")
```

The hard part is extracting the citation list from the essays — do that by reading each essay and pulling out quoted passages (text in `"..."` or preceded by a citation marker). The results doc already has most of them enumerated in the per-model sections.
