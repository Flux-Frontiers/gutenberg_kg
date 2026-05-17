# GutenbergKG Pipeline

Technical reference: raw Gutenberg text → queryable KGRAG entry.

---

## 1. End-to-End Flow

```
Project Gutenberg
  OPDS feed / RDF catalog / plain text pg<id>.txt
        │
        ▼
fetch_metadata(id)
  ├─ OPDS → title, author, subjects, summary, language, rights
  └─ RDF  → author_birth/death, author_url, author_agent_id
        │
        ▼
download_book(id)
  1. idempotence check  (skip if <slug>.md exists; --force to override)
  2. fetch pg<id>.txt   (utf-8-sig, 3 retries + exponential backoff)
  3. strip_boilerplate() — remove PG header/footer markers
  4. text_to_markdown()  — detect headings, emit Markdown tree
  5. write_reference()   — metadata sidecar
        │
        ▼
corpus/<genre>/<Title>/
  ├── <slug>.md
  └── reference.md
        │
  gutenkg ingest --genre G
  get_pipeline(genre)
        │
   ┌────┴────────────────────────┐
   │                             │
pipeline == None          pipeline == "diary"
(standard genres)         (diaries genre)
   │                             │
   ▼                             ▼
build_dockg()           run_diary_pipeline()
→ book_dir/.dockg/      → book_dir/.diary/.dockg/
   │                             │
   └────────────┬────────────────┘
                ▼
register_book() + add_to_corpus()
  ├─ KGEntry → registry.sqlite  (kind = GUTENBERG)
  ├─ corpus: gutenberg-<genre>
  └─ corpus: gutenberg-all
                │
   (periodically, after a batch)
                ▼
gutenkg authors
  ├─ parse corpus/*/*/reference.md
  ├─ [--refresh] re-fetch RDF for missing provenance
  ├─ write corpus/authors/<slug>/author.md
  └─ write corpus/authors/index.md
```

---

## 2. Entry Points

| Command | Does |
|---|---|
| `gutenkg download book <id> [--genre G]` | Single book |
| `gutenkg download catalog <file> [--genre G]` | Batch from catalog file |
| `gutenkg download search "<query>"` | Gutenberg catalog search |
| `gutenkg download fetch-genre <G>` | Search + confirm + download whole genre |
| `gutenkg download survey [--genre G]` | Show downloaded/indexed state |
| `gutenkg ingest [--genre G]` | Build DocKG + register (auto-routes diary) |
| `gutenkg authors [--refresh] [--dry-run]` | Rebuild author pages |

Key source modules:

- [`src/gutenberg_kg/gutenberg.py`](../src/gutenberg_kg/gutenberg.py) — download library
- [`src/gutenberg_kg/ingest.py`](../src/gutenberg_kg/ingest.py) — ingest orchestration
- [`src/gutenberg_kg/diary/parser.py`](../src/gutenberg_kg/diary/parser.py) — `GutenbergDiaryParser`
- [`src/gutenberg_kg/diary/pipeline.py`](../src/gutenberg_kg/diary/pipeline.py) — diary pipeline
- [`src/gutenberg_kg/genres.py`](../src/gutenberg_kg/genres.py) — genre registry + `get_pipeline()`
- [`src/gutenberg_kg/authors.py`](../src/gutenberg_kg/authors.py) — author-corpus builder

---

## 3. Data Sources

| Endpoint | URL pattern | Used for |
|---|---|---|
| **OPDS feed** | `https://www.gutenberg.org/ebooks/{id}.opds` | Title, author, subjects, summary, language, rights |
| **RDF catalog** | `https://www.gutenberg.org/cache/epub/{id}/pg{id}.rdf` | Author birth/death, Wikipedia URL, agent ID |
| **Plain text** | `https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt` | The book (UTF-8 with BOM) |
| **Search** | `https://www.gutenberg.org/ebooks/search.opds/?query=…` | `download search` / `fetch-genre` only |

---

## 4. Downloading One Book

**`fetch_metadata(id)`** — OPDS → title, author (reversed "Last, First"), published, rights, subjects, language, summary. Then `_fetch_rdf_author()` merges birth/death/Wikipedia/agent_id (silent failure if RDF missing).

**`download_book(id)`**:
1. Idempotence check — skip if `<slug>.md` exists; `--force` overrides.
2. Fetch `pg{id}.txt` — `utf-8-sig`, 3 retries (2×/4× backoff).
3. `strip_boilerplate()` — removes everything before/after `*** START/END ***` markers.
4. `text_to_markdown()` — skips front-matter credits and TOC blocks; detects CHAPTER/VOLUME/PART/ACT/SCENE/LETTER/STAVE headings and emits `##`/`###`.
5. `write_reference()` — writes `reference.md` with Source, Author (Name, Born, Died, Wikipedia), Language, Subjects, Summary.

---

## 5. Standard Ingest Pipeline

