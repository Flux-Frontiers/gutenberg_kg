# Release Notes — v1.5.0

> Released: 2026-06-08

## Highlights

### Image Generation: HTTP-First Architecture

`gutenkg imagine` now requires an HTTP endpoint (`--endpoint` or `GUTENKG_IMAGE_ENDPOINT`).
The `imagine-local` extra and all `mflux` / Apple-Silicon-only dependencies have been
removed — they were incompatible with the KG embeddings `transformers<4.57` pin. Run
`mflux-serve` locally or point at any compatible image server; the CLI is otherwise unchanged.

Multi-provider synthesis is now available in the chat UI (oMLX / Ollama / OpenAI), with
per-request backend routing and a timing display showing search, synthesis, VLM rewrite,
and image generation latency.

### Corpus Integrity: 8 Books Repaired

Eight books in the corpus contained completely wrong text due to incorrect Gutenberg IDs in
the catalog files. The bad downloads had gone undetected because only `reference.md` metadata
was obviously wrong — the text files silently held entirely different works:

| Book | Was actually |
|---|---|
| Flatland (Abbott) | Alice's Adventures in Wonderland |
| A Princess of Mars (Burroughs) | The Night Land (Hodgson) |
| At the Earth's Core (Burroughs) | A Princess of Mars (wrong ID cascade) |
| The First Men in the Moon (Wells) | Journey to the Centre of the Earth (Verne) |
| The Food of the Gods (Wells) | Ion (Plato) |
| The Sea-Wolf (London) | La Dame aux Camélias (Dumas fils) |
| Germinal (Zola) | Insectivorous Plants (Darwin) |
| On the Eve (Turgenev) | Mr. Punch's History of the Great War |

All 5 affected catalog files corrected; books re-downloaded and re-ingested.

### Corpus Expansion: 249 Books across 19 Genres

42 new texts across 5 genres added (biography, drama, letters, natural-history, travel);
4 diary books given proper `reference.md` metadata. `scripts/regenerate_corpus_doc.py`
added to keep `docs/CORPUS.md` in sync automatically.

### Docker & RunPod

Standalone Docker image bakes the full corpus bundle for cold-start-free deployment.
RunPod handler gains `corpus` routing, `op=models`, `HANDLER_SECRET` auth, per-request
synthesis model override, and timing fields. Chat UI adds provider selection, global
image resolution control, and sidebar-based save/render.

## Breaking Changes

- `gutenkg imagine` **requires** `--endpoint` or `GUTENKG_IMAGE_ENDPOINT` — local
  Apple Silicon generation no longer available via the CLI.
- `pip install gutenberg-kg[imagine-local]` is no longer valid; use `[imagine]`.

## Dependency Changes

- `kg-rag` moved from GitHub source to PyPI (`>=0.9.1`)
- `kgmodule-utils[synthesis]` bumped to `>=0.4.2`
- `rich` promoted to a core dependency
- `doc-kg` minimum raised to `0.15.5`

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
