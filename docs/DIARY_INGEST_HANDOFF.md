# Diary Ingestion Handoff — Option 3: Full DiaryKG Pipeline

**For:** gutenberg_kg Docker build agent
**Topic:** Replace `dockg build`-only diary indexing with the full DiaryKG pipeline
**Date:** 2026-06-06
**Status:** Implemented 2026-06-06
**Supersedes:** Earlier handoff describing Option 1 (`dockg build` only)

---

## Why this change

The current `build_diaries.py` runs only Step 2 of the DiaryKG pipeline (`dockg build`
with `sentence_group`). It misses:

- **Step 3** — `_inject_topic_edges()`: reads the DiaryTransformer's pre-computed
  `topics: name:score,…` frontmatter and writes `HAS_TOPIC` edges with classifier
  confidence into SQLite. Without this, topic nodes come from DocKG's weaker keyword
  matcher, not the diary-aware classifier.
- **Step 4** — `_enrich_metadata()`: writes `timestamp`, `category`, `context`, and
  `diary_source_file` as first-class SQLite columns on every chunk node. Without this,
  temporal data is only in the chunk text — not queryable as a structured field.

In addition, the handler currently registers diaries as `KGKind.GUTENBERG`, so queries
go through the generic DocKG adapter. Registering as `KGKind.DIARY` routes them through
`DiaryKGAdapter` which surfaces `timestamp`, `source_file`, and category metadata on
every hit — enabling temporal-aware retrieval.

---

## Key structural insight

The `.diary/` subdirectory in each diary corpus directory is **structurally identical**
to the `.diarykg/corpus/` directory that `DiaryTransformer.ingest_to_corpus()` produces.
The YAML frontmatter fields match exactly:

```
source_file: the_diary_of_samuel_pepys_complete.md
entry_index: 42
chunk_index: 0
timestamp: 1660-02-15T00:00
category: work
context: Office
topics: work:1.0000
```

`DiaryKG` stores its corpus at `.diarykg/corpus/`. The simplest bridge:
**symlink** `.diarykg/corpus` → `.diary` before calling `DiaryKG.rebuild_index()`.
This reuses all DiaryKG enrichment code without any copying.

---

## The four-step pipeline

```
corpus/diaries/<Name>/
  .diary/              ← Step 1 output (already exists — DiaryTransformer ran offline)
  .diarykg/
    corpus   → ../.diary   ← symlink created by build_diary_index()
    graph.sqlite           ← Step 2: dockg build (sentence_group, no SIMILAR_TO)
    lancedb/               ← Step 2: vector index
    config.json            ← Step 2 metadata
```

| Step | What runs | Where implemented |
|---|---|---|
| 1 | `DiaryTransformer.ingest_to_corpus()` | **Already done** — `.diary/` exists |
| 2 | `DocKG.build()` (sentence_group, no similar) | `DiaryKG.rebuild_index()` calls this |
| 3 | `DiaryKG._inject_topic_edges()` | DiaryKG method — reads `topics:` frontmatter |
| 4 | `DiaryKG._enrich_metadata()` | DiaryKG method — writes `timestamp`, `category`, `context` columns |

---

## What to change in `build_diaries.py`

Replace the current `DocKG(...)` block with `DiaryKG.rebuild_index()`:

```python
# build_diaries.py  — updated build_diary_index()

def build_diary_index(diary_dir, opts, embedder=None):
    name = diary_dir.name
    diary_chunks_dir = diary_dir / ".diary"
    diarykg_dir = diary_dir / ".diarykg"
    corpus_link = diarykg_dir / "corpus"      # DiaryKG expects corpus here
    sqlite_path = diarykg_dir / "graph.sqlite"
    ...

    # Create .diarykg/ and symlink corpus → ../.diary so DiaryKG finds its corpus.
    diarykg_dir.mkdir(parents=True, exist_ok=True)
    if not corpus_link.exists():
        corpus_link.symlink_to(diary_chunks_dir.resolve())

    try:
        from diary_kg.kg import DiaryKG

        kg = DiaryKG(root=diary_dir, model=DIARY_EMBED_MODEL)
        # rebuild_index() = Step 2 (dockg build) + Step 3 (inject topics) + Step 4 (enrich metadata)
        kg.rebuild_index()
    except ImportError as exc:
        return DiaryBuildResult(name=name, status="failed", message=f"diary-kg not installed: {exc}")
    except Exception as exc:
        return DiaryBuildResult(name=name, status="failed", message=str(exc))

    nodes, edges = _sqlite_counts(sqlite_path)
    return DiaryBuildResult(name=name, status="built", nodes=nodes, edges=edges, ...)
```

