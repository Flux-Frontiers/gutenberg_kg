# Release Notes — v1.2.0

> Released: 2026-05-12

## Highlights

**Corpus library API.** A new `corpus.py` module extracts all corpus data logic out of the CLI into a clean, path-parameterised public API (`collect_genre_stats`, `corpus_status`, `snapshot_build/save/list/show/diff`). CLI commands now delegate to this layer — making the data accessible from tests, scripts, and external code without touching Click internals.

**New CLI commands.** `gutenkg status` prints a live Rich table of per-genre book/node/edge counts directly from the KGRAG registry. `gutenkg snapshot` captures point-in-time corpus metrics to `corpus/.snapshots/` with four subcommands: `save`, `list`, `show`, and `diff` (compare two snapshots side-by-side).

**Corpus growth chart.** `gutenkg viz-timeline` renders an interactive Plotly chart of corpus growth across saved snapshots — 2D subplot grid (books / authors / nodes / edges over time) or 3D multi-metric scatter. Requires the new `viz` extra.

**Corpus expanded to 181 books.** Six new works added: five Stoic texts (Seneca's *Minor Dialogues*, two Epictetus works, two Marcus Aurelius editions) and Nietzsche's *Twilight of the Idols / The Antichrist*. Forty-plus author profiles filled in.

**3-D forest visualiser overhauled.** Node rendering is now O(kinds) instead of O(nodes) via `pv.PolyData.glyph()`. Trunks are genre-coloured using a merged mesh and a 10-colour palette. Sections spiral up trunks with golden-angle branching. Grove radii doubled to accommodate the larger corpus without overlap.

**Ingest performance.** `build_dockg()` now calls DocKG in-process and accepts a shared `SentenceTransformerEmbedder` — one model load per genre instead of one per book.

**`rebuild-indices` rename.** `gutenkg rebuild-lancedb` renamed to `gutenkg rebuild-indices` (technology-neutral).

## Test Coverage

- `tests/test_cmd_status.py` — 42 tests covering all status helpers and CLI integration
- `tests/test_cmd_snapshot.py` — 41 tests covering all snapshot subcommands and round-trip flows
- `tests/test_ingest.py` — 5 new tests for `build_dockg` (dry-run, exception, embedder passthrough)

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
