# Handoff: IA Integration & "The Knowledge Press" Re-framing

**Date:** 2026-05-03
**Author:** Eric G. Suchanek, PhD
**Status:** Ready to execute

---

## Context

GutenbergKG began as a Project Gutenberg corpus tool. It has grown into something larger: a
proof-of-concept for Structurally-Grounded Synthetic Intelligence (see `MANIFESTO.md`). The
`audel_kg/` sub-project already proves we can pull books from the Internet Archive, convert them
to DocKG-compatible Markdown, and ingest them with no changes to the core pipeline. IA is not a
new adapter — it is a second *source* feeding the same graph engine.

The goal of this handoff is two things:

1. **Re-frame**: GutenbergKG becomes "The Knowledge Press" — a universal ingestion engine for
   digitized text, just as the Gutenberg press was a universal production engine for books. Any
   source of structured text (Project Gutenberg, Internet Archive, local files) can be fed in;
   one queryable knowledge graph comes out.

2. **Fold IA in**: Promote the working IA downloader from `audel_kg/scripts/download_ia.py` into
   the main `gutenberg_kg` package as a first-class source alongside `download_gutenberg.py`.

---

## Current State

| Component | Location | Status |
|---|---|---|
| Gutenberg downloader | `scripts/download_gutenberg.py` | Production-ready |
| IA downloader | `audel_kg/scripts/download_ia.py` | Works; isolated sub-project |
| CLI download group | `src/gutenberg_kg/cli/cmd_download.py` | Gutenberg-only |
| Source abstraction | — | Does not exist yet |
| MANIFESTO.md | repo root | Written for Gutenberg only; needs broadening |
| README.md | repo root | Gutenberg-focused |
| `pyproject.toml` description | repo root | "CLI for Project Gutenberg knowledge graphs" |

The `audel_kg/scripts/download_ia.py` script is self-contained and production-quality. It
handles IA search, single-item download, catalog batch download, OCR artifact cleanup, ligature
normalization, Q&A pair elevation, and a `reference.md` metadata sidecar. It outputs directly
into `corpus/<genre>/<Title>/` exactly as the Gutenberg downloader does — making both sources
fully interchangeable downstream.

---

## What to Build

### 1. Promote the IA downloader into the main package

Move `audel_kg/scripts/download_ia.py` → `scripts/download_ia.py` (repo root `scripts/`,
alongside `download_gutenberg.py`). No code changes needed — the script already uses
`REPO_ROOT = Path(__file__).resolve().parent.parent`.

Delete `audel_kg/scripts/download_ia.py` and update `audel_kg/scripts/ingest.py` to import
from the promoted location if needed.

### 2. Add `ia` subgroup to the CLI

Add `src/gutenberg_kg/cli/cmd_ia.py` mirroring the structure of `cmd_download.py` but
delegating to `download_ia.py`. Expose the same surface:

```
gutenkg ia search <query>
gutenkg ia download <identifier> --genre <genre> [--title ...] [--force] [--dry-run]
gutenkg ia catalog <catalog_file> --genre <genre> [--force] [--dry-run]
gutenkg ia survey [--genre <genre>]
```

Register the group in `src/gutenberg_kg/cli/main.py` the same way `download_group` is
registered.

### 3. Extend `ALL_GENRES` in `cli/options.py`

`audel_kg` uses `"audel-electric"` as a genre. Add it (and any other IA-sourced genres) to
`ALL_GENRES` in `src/gutenberg_kg/cli/options.py` so both CLI groups share the same valid
choices. Long-term, genres should probably be discovered from `corpus/` at runtime rather than
hard-coded — but that is a separate cleanup.

### 4. Update identity strings

| File | Change |
|---|---|
| `pyproject.toml` | `description = "The Knowledge Press — universal ingestion engine for digitized text corpora"` |
| `pyproject.toml` | Add `"internet-archive"` and `"knowledge-press"` to `keywords` |
| `README.md` | Lead section: re-frame as "The Knowledge Press"; add IA as a supported source |
| `MANIFESTO.md` | Broaden the "GutenbergKG Proof of Concept" section to name IA as a second source; update the vision paragraph |

### 5. (Optional) Add `audel-electric` corpus to the brands/color palette

The `audel_kg` sub-project is a domain corpus (electrical manuals), not a distinct KG adapter.
Document it in `CHEATSHEET.md` as an example IA-sourced corpus, not in `brands.md`.

---

## What NOT to Do

- **Do not create a new KG adapter class** for IA. The existing DocKG ingestion pipeline
  handles everything already. IA is a *source*, not a schema.
- **Do not move `audel_kg/` out of the repo** or dissolve it yet — it contains corpus files
  (`audel_kg/corpus/`), a separate `pyproject.toml`, and catalog definitions. Promote just the
  downloader script; leave the rest in place until the corpus is fully migrated to `corpus/`.
- **Do not change the DocKG build pipeline** — `gutenkg ingest` and `dockg build` work for
  both sources today without modification.

---

## Ordered Task List

1. `cp audel_kg/scripts/download_ia.py scripts/download_ia.py` — promote script
2. Verify `REPO_ROOT` path still resolves correctly from `scripts/` (it will — same parent)
3. Create `src/gutenberg_kg/cli/cmd_ia.py` — mirror of `cmd_download.py` delegating to `download_ia`
4. Register `ia_group` in `src/gutenberg_kg/cli/main.py`
5. Add `"audel-electric"` to `ALL_GENRES` in `cli/options.py`
6. Update `pyproject.toml` description and keywords
7. Update `README.md` lead section — one paragraph on "The Knowledge Press" framing + IA as source
8. Update `MANIFESTO.md` — broaden "GutenbergKG Proof of Concept" section
9. Run `gutenkg ia survey` and `gutenkg ia search "audel"` to smoke-test the new CLI group
10. Run `gutenkg ingest` on a small IA-sourced book to confirm end-to-end pipeline

---

## Acceptance Criteria

- [ ] `gutenkg ia download <identifier> --genre audel-electric` works from repo root
- [ ] `gutenkg ia survey` shows the existing `audel_kg/corpus/audel-electric/` books
- [ ] `gutenkg download book 1342` (Gutenberg) still works unchanged
- [ ] `pyproject.toml` description reads "The Knowledge Press…"
- [ ] No new adapter class, no schema changes, no DocKG pipeline changes

---

## Brand Note

The GutenbergKG logo (emerald `#2ECC71`, movable-type "G" ghosted in the brain) does not need
to change. "The Knowledge Press" is a subtitle/re-framing, not a rename. The logo prompt in
`assets/brands.md` can optionally gain the subtitle line — change "GutenbergKG" wordmark
description to `"GutenbergKG / The Knowledge Press"` — but that is cosmetic.
