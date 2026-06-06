# Diary Ingestion Handoff

**For:** gutenberg_kg Docker build agent
**Topic:** How to build `.diarykg/` indices from diary chunk corpora
**Date:** 2026-06-06

---

## What this document covers

The `gutenkg build-corpus` command (which drives the Docker image build) calls
`bundle_diaries()` as its final stage. That function **copies** existing
`.diarykg/` indices verbatim — it does **not** build them. If you are starting
from scratch (no pre-built `.diarykg/` directories), you must build them first
using `dockg build`. This document explains exactly how.

---

## Diary corpus layout

Diaries live under `corpus/diaries/`, each in its own named directory:

```
corpus/diaries/
  The Diary of Samuel Pepys — Complete/
    .diary/                       ← pre-chunked entry markdown files
      entry_0000_chunk_0.md
      entry_0000_chunk_1.md
      entry_0001_chunk_0.md
      …  (8,423 files for Pepys)
    .diarykg/                     ← DocKG index (build output)
      graph.sqlite                  (45,506 nodes · 310,205 edges)
      lancedb/                      (vector index)

  The Diary of John Evelyn — Volume 1/
    .diary/   (1,790 files)
    .diarykg/ (13,010 nodes · 46,403 edges)

  The Diary of John Evelyn — Volume 2/
    .diary/   (1,776 files)
    .diarykg/ (10,844 nodes · 44,925 edges)

  The Journal of a Tour to the Hebrides with Samuel Johnson/
    .diary/   (1,743 files)
    .diarykg/ (10,413 nodes · 40,379 edges)
```

---

## Chunk file format (`.diary/entry_NNNN_chunk_N.md`)

Each file is a standalone Markdown document with YAML frontmatter:

```markdown
---
source_file: the_diary_of_samuel_pepys_complete.md
entry_index: 1
chunk_index: 0
timestamp: 1660-01-02T00:00
category: pepys_court
context: General
topics: pepys_court:0.5710,personal_info:0.1430,learning:0.1430,pepys_financial:0.1430
---

[Topics: pepys_court, personal_info, learning, pepys_financial]

In the morning before I went forth old East brought me a dozen of bottles of
sack, and I gave him a shilling for his pains. …
```

Key fields:
- `timestamp` — ISO 8601 diary entry date (temporal dimension)
- `category` — primary topic slug
- `topics` — scored topic list from the DiaryKG classifier
- Body text starts after the frontmatter block

DocKG reads these as plain Markdown files. The YAML frontmatter is treated as
prose — it does not need special handling by the ingest pipeline.

---

## Building the `.diarykg/` index

Run `dockg build` once per diary, pointing `--repo` at the `.diary/` subdirectory
(where the `entry_*.md` files live) and directing the output into `.diarykg/`.

### Command template

```bash
dockg build \
  --repo   "corpus/diaries/<DIARY-NAME>/.diary" \
  --sqlite "corpus/diaries/<DIARY-NAME>/.diarykg/graph.sqlite" \
  --lancedb "corpus/diaries/<DIARY-NAME>/.diarykg/lancedb" \
  --chunk-strategy sentence_group \
  --sentences-per-chunk 4 \
  --no-similar \
  --model BAAI/bge-small-en-v1.5
```

### Flag rationale

| Flag | Value | Why |
|---|---|---|
| `--chunk-strategy sentence_group` | `sentence_group` | Chunks are already small discrete entries (~400-500 chars). `semantic` would re-chunk them further with an embedder and fragment the temporal structure. |
| `--sentences-per-chunk 4` | 4 | DocKG default; groups 4 sentences per sub-chunk within each entry file. |
| `--no-similar` | flag | Diary entries are chronologically dense and stylistically homogeneous — SIMILAR_TO edges between near-identical daily entries produce low-value noise. Skip them. |
| `--model BAAI/bge-small-en-v1.5` | explicit | Must match the model baked into the Docker image (`EMBED_MODEL` env var). The handler and build pipeline both use `bge-small-en-v1.5`. |

### Concrete commands (all four diaries)

Run from the `gutenberg_kg` repo root:

