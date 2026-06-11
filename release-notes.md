# Release Notes — v1.6.0

> Released: 2026-06-10

## Semantic-First Retrieval

The worker now ranks results by **true semantic similarity** instead of routing
every query through graph-hop expansion. This is the headline fix of the release.

Naming a book in a query used to fail badly. *"What does the Quran say about
Moses?"* came back with *The Three Musketeers* and *Confucius* — and not a single
Quran passage. The cause was in `DocKG.query()`'s hop-1 expansion: every chunk
inherited the distance of the *seed* it was reached through, so an entire book
collapsed onto one flat score, and the genuinely best matches were buried below
the `max_nodes` cutoff before the genre filter ever saw them.

The new path queries the LanceDB vector table directly with cosine distance, so
each chunk is scored on its own merits. Content-kind, genre, and front-matter
filters are pushed into the search as a pre-filter, so the top-k is computed over
exactly the eligible passages. The named book now lands on top, every time:

| Query | Top result | Score |
|---|---|---|
| What is justice according to Plato? | The Republic | 0.824 |
| What does the Quran say about Moses? | The Quran | 0.801 |
| How does Dante describe the circles of Hell? | The Divine Comedy | 0.789 |
| Describe Darwin's observations on the Galapagos | The Voyage of the Beagle | 0.816 |
| What did Pepys say about the great fire? | Pepys' Diary | 0.706 |

Diaries get the same treatment across their per-book DiaryKG vector tables, so a
unified (`all`) query ranks books and diaries on **one comparable cosine scale**.
Previously the diaries' inflated plateau scores (~0.88) out-sorted better book
matches; now Plato's *Republic* correctly tops a justice query while the diaries
settle to ~0.62 where they belong.

The KGRAG orchestrator is no longer on the query path. Clean passage text and
diary timestamps are hydrated from SQLite (the LanceDB `text` column holds the
prefixed embed-text, not the clean passage).

---


## Simpler Installation

A new **`full` install extra** bundles everything except dev tooling — kgdeps,
viz, viz3d, and mcp — in one step:

```bash
pip install -e ".[full]"
# or
poetry install --extras "full"
```

Two new guides round out the docs:

- **`docs/INSTALLATION.md`** — prerequisites, platform notes, the complete
  environment-variable reference, and troubleshooting.
- **`docs/CHAT_UI.md`** — a walkthrough of the Streamlit *Knowledge Press* chat
  UI: search scopes, controls, synthesis providers, corpus-grounded image
  rendering, and troubleshooting.

The README gains a `Requirements` table and split **Quick Start — CLI** and
**Quick Start — Docker** sections covering the full
`make build-corpus → build → up → query` flow.

---

## In-Repo Knowledge-Graph Tooling

`.mcp.json` now registers the `pycodekg` and `dockg` MCP servers, so the
codebase and documentation knowledge graphs are queryable directly from the
editor.

---

## Quality & Fixes

- **`scripts/check_standard_queries.py`** — a validation harness that runs the
  eight standard chat queries against a live worker and asserts each returns a
  hit, printing the top results and scores. This is what verified the
  semantic-first fix end-to-end.
- **Image Resolution selector now works** — the chat UI's Preview / Standard /
  Full choice was shown in the caption but never sent to the image backend, so
  every render came back at 1536×1024. The selected size is now threaded
  end-to-end via a new `size` parameter, honored by the mflux local and serve
  backends.
- **`kgmodule-utils` bumped to `0.4.3`** across the pyproject floor, lock, and
  Docker build for the image-size fix.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