Runs for all genres **not** listed in `corpus/genres.json → "pipelines"`.

```
book_dir/<slug>.md
  → DocKG.build_graph()             →  .dockg/graph.sqlite
  → DocKG.build_embeddings()        →  .dockg/embeddings.json (temp)
  → DocKG.build_index_from_cache()  →  .dockg/lancedb/
  → (embeddings.json deleted)
```

A shared `SentenceTransformerEmbedder` is reused across all books in a genre run.

---

## 6. Diary Ingest Pipeline

Runs for genres marked `"pipeline": "diary"` in `corpus/genres.json` (currently: **diaries**).

```
book_dir/<slug>.md
      │
      │  Step 1 — GutenbergDiaryParser
      │  parse()  → ParsedEntry(timestamp, content, source_line)
      │    • skips preamble before first ALL-CAPS MONTH YEAR header
      │    • bracket-depth tracking prevents date matches inside [footnotes]
      │    • strict punctuation guard ("March 25th to the following…" ignored)
      │    • continuation entries ("2nd.") carry forward current month
      │  write_psv() → TIMESTAMP | diary | prose | CONTENT
      │
      ├──► .diary_source.psv
      │
      │  Step 2 — DiaryTransformer.ingest_to_corpus()
      │    chunking_strategy    : sentence_group (3 sentences/chunk)
      │    batch_size           : 0  (all entries, no sub-sampling)
      │    max_chunks_per_entry : 0  (unlimited)
      │    per chunk → entry_NNNN_chunk_M.md with YAML frontmatter:
      │      timestamp, category, context, topics
      │
      ├──► .diary/entry_0001_chunk_0.md
      ├──► .diary/entry_0001_chunk_1.md
      ├──► .diary/…
      │
      │  Step 3 — DocKG(.diary/)
      │    build_graph() / build_embeddings() / build_index_from_cache()
      │
      └──► .diary/.dockg/graph.sqlite
           .diary/.dockg/lancedb/

KGRAG registration points to .diary/.dockg/ (not book_dir/.dockg/).
```

---

## 7. Genre Registry & Pipeline Routing

`corpus/genres.json` is the single source of truth:

```json
{
  "gutenberg": ["ancient-classical", "shakespeare", "…", "diaries"],
  "ia": ["audel-electric"],
  "pipelines": {
    "diaries": "diary"
  }
}
```

`genres.py` exports: `GUTENBERG_GENRES`, `IA_GENRES`, `ALL_GENRES`, `PIPELINE_GENRES`, `get_pipeline(genre)`.

To add a diary-style genre:

```bash
gutenkg genres add my-diaries --source gutenberg
# then add "my-diaries": "diary" to corpus/genres.json → "pipelines"
```

---

## 8. Output Layout

```
corpus/
├── genres.json
├── <genre>/
│   └── <Book Title>/
│       ├── <slug>.md
│       ├── reference.md
│       └── .dockg/               — gitignored
│           ├── graph.sqlite
│           └── lancedb/
├── diaries/
│   └── <Diary Title>/
│       ├── <slug>.md
│       ├── reference.md
│       ├── .diary_source.psv     — gitignored
│       └── .diary/               — gitignored
│           ├── entry_0001_chunk_0.md
│           ├── …
│           └── .dockg/
│               ├── graph.sqlite
│               └── lancedb/
└── authors/
    ├── index.md
    └── <author_slug>/author.md
```

---

## 9. Batch Download

Catalog files in [`scripts/catalogs/`](../scripts/catalogs/):

```
# Column 1: Gutenberg ID  Column 2: title override  Column 3: genre override
# Lines starting with # are comments
41218    The Diary of John Evelyn — Volume 1
42081    The Diary of John Evelyn — Volume 2
5826     The Diary and Letters of Madame D'Arblay — Volume 1
```

---

## 10. Failure Modes

| Failure | Behavior |
|---|---|
| OPDS 404 / network error | Returns `{"ebook_id": id}`; title falls back to `Book_<id>` |
| RDF 404 / network error | Book downloads; Born/Died/Wikipedia missing from reference |
| Plain-text 404 | Raises after 3 retries; CLI reports error per book |
| START/END markers missing | Full text kept (including Gutenberg header) |
| No dated entries parsed | Diary pipeline raises `ValueError`; book marked failed |
| `diary_transformer` not installed | `ModuleNotFoundError`; install via `kgdeps` extra |
| Corrupt/empty graph.sqlite | Auto-wiped and rebuilt on next ingest run |
| Already built | Skipped unless `--force-build` |

---

## 11. Adding Books

```bash
# Single book
gutenkg download book 2701 --genre american-literature
gutenkg ingest --genre american-literature

# Batch
gutenkg download catalog scripts/catalogs/diaries.txt --genre diaries
gutenkg ingest --genre diaries

# Find then download a diary
gutenkg download search --author "John Evelyn"
gutenkg download book 41218 --genre diaries
gutenkg ingest --genre diaries
```
