# GutenbergKG — Ingestion Pipeline

> **Current corpus:** 241 books across 20 genres. The per-stage sizes below are
> architecture examples from a reference build; consult the [corpus catalog](CORPUS.md)
> for live coverage and [`gutenkg status`](CHEATSHEET.md#check-ingest-status-across-corpus)
> for local index metrics.

---

## Overview

```
  Raw Text (Project Gutenberg / Internet Archive)
        │
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                   CORPUS  (corpus/)                         │
  │   20 genres · 241 books · Markdown + reference.md             │
  └─────────────────────────────────────────────────────────────┘
        │
        ├─── 18 prose / technical genres ─────────────────────────▶  Semantic Chunker
        │       american-literature, ancient-classical,              (doc-kg)
        │       english-literature, french-literature,
        │       philosophy, science-fiction, drama …
        │
        ├─── sacred-texts (7 books) ────────────────────────────▶  Verse Chunker
        │       Bible KJV · Quran · Torah · Bhagavad Gita           (chapter:verse aware)
        │       Upanishads · Analects · Tao Te Ching
        │
        └─── diaries (4 collections) ───────────────────────────▶  DiaryKG Pipeline
                Pepys Complete · Evelyn Vol 1&2                      (temporal, separate)
                Boswell's Hebrides
```

---

## Stage 1 — Content Routing

Each genre is assigned a **chunk strategy** before the walk begins.
All genres in a strategy group are processed together in one DocKG pass.

| Strategy | Genres | Chunker behaviour |
|---|---|---|
| `semantic` | 18 genres (230 books) | Sentence-transformer semantic boundary detection |
| `verse` | `sacred-texts` (7 books) | Chapter:verse window; auto-detects `^\d+:\d+\s` format |
| `diarykg` | `diaries` (4 collections) | Separate temporal pipeline — YAML timestamps, diary-aware chunking |

> **Auto-detection:** The verse chunker fires automatically on any file where >10% of
> non-blank lines match the `chapter:verse` pattern — even inside a prose-genre book.

---

## Stage 2 — Graph Parsing  `[1/4]`

```
  For each strategy group (sequential):
  ┌──────────────────────────────────────────────────────────┐
  │  DocKG.build_graph(wipe=True¹)                           │
  │                                                          │
  │  corpus/ walk  →  chunk text  →  SQLite nodes           │
  │                                                          │
  │  Node fields:                                            │
  │    file_path  =  <genre>/<book>/<file>.md  ←  genre tag  │
  │    content_type  =  prose | verse | poetry | diary        │
  │    book, chapter, verse_start, verse_end   (verse only)   │
  │    section, heading                        (all)          │
  └──────────────────────────────────────────────────────────┘
  ¹ First group wipes; subsequent groups append to same graph.sqlite
```

**Output:** `bundles/gutenberg-all/.dockg/graph.sqlite`
683,531 nodes · all genres in one table

---

## Stage 3 — Embedding  `[2/4]`

```
  DocKG.build_embeddings(n_workers=4)
  ┌──────────────────────────────────────────────────────────┐
  │  Read every node from graph.sqlite                       │
  │         │                                                │
  │         ▼                                                │
  │  SentenceTransformerEmbedder                             │
  │    model : BAAI/bge-small-en-v1.5                        │
  │    dim   : 384                                           │
  │    batch : 64 chunks/batch                               │
  │         │                                                │
  │         ▼                                                │
  │  embeddings.jsonl (temp cache, deleted after indexing)   │
  └──────────────────────────────────────────────────────────┘
```

**One embedding pass** covers all strategy groups (prose + verse combined).

---

## Stage 4 — Vector Index + Lexical Index  `[3/4]`

```
  DocKG.build_index_from_cache()
  ┌──────────────────────────────────────────────────────────┐
  │  embeddings.jsonl                                        │
  │         │                                                │
  │         ├──▶  vectors.sqlite (sqlite-vec `vec0` table)   │
  │         │      384-dim fp32 · ~1.1 GB                    │
  │         │      enables semantic search at query time     │
  │         │                                                │
  │         └──▶  SIMILAR_TO edges  (graph.sqlite)           │
  │                OFF by default — enable with `--similar`   │
  │                threshold : cosine ≥ 0.85                 │
  │                cap       : k = 8 per chunk               │
  │                scope     : cross-book, cross-author       │
  └──────────────────────────────────────────────────────────┘
        │
        ▼
  ┌──────────────────────────────────────────────────────────┐
  │  store.rebuild_fts()  →  nodes_fts (FTS5)                │
  │    the lexical half of the worker's hybrid retrieval;     │
  │    without it, search silently degrades to dense-only     │
  └──────────────────────────────────────────────────────────┘
```

The served handler is semantic-first and never traverses `SIMILAR_TO`, so
discovery is opt-in and is skipped entirely on `--update`. See
[`SIMILAR_TO_CAP_RECOMMENDATION.md`](SIMILAR_TO_CAP_RECOMMENDATION.md) for the
evaluation behind the cap. Measured bundle sizes live in
[`APP_ARCHITECTURE.md`](APP_ARCHITECTURE.md).

---

## Stage 5 — Diary Bundle  `[4/4]`

DiaryKG indices are built by `make build-diaries` **before** `make build-corpus` runs.
Each diary goes through the full four-step DiaryKG pipeline:

| Step | What runs |
|---|---|
| 0 | `gutenkg chunk-diaries` — `GutenbergDiaryParser` parses `<book>.md` → `.diary_source.psv`, then `DiaryTransformer.ingest_to_corpus()` chunks it into `.diary/`. Reproducible from the committed `.md`; `make build-diaries` runs this first. |
| 2 | `DocKG.build()` via `DiaryKG.rebuild_index()` — sentence_group, no SIMILAR_TO |
| 3 | `DiaryKG._inject_topic_edges()` — writes `HAS_TOPIC` edges from frontmatter classifier scores |
| 4 | `DiaryKG._enrich_metadata()` — adds `timestamp`, `category`, `context`, `diary_source_file` columns |

`bundle_diaries()` copies the completed `.diarykg/` indices verbatim (`symlinks=True` preserves
the `.diarykg/corpus -> ../.diary` symlink; if the target is absent in the bundle the symlink is
dangling but query-time reads only hit `graph.sqlite` + `vectors.sqlite`, so this is safe).

```
  corpus/diaries/
    The Diary of Samuel Pepys — Complete/.diarykg/              ──┐
    The Diary of John Evelyn — Volume 1/.diarykg/               ──┤  shutil.copytree
    The Diary of John Evelyn — Volume 2/.diarykg/               ──┤  (symlinks=True)
    The Journal of a Tour to the Hebrides with Samuel Johnson/.diarykg/  ──┘

  bundles/gutenberg-all/diaries/
    The Diary of Samuel Pepys — Complete/.diarykg/
    The Diary of John Evelyn — Volume 1/.diarykg/
    The Diary of John Evelyn — Volume 2/.diarykg/
    The Journal of a Tour to the Hebrides with Samuel Johnson/.diarykg/
```

DiaryKG chunk nodes carry these extra SQLite columns (added by Step 4):

| Column | Example |
|---|---|
| `timestamp` | `1660-02-15T00:00` |
| `category` | `work` |
| `context` | `Office` |
| `diary_source_file` | `the_diary_of_samuel_pepys_complete.md` |

Step 3 also writes `HAS_TOPIC` edges with classifier confidence scores into the graph.

---

## Stage 6 — Catalog Sidecar

```
  build_catalog()  →  .dockg/catalog.json

  Key: "<genre>/<book>"   (matches file_path prefix of every node)

  {
    "philosophy/The Republic": {
      "genre":        "philosophy",
      "title":        "The Republic",
      "author":       "Plato",
      "author_birth": "428 BC",
      "author_death": "348 BC",
      "ebook_id":     1497
    },
    …  241 entries
  }
```

No schema change. The handler joins author/title onto search hits at query time using
the `file_path` prefix — no extra node fields required.

---

## Output Bundle

```
  bundles/gutenberg-all/
  ├── .dockg/
  │   ├── graph.sqlite          2.9 GB   (683,531 nodes; embed-text, topics, entities)
  │   ├── vectors.sqlite        1.1 GB   (688 K × 384-dim fp32 vectors, sqlite-vec)
  │   └── catalog.json          size varies  (241 books · author/title/ID)
  │
  └── diaries/
      ├── The Diary of Samuel Pepys — Complete/.diarykg/
      ├── The Diary of John Evelyn — Volume 1/.diarykg/
      ├── The Diary of John Evelyn — Volume 2/.diarykg/
      └── The Journal of a Tour to the Hebrides with Samuel Johnson/.diarykg/

  Total: ~4.3 GB  ·  Build time: 34m  ·  streaming embed (single-process)
```

---

## Build Workflow

Full sequence from clean checkout to running container:

```
make chunk-diaries   # .md -> .diary_source.psv -> .diary/ chunks (Gutenberg parser; clean-clone step)
make build-diaries   # DiaryKG pipeline (Steps 2+3+4) for each diary; depends on chunk-diaries
make build-corpus    # DocKG prose index + copy diary indices -> bundles/gutenberg-all/
make build           # docker build — COPYs bundles/gutenberg-all/ into image
make run             # docker compose up — worker on http://localhost:8000
```

`.diary/` and `.diary_source.psv` are git-ignored — `make chunk-diaries` rebuilds them from
each book's committed `.md`. The `.md → PSV` step is gutenberg_kg's own
`GutenbergDiaryParser` (`src/gutenberg_kg/diary/parser.py`), with the per-book date format
selected by a committed `.diary_format` file (`pepys` | `evelyn` | `boswell`).

`make build-corpus` depends on `make build-diaries` in the Makefile, so running
`make build-corpus` alone is sufficient for steps 1-2.  **Never run `make build`
before `make build-corpus` completes** — the Dockerfile COPYs from `bundles/gutenberg-all/`
and will bake in a stale or empty bundle if that directory is missing or outdated.

---

## Query-Time Architecture (Docker Image)

```
  ┌─────────────────────────────────────────────────────────────┐
  │  corpus-gutenberg  (Docker image, ~9 GB)                    │
  │                                                             │
  │  Handler registers:                                         │
  │    KGKind.GUTENBERG  →  .dockg/  (semantic + verse)         │
  │    KGKind.DIARY      →  diaries/*/  (temporal, per-diary)   │
  │                                                             │
  │  Query path:                                                │
  │    user query  →  KGRAG federated search                   │
  │                   ├── sqlite-vec kNN (dense semantic)       │
  │                   ├── FTS5 / BM25 (lexical), fused by RRF   │
  │                   └── DiaryKG temporal filter (date range)  │
  │                →  ranked chunks  →  LLM synthesis           │
  │                   (Ollama / oMLX via OpenAI-compatible API) │
  └─────────────────────────────────────────────────────────────┘
```

---

## Current routing at a glance

| Content type | Genres | Books | Index |
|---|---:|---:|---|
| Prose and technical text | 18 | 230 | DocKG semantic chunking |
| Sacred texts | 1 | 7 | DocKG verse chunking |
| Diaries | 1 | 4 | DiaryKG temporal indexing |
| **Total** | **20** | **241** | |

---

For the live genre-by-genre breakdown, see [Books in the Corpus](CORPUS.md).
