# Release Notes — v1.3.0

> Released: 2026-05-16

### Added

- **`gutenkg snapshot prune`** — new subcommand that removes vestigial snapshots carrying
  no new metric information. Cleans three categories: metric-duplicates (interior snapshots
  with identical metrics), broken entries (manifest entries whose JSON file is missing), and
  orphaned files (JSON files on disk not referenced by the manifest). Oldest (baseline) and
  newest (latest) snapshots are always kept. `--dry-run` reports what would be removed
  without deleting anything.

- **`gutenkg re-register`** — new CLI command (`cmd_reregister.py` + `run_reregister()` in
  `ingest.py`) that re-registers all built books in the KGRAG registry with the correct
  `kind=gutenberg` without rebuilding DocKGs. Idempotent and safe to run on any machine,
  including fresh clones where the registry is empty. Accepts `--genre`, `--dry-run`, and
  `--registry` flags. Skips books that are already correctly tagged and books with no built
  `.dockg/graph.sqlite`.

### Changed

- **`gutenkg snapshot`** — rewritten to use `GutenbergSnapshotManager` (backed by
  `kg_utils.snapshots.SnapshotManager`). Snapshots are now keyed by git tree hash and
  stored alongside a `manifest.json` index with per-entry deltas vs. previous and baseline.
  Subcommands updated: `save` gains `--force` and `--json`; `list` gains `--branch`,
  `--limit`, and `--json`; `show` is key-addressable (defaults to latest); `diff` accepts
  explicit keys or auto-selects last two, with `--json` output.

- **`tests/test_cmd_snapshot.py`** — fully rewritten for the new `GutenbergSnapshotManager`
  API (37 tests). Covers help text, `list`/`show`/`diff`/`prune`/`save` CLI paths, error
  cases, JSON output, round-trip save→list and save→show flows. Uses a `fake_registry`
  fixture (in-memory SQLite) for `save` tests; all others use a manifest-writing helper so
  no live registry is required.

### Fixed

- **`gutenkg snapshot diff` delta display** — all metrics showed `(+0)` because `_line()`
  looked up the computed delta using `total_books`/`total_nodes` keys while
  `_compute_delta_from_metrics` stores them as `books`/`nodes`. Fixed by computing the
  delta directly as `mb − ma` from the already-fetched metric values, eliminating any
  dependency on delta dict key names.

- **`ingest.py` `register_book`** — changed `KGKind.from_str("doc")` to `KGKind.GUTENBERG`
  so all new ingest runs register books with the correct kind. Previously all 203 Gutenberg
  books were registered as `kind=doc` instead of `kind=gutenberg`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
