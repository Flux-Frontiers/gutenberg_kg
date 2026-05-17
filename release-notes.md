# GutenbergKG v1.3.0 — The Knowledge Press

**203 books · 1,000,103 nodes · 4,362,409 edges · 13 genres**

This release completes the snapshot system overhaul and adds two new operational
commands that make corpus maintenance significantly easier — especially on fresh
clones or machines where the KGRAG registry needs to be rebuilt from scratch.

---

## What's New

### Snapshot system rebuilt on `GutenbergSnapshotManager`

The entire snapshot subsystem has been rewritten on top of
`kg_utils.snapshots.SnapshotManager`, aligning it with the rest of the KG stack.
Snapshots are now keyed by **git tree hash** rather than timestamps, so two saves
from the same commit always produce the same key. A `manifest.json` index lives
alongside the snapshot files and tracks per-entry deltas vs. the previous snapshot
and the baseline — making `diff` and `list` much more informative.

Every subcommand gained new options:

| Subcommand | New options |
|---|---|
| `snapshot save` | `--force` (overwrite existing key), `--json` |
| `snapshot list` | `--branch`, `--limit`, `--json` |
| `snapshot show` | key-addressable (prefix match); defaults to latest |
| `snapshot diff` | explicit key args or auto last-two; `--json` output |

### `gutenkg snapshot prune` — new

Cleans up vestigial snapshots that carry no new information. Three sweep categories:

- **Metric-duplicates** — interior snapshots whose metrics are identical to their
  neighbour (the corpus didn't change between saves)
- **Broken entries** — manifest entries whose JSON file is missing from disk
- **Orphaned files** — JSON files on disk not referenced by the manifest

The oldest (baseline) and newest (latest) snapshots are always preserved regardless.
`--dry-run` shows exactly what would be removed without touching anything.

### `gutenkg re-register` — new

Re-registers all built books in the KGRAG registry with `kind=gutenberg` without
rebuilding any DocKGs. Previously, a bug in `ingest.py` caused all 203 Gutenberg
books to be registered as `kind=doc` — making them invisible to genre-scoped
Gutenberg queries. `re-register` fixes this in seconds and is fully idempotent:
safe to run repeatedly, safe on any machine, safe on a fresh clone where the
registry is empty.

```bash
# Fix the whole corpus
gutenkg re-register

# Fix one genre only
gutenkg re-register --genre philosophy

# Preview without writing
gutenkg re-register --dry-run
```

---

## Fixes

- **`snapshot diff` showed `(+0)` for every metric** — delta lookup used the wrong
  key names (`total_books`/`total_nodes`) vs. what was stored (`books`/`nodes`).
  Deltas are now computed directly from the metric values, with no key dependency.

- **All 203 books registered as `kind=doc` instead of `kind=gutenberg`** — fixed in
  `ingest.py register_book`. New ingest runs are now tagged correctly. Use
  `gutenkg re-register` to fix existing registries without a full rebuild.

- **CI stability** — `kgmodule-utils` promoted to a core dependency (was missing
  from `pyproject.toml`); `kg_rag` imports in `ingest.py` made lazy so the module
  loads cleanly in environments where only the `dev` extra is installed.

---

## Corpus

| Genre | Books | Nodes | Edges |
|---|---:|---:|---:|
| English Literature | 37 | 187,058 | 927,903 |
| Ancient & Classical | 26 | 137,857 | 579,264 |
| Philosophy | 48 | 226,660 | 861,848 |
| Russian Literature | 13 | 90,191 | 462,058 |
| American Literature | 23 | 90,481 | 370,089 |
| French Literature | 12 | 89,511 | 447,010 |
| Science Fiction | 19 | 70,550 | 260,781 |
| Sacred Texts | 7 | 32,942 | 175,701 |
| World Literature | 5 | 21,185 | 83,696 |
| German Literature | 5 | 13,066 | 50,830 |
| Spanish Literature | 1 | 11,422 | 57,980 |
| Shakespeare | 4 | 6,260 | 22,743 |
| Technical Reference (IA) | 3 | 22,920 | 62,506 |
| **Total** | **203** | **1,000,103** | **4,362,409** |

---

## Upgrade

```bash
git pull
poetry install
gutenkg re-register   # one-time fix for existing registries
```

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