```bash
# Pepys (largest — ~45 min; 8,423 entries → ~45K nodes)
dockg build \
  --repo   "corpus/diaries/The Diary of Samuel Pepys — Complete/.diary" \
  --sqlite "corpus/diaries/The Diary of Samuel Pepys — Complete/.diarykg/graph.sqlite" \
  --lancedb "corpus/diaries/The Diary of Samuel Pepys — Complete/.diarykg/lancedb" \
  --chunk-strategy sentence_group \
  --no-similar \
  --model BAAI/bge-small-en-v1.5

# Evelyn Vol 1 (~5 min; 1,790 entries → ~13K nodes)
dockg build \
  --repo   "corpus/diaries/The Diary of John Evelyn — Volume 1/.diary" \
  --sqlite "corpus/diaries/The Diary of John Evelyn — Volume 1/.diarykg/graph.sqlite" \
  --lancedb "corpus/diaries/The Diary of John Evelyn — Volume 1/.diarykg/lancedb" \
  --chunk-strategy sentence_group \
  --no-similar \
  --model BAAI/bge-small-en-v1.5

# Evelyn Vol 2 (~5 min; 1,776 entries → ~11K nodes)
dockg build \
  --repo   "corpus/diaries/The Diary of John Evelyn — Volume 2/.diary" \
  --sqlite "corpus/diaries/The Diary of John Evelyn — Volume 2/.diarykg/graph.sqlite" \
  --lancedb "corpus/diaries/The Diary of John Evelyn — Volume 2/.diarykg/lancedb" \
  --chunk-strategy sentence_group \
  --no-similar \
  --model BAAI/bge-small-en-v1.5

# Boswell (Hebrides) (~5 min; 1,743 entries → ~10K nodes)
dockg build \
  --repo   "corpus/diaries/The Journal of a Tour to the Hebrides with Samuel Johnson/.diary" \
  --sqlite "corpus/diaries/The Journal of a Tour to the Hebrides with Samuel Johnson/.diarykg/graph.sqlite" \
  --lancedb "corpus/diaries/The Journal of a Tour to the Hebrides with Samuel Johnson/.diarykg/lancedb" \
  --chunk-strategy sentence_group \
  --no-similar \
  --model BAAI/bge-small-en-v1.5
```

### Expected node counts after build

| Diary | Entry files | Nodes | Edges |
|---|---:|---:|---:|
| Pepys Complete | 8,423 | ~45,506 | ~310,205 |
| Evelyn Vol 1 | 1,790 | ~13,010 | ~46,403 |
| Evelyn Vol 2 | 1,776 | ~10,844 | ~44,925 |
| Boswell Hebrides | 1,743 | ~10,413 | ~40,379 |

Node breakdown (Pepys example):
- `chunk` — 19,339 (DocKG sub-chunks from sentence_group splitting)
- `document` — 8,423 (one per entry file)
- `topic` — 7,424
- `entity` — 7,186
- `keyword` — 3,134

---

## How `bundle_diaries()` picks them up

After all four `.diarykg/` indices exist, `gutenkg build-corpus` runs
`bundle_diaries()` (`src/gutenberg_kg/build_corpus.py:181`) which does:

```python
for diary_dir in sorted(diaries_root.iterdir()):
    diarykg_dir = diary_dir / ".diarykg"
    if not diarykg_dir.exists():
        continue          # ← silently skipped if you forgot to build it
    dest = bundle_diaries_dir / diary_dir.name / ".diarykg"
    shutil.copytree(str(diarykg_dir), str(dest), dirs_exist_ok=True)
```

**If `.diarykg/` is absent, `bundle_diaries()` silently skips that diary.** The
handler will start but `corpus=diary` queries will return zero hits for the
missing diary. There is no error — check the startup log for
`[bootstrap] registered diary: <slug>` lines to confirm all four loaded.

The bundle destination layout is:

```
bundles/gutenberg-all/diaries/
  The Diary of Samuel Pepys — Complete/.diarykg/
  The Diary of John Evelyn — Volume 1/.diarykg/
  The Diary of John Evelyn — Volume 2/.diarykg/
  The Journal of a Tour to the Hebrides with Samuel Johnson/.diarykg/
```

