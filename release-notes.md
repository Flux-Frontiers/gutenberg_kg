# Release Notes — v1.5.0

> Released: 2026-06-08

## Corpus-Grounded Image Generation

GutenbergKG can now generate images directly from the corpus. The `gutenkg imagine`
command retrieves relevant passages, rewrites them into a visual scene description via
a local VLM, and passes the result to a FLUX.2-Klein image server — all in one command.

```bash
# Direct prompt
gutenkg imagine "the great fire of London at night, oil painting"

# Corpus-grounded: retrieve from Pepys' diary, rewrite with VLM, generate
gutenkg imagine --query "great fire" --book pepys --ratio 16:9

# Skip the VLM rewrite and pass corpus text straight to FLUX
gutenkg imagine --query "great fire" --book pepys --no-vlm

# Print the retrieved + rewritten prompt without generating
gutenkg imagine --query "great fire" --book pepys --corpus-only
```

Image generation is now **HTTP-first**: point `--endpoint` (or `GUTENKG_IMAGE_ENDPOINT`)
at any running `mflux-serve` instance. Aspect ratio (`1:1`, `3:2`, `16:9`, etc.),
inference steps, seed, and output path are all configurable.

> **Breaking change:** the `imagine-local` extra is removed. Local Apple Silicon generation
> was incompatible with the KG embeddings `transformers<4.57` pin. Use `mflux-serve` over
> HTTP instead — same model, no dependency conflict.

---

## Multi-Provider LLM Synthesis

The chat UI now supports three synthesis backends selectable at runtime — no restart needed:

| Backend | When to use |
|---|---|
| **oMLX** | Apple Silicon, sub-second local inference |
| **Ollama** | Cross-platform local inference, GPU or CPU |
| **OpenAI** | Cloud fallback, maximal quality |

The selected backend is forwarded to the worker on every `query`, `rewrite`, and `imagine`
call. Per-request model override is also supported in the RunPod handler.

---

## Configurable Inference Steps & Image Resolution

Two new controls let you trade quality for speed on every request:

- **`IMAGE_STEPS` env var** — sets default inference steps across the worker, image server,
  and chat UI. `4` is fast/preview; `25` gives noticeably better detail.
- **Resolution tiers in the chat sidebar** — Preview (768 × 512), Standard (1152 × 768),
  Full (1536 × 1024). Applied globally to all image results in the session.

---

## Pipeline Timing Visibility

Every response now exposes latency at each stage: `search_ms`, `synthesis_ms`, VLM rewrite
time, and image generation time are shown in result captions. Bottlenecks are immediately
visible without digging into logs.

---

## Standalone Docker Deployment

A self-contained Docker image bakes the full 249-book corpus bundle so the worker starts
cold with no build step. The stack (`make up`) starts the KGRAG worker, FLUX image server,
and Streamlit chat UI in one command.

RunPod handler additions: `corpus` routing by genre, `op=models` introspection,
`HANDLER_SECRET` auth, and `SYNTH_MAX_K` cap to prevent context-window overflow.

---

## Corpus Integrity: 8 Books Repaired

Eight books contained completely wrong text due to incorrect Gutenberg IDs in the catalog
files — silently serving Alice in Wonderland as Flatland, Dumas as Jack London, Darwin as
Zola. All catalog IDs corrected, books re-downloaded and re-ingested.

---

## Other Changes

- **249 books / 19 genres** — 42 texts added across biography, drama, letters,
  natural-history, and travel since v1.3.0
- **`scripts/regenerate_corpus_doc.py`** — keeps `docs/CORPUS.md` in sync with the corpus
- `kg-rag` moved from GitHub source to PyPI
- `rich` promoted to a core dependency
- `doc-kg` minimum raised to `0.15.5` (bounded SIMILAR_TO edges)

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