Key points:
- `DiaryKG(root=diary_dir)` sets `self._corpus_dir = diary_dir / ".diarykg" / "corpus"`
- The symlink makes `self._corpus_dir` resolve to `.diary/`
- `rebuild_index()` runs Steps 2 + 3 + 4 in sequence without re-running the DiaryTransformer

---

## Using `dockg pipeline` for topic discovery (optional pre-step)

For diaries where the DiaryTransformer topics are sparse or absent, run
`dockg pipeline discover-topics` first to build a `topics.yaml`, then pass it
to `rebuild_index()` via the `topics_file` argument:

```bash
# Discover corpus-specific topics (run once per diary, output reviewed manually)
dockg pipeline discover-topics \
  --repo "corpus/diaries/<Name>/.diary" \
  --n-clusters 16 \
  --chunk-strategy sentence_group \
  --output "corpus/diaries/<Name>/topics.yaml"
```

Then in `build_diary_index()`:
```python
kg.rebuild_index(topics_file=str(diary_dir / "topics.yaml"))
```

For Pepys, `pepys_only_topics.yaml` already exists in the `diary_kg` repo — copy it
to `corpus/diaries/The Diary of Samuel Pepys — Complete/topics.yaml` and pass it in.
This gives the Pepys build the 17th-century-aware topic vocabulary rather than the
generic DocKG keyword classifier.

---

## What to change in `handler.py`

### 1. Register diaries as `KGKind.DIARY`

```python
# docker/handler.py  — in _bootstrap_registry()

from kg_rag.primitives import KGEntry, KGKind

entry = KGEntry(
    id=str(uuid.uuid4()),
    name=slug,
    kind=KGKind.DIARY,          # ← was KGKind.GUTENBERG
    repo_path=diary_dir,        # diary root, not .diarykg/
    venv_path=Path("/usr"),
    sqlite_path=sqlite,
    lancedb_path=lancedb,
    metadata={"source_file": _source_file_for(diary_dir)},  # see below
    created_at=datetime.now(UTC),
    updated_at=datetime.now(UTC),
)
```

Add a helper to read the source file name from `.diarykg/config.json`:
```python
def _source_file_for(diary_dir: Path) -> str:
    config = diary_dir / ".diarykg" / "config.json"
    if config.exists():
        import json
        return json.loads(config.read_text()).get("source_file", "")
    return ""
```

### 2. Remove diary filtering by `kg_name`

The current handler filters diary hits by `kg_name != "gutenberg"`. With
`KGKind.DIARY` registered, the orchestrator separates them by kind — no manual
filter needed. Update the `corpus="diary"` branch:

```python
# Before
elif corpus == "diary":
    kind_filter = [KGKind.GUTENBERG]
    diary_filter = True

# After
elif corpus == "diary":
    kind_filter = [KGKind.DIARY]
    diary_filter = False        # kind_filter handles separation
```

And remove the `diary_filter` post-filter block.

### 3. Surface temporal metadata on hits

`DiaryKGAdapter.query()` returns `CrossHit` objects where:
- `hit.name` = `timestamp` (ISO 8601 date string from the chunk)
- `hit.source_path` = original source `.txt` filename
- `hit.kg_kind` = `KGKind.DIARY`

Update `_hit_to_dict()` to include timestamp:
```python
def _hit_to_dict(hit) -> dict:
    return {
        "kg_name":    hit.kg_name,
        "kg_kind":    str(hit.kg_kind),
        "node_id":    hit.node_id,
        "name":       hit.name,
        "kind":       hit.kind,
        "score":      round(float(hit.score), 4),
        "summary":    hit.summary,
        "source_path": hit.source_path,
        "timestamp":  hit.name if hit.kg_kind == KGKind.DIARY else None,  # ← add
    }
```

---

## What `diary-kg` provides that makes this work

