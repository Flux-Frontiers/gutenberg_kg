# GutenbergKG — Ingestion Pipeline

**The Knowledge Press:** 245 books · 18 genres · one query-ready index

---

## Overview

```
  Raw Text (Project Gutenberg / Internet Archive)
        │
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                   CORPUS  (corpus/)                         │
  │   18 genres  ·  245 books  ·  Markdown + reference.md      │
  └─────────────────────────────────────────────────────────────┘
        │
        ├─── 17 prose genres ────────────────────────────────────▶  Semantic Chunker
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
| `semantic` | 17 genres (238 books) | Sentence-transformer semantic boundary detection |
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
696,166 nodes · all genres in one table

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
  │  embeddings.json  (temp cache, deleted after indexing)   │
  └──────────────────────────────────────────────────────────┘
```

**One embedding pass** covers all strategy groups (prose + verse combined).

---

## Stage 4 — Vector Index + Similarity Edges  `[3/4]`

```
  DocKG.build_index_from_cache()
  ┌──────────────────────────────────────────────────────────┐
  │  embeddings.json                                         │
  │         │                                                │
  │         ├──▶  LanceDB (ANN vector index)                 │
  │         │      384-dim · ~1.6 GB                         │
  │         │      enables semantic search at query time     │
  │         │                                                │
  │         └──▶  SIMILAR_TO edges  (graph.sqlite)           │
  │                threshold : cosine ≥ 0.85                 │
  │                cap       : k = 8 per chunk               │
  │                scope     : cross-book, cross-author       │
  │                2,582,715 edges  (42% of all edges)        │
  └──────────────────────────────────────────────────────────┘
```

**Total edges:** 6,175,439  ·  **Index size:** 6,508.9 MB (sqlite 4.8 GB + lancedb 1.6 GB)

---

## Stage 5 — Diary Bundle  `[4/4]`

```
  DiaryKG indices are NOT re-ingested through DocKG.
  Temporal structure and YAML timestamps are preserved by copying verbatim.

  corpus/diaries/
    The Diary of Samuel Pepys — Complete/.diarykg/   ──┐
    The Diary of John Evelyn — Volume 1/.diarykg/    ──┤  shutil.copytree
    The Diary of John Evelyn — Volume 2/.diarykg/    ──┤  ──────────────▶
    The Journal of a Tour to the Hebrides/.diarykg/  ──┘

  bundles/gutenberg-all/diaries/
    pepys-complete/.diarykg/
    evelyn-vol1/.diarykg/
    evelyn-vol2/.diarykg/
    boswell-hebrides/.diarykg/
```

DiaryKG nodes carry: `date`, `year`, `month`, `entry_index`, `location` — queryable as a
temporal dimension alongside the main semantic index.

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
  │   ├── graph.sqlite          4.8 GB   (696,166 nodes · 6,175,439 edges)
  │   ├── lancedb/              1.6 GB   (696,166 × 384-dim vectors)
  │   └── catalog.json          84 KB    (241 books · author/title/ID)
  │
  └── diaries/
      ├── pepys-complete/.diarykg/
      ├── evelyn-vol1/.diarykg/
      ├── evelyn-vol2/.diarykg/
      └── boswell-hebrides/.diarykg/

  Total: 6,508.9 MB  ·  Build time: 23m 18s  ·  4 embed workers
```

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
  │                   ├── LanceDB ANN (semantic similarity)     │
  │                   ├── SQLite graph traversal (SIMILAR_TO)   │
  │                   └── DiaryKG temporal filter (date range)  │
  │                →  ranked chunks  →  LLM synthesis           │
  │                   (Ollama / oMLX via OpenAI-compatible API) │
  └─────────────────────────────────────────────────────────────┘
```

---

## Corpus at a Glance

| Genre | Books | Chunker |
|---|---|---|
| philosophy | 48 | semantic |
| english-literature | 37 | semantic |
| ancient-classical | 26 | semantic |
| american-literature | 23 | semantic |
| science-fiction | 19 | semantic |
| russian-literature | 13 | semantic |
| french-literature | 12 | semantic |
| biography | 11 | semantic |
| drama | 11 | semantic |
| sacred-texts | 7 | **verse** |
| natural-history | 7 | semantic |
| letters | 7 | semantic |
| german-literature | 5 | semantic |
| world-literature | 5 | semantic |
| shakespeare | 4 | semantic |
| travel | 6 | semantic |
| audel-electric | 3 | semantic |
| spanish | 1 | semantic |
| **diaries** | **4** | **DiaryKG (temporal)** |
| **TOTAL** | **249** | |

---

*Generated from `gutenkg build-corpus` · doc-kg 0.15.4 · BAAI/bge-small-en-v1.5*
