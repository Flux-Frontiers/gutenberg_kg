# GutenbergKG v1.0.1 — Bounded Similarity, New Stoic

A patch release that addresses an embedder-driven graph-density issue uncovered after v1.0.0 and adds Epictetus to the ancient-classical shelf.

## What changed

When v1.0.0 was re-indexed against the new BAAI/bge-small-en-v1.5 embedder, the per-book SIMILAR_TO edge count exploded — from a typical ~58K edges/book to as much as 235 edges/node on stylistically formulaic prose (Burroughs, Lovecraft, long Russian novels). Total corpus edges nearly tripled, from 4.5M to 12.4M, with no proportional gain in retrieval quality. Diagnosis: the underlying DocKG implementation was emitting *every* chunk pair above a 0.85 cosine threshold, with no bound on out-degree per chunk. For prose with high stylistic redundancy that threshold lost its discriminative power.

The fix lives in DocKG (now 0.13.0) and enforces a per-chunk top-K cap on SIMILAR_TO edges. After the corpus re-build with K=5, the graph sits at **4.84M edges across 79 books** — bounded, signal-rich, and ~14% faster to ingest. Princess of Mars, the worst offender, dropped from 1.28M edges to 12K (103×).

This release also adds **Epictetus** — *A Selection from the Discourses of Epictetus with the Encheiridion* (Gutenberg #10661) — to the ancient-classical genre, joining Marcus Aurelius's *Meditations* on the Stoic shelf.

## Corpus stats

| Metric | v1.0.0 | v1.0.1 |
|---|---:|---:|
| Books | 78 | **79** |
| Nodes | 445,486 | **448,139** |
| Edges | 12,429,291 (post-reindex) | **4,836,993** |
| ancient-classical books | 8 | **9** |

## Upgrading

```bash
poetry install              # picks up doc-kg 0.13.0
gutenkg ingest --force-build
```

The new defaults (`--similar-k 5 --similar-threshold 0.85` on `dockg build`) are bounded out-of-the-box. No code changes needed in downstream consumers.

## Citation

> Suchanek, E. G. (2026). *GutenbergKG: The Knowledge Press* (Version 1.0.1) [Software]. Flux-Frontiers. https://github.com/Flux-Frontiers/gutenberg_kg

Full changelog: [CHANGELOG.md](CHANGELOG.md)