`diary-kg` is **already in the Dockerfile**:
```dockerfile
RUN pip install --no-cache-dir doc-kg diary-kg streamlit httpx watchdog
```

At runtime it provides:
- `DiaryKG.rebuild_index()` — Steps 2+3+4 as one call
- `DiaryKG._inject_topic_edges()` — reads `topics: name:score,…` from frontmatter,
  writes `HAS_TOPIC` edges with `{"confidence": 0.57, "source": "classifier"}` evidence
- `DiaryKG._enrich_metadata()` — adds `timestamp TEXT`, `category TEXT`, `context TEXT`,
  `diary_source_file TEXT` columns to the `nodes` table (idempotent `ALTER TABLE`)
- `DiaryKGAdapter` — registered automatically by KGRAG for `KGKind.DIARY` entries

The `DiaryKGAdapter` wraps `DiaryKG.query()` which queries the LanceDB vector index and
joins `timestamp`, `category`, `context` from the SQLite columns enriched in Step 4.

---

## What the SQLite schema looks like after Steps 3+4

Standard DocKG columns (from Step 2):

| column | type | example |
|---|---|---|
| `id` | TEXT | `chunk:entry_0042_chunk_0:1234` |
| `kind` | TEXT | `chunk` |
| `file_path` | TEXT | `entry_0042_chunk_0.md` |
| `text` | TEXT | `[Topics: work, naval] In the morning…` |

Extra columns added by Steps 3+4:

| column | type | example | step |
|---|---|---|---|
| `timestamp` | TEXT | `1660-02-15T00:00` | 4 |
| `category` | TEXT | `work` | 4 |
| `context` | TEXT | `Office` | 4 |
| `diary_source_file` | TEXT | `the_diary_of_samuel_pepys_complete.md` | 4 |

HAS_TOPIC edges (Step 3):

| src | rel | dst | evidence |
|---|---|---|---|
| `chunk:entry_0042_chunk_0:…` | `HAS_TOPIC` | `topic:work` | `{"confidence":1.0,"source":"classifier"}` |

---

## Updated `bundle_diaries()` in `build_corpus.py`

`bundle_diaries()` (`src/gutenberg_kg/build_corpus.py:181`) copies `.diarykg/` verbatim.
The symlink `corpus/diaries/<Name>/.diarykg/corpus → ../.diary` will be included in the
copy. Verify `shutil.copytree` follows symlinks:

```python
shutil.copytree(str(diarykg_dir), str(dest), dirs_exist_ok=True, symlinks=True)
```

If `symlinks=True` is not set, `copytree` dereferences the link and copies the full
`.diary/` content into the bundle under `diaries/<Name>/.diarykg/corpus/` — which is
also fine (larger bundle, but self-contained).

---

## Updated Makefile workflow

```
make build-diaries   # Step 1 done; Steps 2+3+4 via DiaryKG.rebuild_index()
make build-corpus    # bundles .diarykg/ + main DocKG prose corpus
make build           # docker build
```

No change to the Makefile targets — `gutenkg build-diaries` is already wired.
Only `build_diary_index()` in `build_diaries.py` and `_bootstrap_registry()` in
`docker/handler.py` need updating.

---

## Per-diary topics files

| Diary | Topics file | Notes |
|---|---|---|
| Pepys Complete | `pepys_only_topics.yaml` from `diary_kg` repo | 17th-century-aware; copy to `corpus/diaries/…/topics.yaml` |
| Evelyn Vol 1 & 2 | Run `dockg pipeline discover-topics` first | Similar 17th-century vocabulary to Pepys |
| Boswell Hebrides | Run `dockg pipeline discover-topics` first | 18th-century; different vocabulary |

---

## Summary of files to change

| File | Change |
|---|---|
| `src/gutenberg_kg/build_diaries.py` | Replace `DocKG(…)` block with symlink + `DiaryKG.rebuild_index()` |
| `docker/handler.py` | Register as `KGKind.DIARY`; add `_source_file_for()`; update corpus filter; add `timestamp` to hit dict |
| `src/gutenberg_kg/build_corpus.py` | Add `symlinks=True` to `shutil.copytree` in `bundle_diaries()` |
| `corpus/diaries/*/topics.yaml` | Copy `pepys_only_topics.yaml` for Pepys; run `discover-topics` for others |