---

## Handler registration

At container startup, `docker/handler.py::_bootstrap_registry()` walks
`/workspace/gutenberg/diaries/` and registers each diary as `KGKind.GUTENBERG`
(the DocKG adapter — not a native DiaryKG adapter, because `.diarykg/` was
built with `dockg build` and uses the DocKG schema):

```python
entry = KGEntry(
    name=slug,          # e.g. "pepys-complete"
    kind=KGKind.GUTENBERG,
    sqlite_path=diarykg_dir / "graph.sqlite",
    lancedb_path=diarykg_dir / "lancedb",
    …
)
```

Slug derivation (from handler.py):
- `"The Diary of Samuel Pepys — Complete"` → `"pepys-complete"`
- `"The Diary of John Evelyn — Volume 1"` → `"evelyn-volume-1"`
- `"The Diary of John Evelyn — Volume 2"` → `"evelyn-volume-2"`
- `"The Journal of a Tour to the Hebrides with Samuel Johnson"` → `"johnson"`

Successful registration prints:
```
[bootstrap] registered diary: pepys-complete
[bootstrap] registered diary: evelyn-volume-1
…
```

---

## Full Docker build workflow (from scratch)

```bash
# 1. Build all four .diarykg/ indices (run in gutenberg_kg repo root)
#    Do this before build-corpus, as bundle_diaries() copies these.
#    (Skip any that already exist on disk — dockg build is idempotent with --update)

dockg build \
  --repo "corpus/diaries/The Diary of Samuel Pepys — Complete/.diary" \
  --sqlite "corpus/diaries/The Diary of Samuel Pepys — Complete/.diarykg/graph.sqlite" \
  --lancedb "corpus/diaries/The Diary of Samuel Pepys — Complete/.diarykg/lancedb" \
  --chunk-strategy sentence_group --no-similar --model BAAI/bge-small-en-v1.5

# … (repeat for Evelyn Vol 1, Vol 2, and Boswell as shown above)

# 2. Build the consolidated DocKG bundle (prose + verse + copy diaries)
#    Takes ~24 min on Apple M5 Max.
gutenkg build-corpus

# 3. Build the Docker image (bakes bundles/gutenberg-all/ into the image)
docker build -f docker/Dockerfile -t corpus-gutenberg:latest .

# 4. Run
docker compose -f docker/docker-compose.yml up -d gutenberg-worker
```

---

## Incremental update (adding a new diary)

1. Place chunked entries in `corpus/diaries/<New Diary Name>/.diary/`
2. Run `dockg build` with the flags above, pointing at the new `.diary/`
3. Re-run `gutenkg build-corpus` (or just re-run `bundle_diaries()` manually)
4. Rebuild the Docker image

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `[bootstrap] skipping <name> — no .diarykg/graph.sqlite` | `.diarykg/` was not built or `graph.sqlite` is absent | Run `dockg build` for that diary |
| `corpus=diary` returns 0 hits | diary not registered | Check startup log for `[bootstrap] registered diary:` lines |
| Topics all `fallback` | No topics YAML provided | Topics come from frontmatter text; the DocKG keyword classifier picks them up from the `[Topics: …]` body line — no separate topics file needed |
| Embedding model mismatch | Built with a different model than `EMBED_MODEL` | Rebuild with `--model BAAI/bge-small-en-v1.5` |
| `VerseChunker` fires on diary entries | Diary entries contain `\d+:\d+` patterns (rare) | Force strategy: `--chunk-strategy sentence_group` (already in the commands above) |

---

## Where the `dockg` binary lives

In the gutenberg_kg virtualenv:

```bash
.venv/bin/dockg build …
```

Or if `doc-kg` is installed globally in the Docker image via `pip install doc-kg`,
use `dockg` directly. The Dockerfile installs it with:

```dockerfile
RUN pip install --no-cache-dir doc-kg diary-kg streamlit httpx watchdog
```

So inside the image, `dockg` is on `$PATH`.
