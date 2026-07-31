# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""
KGRAG handler — GutenbergKG corpus.

Serves semantic search over the full Project Gutenberg corpus baked into this
image at /workspace/gutenberg/:
  .dockg/            — consolidated DocKG (241 books, 20 genres, 1.3M nodes)
  diaries/*/diarykg/ — 4 DiaryKG temporal indices (Pepys, Evelyn, Boswell)

Implements the RunPod serverless API (--rp_serve_api) so it can be driven by
the Chat.py Streamlit UI, curl, or any compatible HTTP client.

Volume layout (baked in at build time)
---------------------------------------
  /workspace/gutenberg/
    .dockg/
      graph.sqlite
      lancedb/
      catalog.json
    diaries/
      <name>/.diarykg/
        graph.sqlite
        lancedb/

Environment variables
---------------------
GUTENBERG_ROOT     Root of the baked-in bundle.   Default: /workspace/gutenberg
EMBED_MODEL        Sentence-transformer model ID.  Default: BAAI/bge-small-en-v1.5
HANDLER_SECRET     Optional shared secret.  Requests must include {"secret": "<value>"}.
VLLM_ENDPOINT_URL  Optional OpenAI-compatible endpoint for synthesis (oMLX/Ollama/vLLM).
VLLM_API_KEY       Bearer token for the synthesis endpoint.  Omit for Ollama.
VLLM_MODEL         Model ID.  Default: Qwen3-8B-MLX-4bit
SYNTH_MAX_K        Max snippets fed to synthesis.  Default: 12

Request schema
--------------
{
  "query":          str   — natural-language query (required)
  "secret":         str   — required when HANDLER_SECRET is set
  "corpus":         str   — "all" | "gutenberg" | "diary" | <genre>  (default: "all")
                            <genre> is any genre name, e.g. "philosophy", "sacred-texts"
  "k":              int   — top-k hits  (default: 8)
  "min_score":      float — drop hits below this score  (default: 0.0)
  "semantic_floor": float — discard KG if best hit is below this  (default: 0.0)
  "synthesize":     bool  — call vLLM for a generated answer  (default: false)
  "model":          str   — override VLLM_MODEL for this request
  "op":             str   — "models" returns {"models": [...], "default": ...}
                            "stats" returns {"books", "genres", "diaries", "nodes", "edges", "embed_model"}
                            "list_genres" returns [{"genre", "book_count"}, ...]
                            "list_books" (needs "genre") returns its books
                            "get_chapters" (needs "genre", "book") returns its chapter list
                            "get_chapter" (needs "genre", "book", "section_id") returns chapter text
}
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from kg_utils.retrieval import attach_content_by_sqlite
from kg_utils.synthesis import (
    image_synth_for_backend,
    image_synthesizer_from_env,
    text_synth_for_backend,
    text_synthesizer_from_env,
)
from kg_utils.worker import handle_aux_ops

import runpod
from gutenberg_kg.diary_meta import DIARY_META as _DIARY_META
from gutenberg_kg.diary_meta import diary_slug as _diary_slug
from gutenberg_kg.vector_store import resolve_vector_paths

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GUTENBERG_ROOT = Path(os.environ.get("GUTENBERG_ROOT", "/workspace/gutenberg"))
REGISTRY_PATH = Path("/tmp/gutenberg_worker/registry.sqlite")
SYNTH_MAX_K = int(os.environ.get("SYNTH_MAX_K", "12"))
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
HANDLER_SECRET = os.environ.get("HANDLER_SECRET", "")

_DOCKG_SQLITE = GUTENBERG_ROOT / ".dockg" / "graph.sqlite"
_CATALOG_PATH = GUTENBERG_ROOT / ".dockg" / "catalog.json"
# Metadata columns the sqlite-vec store carries (matches doc_kg's index).
_VEC_META = ("kind", "name", "title", "file_path")
_DIARIES_ROOT = GUTENBERG_ROOT / "diaries"

# Valid genre names, populated from catalog.json at startup (see _load_catalog).
# Derived from the live corpus rather than hardcoded, so newly-added genres are
# accepted as corpus filters without touching this file.
_ALL_GENRES: set[str] = set()

# Populated at startup: kg_name → sqlite path (for _attach_content lookups).
_KG_SQLITE: dict[str, Path] = {}

# Populated at startup: the consolidated DocKG LanceDB table, used by the
# semantic-first retrieval path (pure cosine ranking, no graph-hop expansion).
_DOCKG_TABLE = None

# Populated at startup: diary slug → its DiaryKG LanceDB table, so diaries share
# the same true-cosine scoring as the books (no orchestrator hop-expansion).
_DIARY_TABLES: dict = {}

# Populated at startup: a GraphStore over the consolidated DocKG SQLite, used for
# the FTS5/BM25 lexical retrieval channel that is fused with dense cosine search
# via reciprocal rank fusion (RRF).  None when the corpus has no lexical index,
# in which case retrieval degrades to pure dense ranking.
_DOCKG_STORE = None

# Populated on first use: a plain GraphStore for chapter/section reads (Browse
# page), independent of the FTS gate on _DOCKG_STORE above.
_DOCKG_STORE_RO = None

# RRF constant — matches doc_kg's _fused_seeds so the handler and library blend
# dense + lexical ranks on the same scale.
_RRF_K = 60

# Populated at startup: "<genre>/<book>" → {title, author, genre, ...}
_catalog: dict[str, dict] = {}

# Static metadata for diary KGs (not in catalog.json, which covers prose/verse only).

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def _source_file_for(diary_dir: Path) -> str:
    """Look up a diary's original source filename from its DiaryKG config.

    :param diary_dir: Diary directory containing a ``.diarykg/`` subdirectory.
    :returns: The recorded ``source_file`` value, or ``""`` if unavailable.
    """
    config = diary_dir / ".diarykg" / "config.json"
    if config.exists():
        return json.loads(config.read_text()).get("source_file", "")
    return ""


def _bootstrap_registry():
    """Register the consolidated DocKG and every DiaryKG in the KGRegistry at startup.

    Populates the module-level ``_KG_SQLITE`` and ``_DIARY_TABLES`` caches as a
    side effect, opening each diary's LanceDB table for semantic-first search.

    :returns: The populated ``KGRegistry`` instance.
    """
    from kg_rag.corpus_registry import CorpusRegistry
    from kg_rag.primitives import CorpusEntry, KGEntry, KGKind
    from kg_rag.registry import KGRegistry

    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    reg = KGRegistry(db_path=REGISTRY_PATH)
    corp_reg = CorpusRegistry(db_path=REGISTRY_PATH)

    # --- DocKG (consolidated prose + verse) ---
    if not _DOCKG_SQLITE.exists():
        print(f"[bootstrap] WARNING: DocKG not found at {_DOCKG_SQLITE}")
        print("[bootstrap]   Run 'gutenkg build-corpus' then rebuild the image.")
    else:
        # Register whichever store is actually on disk, on the same precedence
        # _open_vector_source reads with — previously this hardcoded the LanceDB
        # dir, recording it even when only vectors.sqlite existed.
        _vectors, _lancedb = resolve_vector_paths(GUTENBERG_ROOT / ".dockg")
        entry = KGEntry(
            id=str(uuid.uuid4()),
            name="gutenberg",
            kind=KGKind.GUTENBERG,
            repo_path=GUTENBERG_ROOT,
            venv_path=Path("/usr"),
            sqlite_path=_DOCKG_SQLITE,
            vectors_path=_vectors,
            lancedb_path=_lancedb,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        reg.register(entry)
        _KG_SQLITE["gutenberg"] = _DOCKG_SQLITE
        print(f"[bootstrap] registered gutenberg dockg ({_DOCKG_SQLITE})")

    # --- DiaryKG indices (one per diary) ---
    corp_reg.create(CorpusEntry(name="diaries", description="Project Gutenberg — diary corpora"))
    n_diaries = 0
    if _DIARIES_ROOT.exists():
        for diary_dir in sorted(_DIARIES_ROOT.iterdir()):
            if not diary_dir.is_dir() or diary_dir.name.startswith("."):
                continue
            diarykg_dir = diary_dir / ".diarykg"
            sqlite = diarykg_dir / "graph.sqlite"
            # diary-kg >=0.94.0 writes vectors.sqlite here and no longer creates
            # lancedb/, so registering the latter unconditionally left the entry
            # pointing at a directory that does not exist.
            vectors, lancedb = resolve_vector_paths(diarykg_dir)
            if not sqlite.exists():
                print(f"[bootstrap] skipping {diary_dir.name} — no .diarykg/graph.sqlite")
                continue
            slug = _diary_slug(diary_dir.name)
            entry = KGEntry(
                id=str(uuid.uuid4()),
                name=slug,
                kind=KGKind.DIARY,
                repo_path=diary_dir,
                venv_path=Path("/usr"),
                sqlite_path=sqlite,
                vectors_path=vectors,
                lancedb_path=lancedb,
                metadata={"source_file": _source_file_for(diary_dir)},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            reg.register(entry)
            corp_reg.add_kg("diaries", entry.id)
            _KG_SQLITE[slug] = sqlite
            # Open the diary's vector store (sqlite-vec preferred, LanceDB fallback).
            try:
                src = _open_vector_source(diarykg_dir, label=f"diary {slug}")
                if src is not None:
                    _DIARY_TABLES[slug] = src
            except Exception as exc:  # noqa: BLE001
                print(f"[bootstrap] WARNING: could not open diary store {slug}: {exc}")
            n_diaries += 1
            print(f"[bootstrap] registered diary: {slug}")
    else:
        print("[bootstrap] no diaries/ directory found")
    print(f"[bootstrap] diaries corpus: {n_diaries} KG(s)")

    return reg


def _open_vector_source(dockg_dir, *, label: str):
    """Open a vector source for a ``.dockg`` dir — sqlite-vec if present, else LanceDB.

    Prefers the exact ``vectors.sqlite`` store (see the sqlite-vec migration);
    falls back to the LanceDB ``dockg_nodes`` table for un-converted corpora, so
    the worker keeps serving during the transition.

    :param dockg_dir: The ``.dockg`` directory holding ``vectors.sqlite`` / ``lancedb``.
    :param label: Human label for startup logging.
    :returns: A ``SqliteVecBackend`` or an open LanceDB table, or ``None``.
    """
    vectors = dockg_dir / "vectors.sqlite"
    lancedb_dir = dockg_dir / "lancedb"
    if vectors.exists():
        from kg_utils.vector_backend import SqliteVecBackend

        be = SqliteVecBackend(vectors, dim=384, meta_columns=_VEC_META, check_same_thread=False)
        be.open(wipe=False)
        print(f"[startup] {label}: sqlite-vec store ({be.count()} vectors)")
        return be
    if lancedb_dir.exists():
        import lancedb

        db = lancedb.connect(str(lancedb_dir))
        names = list(db.table_names())
        table = "dockg_nodes" if "dockg_nodes" in names else (names[0] if names else None)
        if table is None:
            print(f"[startup] WARNING: no lancedb table in {lancedb_dir}")
            return None
        tbl = db.open_table(table)
        print(f"[startup] {label}: LanceDB table {table} ({tbl.count_rows()} rows)")
        return tbl
    print(f"[startup] WARNING: no vector store for {label} in {dockg_dir}")
    return None


def _open_dockg_table() -> None:
    """Open the consolidated DocKG vector store (sqlite-vec preferred)."""
    global _DOCKG_TABLE
    _DOCKG_TABLE = _open_vector_source(GUTENBERG_ROOT / ".dockg", label="DocKG")


def _open_dockg_store() -> None:
    """Open the consolidated DocKG SQLite for FTS5/BM25 lexical search.

    The lexical channel only activates when the corpus carries a ``nodes_fts``
    index (built by ``dockg reindex-fts`` / a recent ``dockg build``).  When it
    is absent the store stays ``None`` and retrieval falls back to pure dense
    cosine ranking, so older corpora keep working unchanged.
    """
    global _DOCKG_STORE
    if not _DOCKG_SQLITE.exists():
        return
    try:
        from doc_kg.store import GraphStore

        store = GraphStore(_DOCKG_SQLITE)
        if not store.has_fts():
            print(
                f"[startup] WARNING: no FTS5 index in {_DOCKG_SQLITE}; lexical "
                "channel disabled (run 'dockg reindex-fts' or rebuild the corpus)"
            )
            store.close()
            return
        _DOCKG_STORE = store
        print("[startup] opened DocKG lexical (FTS5) index — hybrid retrieval enabled")
    except Exception as exc:  # noqa: BLE001 — degrade to dense-only on any error
        print(f"[startup] WARNING: could not open DocKG lexical store: {exc}")


def _load_catalog() -> None:
    """Load ``catalog.json`` into the module-level ``_catalog`` dict, if present."""
    if _CATALOG_PATH.exists():
        with open(_CATALOG_PATH, encoding="utf-8") as f:
            _catalog.update(json.load(f))
        _ALL_GENRES.update(m["genre"] for m in _catalog.values() if m.get("genre"))
        print(f"[startup] loaded catalog: {len(_catalog)} books, {len(_ALL_GENRES)} genres")
    else:
        print(f"[startup] WARNING: catalog.json not found at {_CATALOG_PATH}")


def _make_embedder():
    """Load the sentence-transformer embedder and warm it up with a dummy embed call.

    :returns: A ready-to-use ``SentenceTransformerEmbedder`` instance.
    """
    from kg_rag._embedders import SentenceTransformerEmbedder

    print(f"[startup] loading embedder: {EMBED_MODEL}")
    emb = SentenceTransformerEmbedder(EMBED_MODEL)
    emb.embed_texts(["warm up"])
    print("[startup] embedder ready")
    return emb


print("[startup] bootstrapping registry ...")
_registry = _bootstrap_registry()

print("[startup] loading catalog ...")
_load_catalog()

print("[startup] loading embedder ...")
_embedder = _make_embedder()

print("[startup] opening DocKG vector table ...")
_open_dockg_table()

print("[startup] opening DocKG lexical index ...")
_open_dockg_store()

print("[startup] initialising synthesis backends ...")
_text_synth = text_synthesizer_from_env()
_image_synth = image_synthesizer_from_env()
print("[startup] ready")


# ---------------------------------------------------------------------------
# Per-request backend factory
# ---------------------------------------------------------------------------


def _synth_for_backend(backend_str: str):
    """Resolve the text synthesizer to use for a request, falling back to the env default.

    :param backend_str: Backend name requested by the caller (e.g. ``"ollama"``), or ``""``.
    :returns: A text synthesizer instance for the resolved backend.
    """
    return text_synth_for_backend(backend_str, _text_synth)


def _image_for_backend(backend_str: str):
    """Resolve the image synthesizer to use for a request, falling back to the env default.

    :param backend_str: Backend name requested by the caller (e.g. ``"openai"``), or ``""``.
    :returns: An image synthesizer instance for the resolved backend.
    """
    return image_synth_for_backend(backend_str, _image_synth)


# ---------------------------------------------------------------------------
# Hit serialisation
# ---------------------------------------------------------------------------


def _attach_content(hits: list[dict]) -> None:
    """Fetch full node text from the appropriate SQLite for each hit."""
    attach_content_by_sqlite(hits, _KG_SQLITE)


def _table_search(table, qvec, where: str, k: int) -> list[dict]:
    """Run a cosine kNN search with a pre-filter; returns rows with ``_distance``.

    Dispatches on the store type. The sqlite-vec backend is exact (recall 1.0)
    and its ``where`` compiles to a true rowid-subquery prefilter. The LanceDB
    path keeps the ``nprobes(128)`` stopgap that lifts IvfFlat recall@10 from
    ~0.825 to ~0.99 (benchmarks/SQLITE_VEC_RESULTS.md).
    """
    from kg_utils.vector_backend import SqliteVecBackend

    if isinstance(table, SqliteVecBackend):
        return table.search(qvec, k, where=where)
    return (
        table.search(qvec)
        .metric("cosine")
        .where(where, prefilter=True)
        .nprobes(128)
        .limit(k)
        .to_list()
    )


def _rrf_fuse(dense_ids: list[str], lex_ids: list[str], k: int) -> list[str]:
    """Blend dense and lexical rank lists with reciprocal rank fusion (RRF).

    Each channel contributes ``1 / (_RRF_K + rank)`` to a node's score, so a
    chunk ranked highly by *either* cosine or BM25 floats up, while a chunk
    ranked by both wins decisively.  This is what lets exact-term matches the
    dense embedder buries (e.g. "Hell" in Dante's *Inferno*) seed the answer.

    :param dense_ids: Node IDs ordered best-first by cosine distance.
    :param lex_ids: Node IDs ordered best-first by BM25 lexical score.
    :param k: Number of fused IDs to return.
    :returns: Node IDs ordered best-first by fused RRF score.
    """
    scores: dict[str, float] = {}
    for rank, nid in enumerate(dense_ids):
        scores[nid] = scores.get(nid, 0.0) + 1.0 / (_RRF_K + rank)
    for rank, nid in enumerate(lex_ids):
        scores[nid] = scores.get(nid, 0.0) + 1.0 / (_RRF_K + rank)
    return sorted(scores, key=lambda i: -scores[i])[:k]


def _rows_to_hits(rows: list[dict], kg_name: str, kg_kind: str, min_score: float) -> list[dict]:
    """Shape LanceDB rows into hit dicts (clean content hydrated separately).

    The LanceDB ``text`` column holds the structured *embed-text* (``KIND:/TITLE:/
    FILE:/TEXT:`` prefixed), not the clean passage — so ``content``/``summary`` are
    left empty here and filled from SQLite by ``_attach_content`` / ``_attach_diary_fields``.
    """
    hits: list[dict] = []
    for row in rows:
        score = round(1.0 - float(row.get("_distance", 1.0)), 4)
        if score < min_score:
            continue
        hits.append(
            {
                "kg_name": kg_name,
                "kg_kind": kg_kind,
                "node_id": row.get("id"),
                "name": row.get("name") or row.get("title") or "",
                "kind": row.get("kind", "chunk"),
                "score": score,
                "summary": "",
                "source_path": row.get("file_path") or "",
                "content": "",
                "timestamp": None,
            }
        )
    return hits


def _attach_diary_fields(hits: list[dict]) -> None:
    """Hydrate clean passage text and temporal ``timestamp`` from diary SQLite."""
    by_kg: dict[str, list[dict]] = defaultdict(list)
    for h in hits:
        by_kg[h.get("kg_name", "")].append(h)
    for slug, kg_hits in by_kg.items():
        db_path = _KG_SQLITE.get(slug)
        if not db_path or not Path(db_path).exists():
            continue
        ids = [h["node_id"] for h in kg_hits if h.get("node_id")]
        if not ids:
            continue
        field_by_id: dict[str, tuple[str, str | None]] = {}
        try:
            with sqlite3.connect(str(db_path)) as con:
                placeholders = ",".join("?" * len(ids))
                rows = con.execute(
                    f"SELECT id, text, timestamp FROM nodes WHERE id IN ({placeholders})", ids
                )
                for nid, text, ts in rows:
                    field_by_id[nid] = (text or "", ts)
        except Exception:  # noqa: BLE001
            continue
        for h in kg_hits:
            text, ts = field_by_id.get(h.get("node_id", ""), ("", None))
            h["content"] = text
            h["summary"] = text
            h["timestamp"] = ts


def _semantic_search(
    query: str,
    k: int,
    min_score: float = 0.0,
    semantic_floor: float = 0.0,
    genre_filter: str | None = None,
) -> list[dict]:
    """Hybrid (dense + lexical) search over the consolidated DocKG.

    Ranks every chunk/section by its *own* relevance to the query — no graph-hop
    expansion, so a query that names a book surfaces that book's passages on top
    instead of letting them inherit a flat seed score from a few graph-expanded
    neighbours.  Two channels run over the same in-scope subset and are blended
    with reciprocal rank fusion:

    * **dense** — cosine kNN over the LanceDB vector table;
    * **lexical** — FTS5/BM25 over the SQLite ``nodes_fts`` index.

    The lexical channel recovers exact-term hits that the embedder buries — e.g.
    "circles of Hell" drifts semantically toward Dante's geometric *Paradiso*,
    while BM25 pins the literal *Inferno* passages.  When no lexical index is
    present (``_DOCKG_STORE is None``) the search degrades to pure dense ranking.
    Content-kind and genre filters are pushed into *both* channels so the top-k
    is computed over the eligible subset.

    :param query: Natural-language query string.
    :param k: Number of hits to return.
    :param min_score: Drop hits whose cosine similarity is below this.
    :param semantic_floor: If the best *dense* hit is below this, discard the set.
    :param genre_filter: Restrict to a single genre subtree (e.g. ``sacred-texts``).
    :returns: Hit dictionaries ranked best-first, shaped like ``hit_to_dict``.
    """
    if _DOCKG_TABLE is None:
        return []
    qvec = _embedder.embed_texts([query])[0]
    where = "kind IN ('chunk', 'section') AND file_path NOT LIKE '%reference.md'"
    if genre_filter:
        # genre_filter is validated against _ALL_GENRES before this call.
        where += f" AND file_path LIKE '{genre_filter}/%'"

    # Dense channel — oversample so RRF has rank headroom for the lexical blend.
    dense_rows = _table_search(_DOCKG_TABLE, qvec, where, k * 3)

    # Lexical channel — BM25 over the same genre/kind-scoped subset (pushed down
    # into the FTS5 SQL), returning chunk IDs ordered best-first.
    lex_ids: list[str] = []
    if _DOCKG_STORE is not None:
        try:
            lex_ids = _DOCKG_STORE.search_lexical(
                query,
                limit=k * 3,
                file_prefixes=[f"{genre_filter}/"] if genre_filter else None,
                node_kinds=("chunk", "section"),
            )
        except Exception as exc:  # noqa: BLE001 — degrade to dense-only on any error
            print(f"[query] WARNING: lexical search failed, dense-only: {exc}")

    row_by_id: dict[str, dict] = {r["id"]: r for r in dense_rows}
    if lex_ids:
        # Hydrate cosine rows for lexical-only IDs so every fused hit carries an
        # honest cosine score and stays inside the genre/kind scope.
        missing = [i for i in lex_ids if i and i not in row_by_id]
        if missing:
            id_list = ", ".join("'" + i.replace("'", "''") + "'" for i in missing)
            lex_rows = _table_search(
                _DOCKG_TABLE, qvec, f"{where} AND id IN ({id_list})", len(missing)
            )
            for r in lex_rows:
                row_by_id.setdefault(r["id"], r)
        lex_ids = [i for i in lex_ids if i in row_by_id]  # drop out-of-scope IDs
        ordered_ids = _rrf_fuse([r["id"] for r in dense_rows], lex_ids, k)
        ordered_rows = [row_by_id[i] for i in ordered_ids]
    else:
        ordered_rows = dense_rows[:k]

    hits = _rows_to_hits(ordered_rows, "gutenberg", "KGKind.GUTENBERG", min_score)
    _attach_content(hits)  # clean passage text from SQLite
    for h in hits:
        h["summary"] = h.get("content", "")
    # The semantic floor gauges whether the KG is relevant at all, so test it
    # against the best *dense* cosine (the lexical channel can surface a literal
    # match with modest cosine that should not, by itself, keep a stale set).
    if semantic_floor > 0.0:
        best_dense = round(1.0 - float(dense_rows[0]["_distance"]), 4) if dense_rows else 0.0
        if best_dense < semantic_floor:
            return []
    return hits


def _semantic_search_diaries(
    query: str,
    k: int,
    min_score: float = 0.0,
    semantic_floor: float = 0.0,
) -> list[dict]:
    """Pure cosine search across the DiaryKG vector tables, merged by score.

    Gives diaries the same true-cosine scoring as the books, so a unified
    (``all``) query ranks both corpora on one comparable scale instead of letting
    the diaries' graph-expanded plateau scores dominate.

    :param query: Natural-language query string.
    :param k: Number of hits to return across all diaries.
    :param min_score: Drop hits whose cosine similarity is below this.
    :param semantic_floor: If the best hit is below this, discard the whole set.
    :returns: Hit dictionaries ranked best-first across all diary KGs.
    """
    if not _DIARY_TABLES:
        return []
    qvec = _embedder.embed_texts([query])[0]
    where = "kind IN ('chunk', 'section')"
    hits: list[dict] = []
    for slug, table in _DIARY_TABLES.items():
        rows = _table_search(table, qvec, where, k)
        hits.extend(_rows_to_hits(rows, slug, "KGKind.DIARY", min_score))
    hits.sort(key=lambda h: h["score"], reverse=True)
    hits = hits[:k]
    _attach_diary_fields(hits)  # clean text + timestamp from each diary's SQLite
    if semantic_floor > 0.0 and hits and hits[0]["score"] < semantic_floor:
        return []
    return hits


def _dockg_store_ro():
    """Return a ``GraphStore`` for read-only node lookups (chapters/sections).

    Reuses ``_DOCKG_STORE`` if the FTS-gated lexical channel already opened one;
    otherwise lazily opens and caches a plain store, since chapter/section reads
    don't require an FTS5 index.

    :returns: An open ``GraphStore``, or ``None`` if the DocKG SQLite is missing.
    """
    global _DOCKG_STORE_RO
    if _DOCKG_STORE is not None:
        return _DOCKG_STORE
    if _DOCKG_STORE_RO is None and _DOCKG_SQLITE.exists():
        from doc_kg.store import GraphStore

        _DOCKG_STORE_RO = GraphStore(_DOCKG_SQLITE)
    return _DOCKG_STORE_RO


def _resolve_book_file_path(genre: str, book: str) -> str | None:
    """Look up the content ``.md`` file path for a ``<genre>/<book>`` pair.

    Each book directory has exactly one content document plus a ``reference.md``;
    this is a single prefix lookup that ``GraphStore.query_nodes`` doesn't support
    directly (it only matches ``file_path`` exactly), so it stays raw SQL.

    :param genre: Genre slug, e.g. ``"american-literature"``.
    :param book: Book directory name, e.g. ``"Adventures of Huckleberry Finn"``.
    :returns: The node ``file_path`` for the book's content document, or ``None``.
    """
    store = _dockg_store_ro()
    if store is None:
        return None
    row = store.con.execute(
        "SELECT file_path FROM nodes WHERE kind='document' AND file_path LIKE ? "
        "AND file_path NOT LIKE '%reference.md' LIMIT 1",
        (f"{genre}/{book}/%",),
    ).fetchone()
    return row[0] if row else None


def _list_genres() -> dict:
    """List every genre in ``catalog.json`` with its book count.

    :returns: ``{"genres": [{"genre": ..., "book_count": ...}, ...]}``, sorted by genre.
    """
    counts: dict[str, int] = defaultdict(int)
    for meta in _catalog.values():
        counts[meta.get("genre", "")] += 1
    genres = [{"genre": genre, "book_count": count} for genre, count in sorted(counts.items())]
    return {"genres": genres}


def _corpus_stats() -> dict:
    """Return live corpus totals for the chat UI header (no hardcoded counts).

    Books and genres come from ``catalog.json``; node/edge totals from the
    consolidated ``graph.sqlite``; diary count from the registered DiaryKG
    tables. Returns zeros for any store that can't be opened.

    :returns: ``{"books", "genres", "diaries", "nodes", "edges", "embed_model"}``.
    """
    genres = {meta.get("genre", "") for meta in _catalog.values() if meta.get("genre")}
    nodes = edges = 0
    if _DOCKG_SQLITE.exists():
        try:
            with sqlite3.connect(_DOCKG_SQLITE) as con:
                nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        except sqlite3.Error:
            pass
    return {
        "books": len(_catalog),
        "genres": len(genres),
        "diaries": len(_DIARY_TABLES),
        "nodes": nodes,
        "edges": edges,
        "embed_model": EMBED_MODEL,
    }


def _list_books(genre: str) -> dict:
    """List every book in a genre from ``catalog.json``.

    :param genre: Genre slug to filter by.
    :returns: ``{"genre": ..., "books": [{"book", "title", "author", "ebook_id"}, ...]}``.
    """
    books = [
        {
            "book": meta.get("book"),
            "title": meta.get("title"),
            "author": meta.get("author"),
            "ebook_id": meta.get("ebook_id"),
        }
        for meta in _catalog.values()
        if meta.get("genre") == genre
    ]
    books.sort(key=lambda b: b.get("title") or "")
    return {"genre": genre, "books": books}


def _get_chapters(genre: str, book: str) -> dict:
    """List a book's chapters (from ``section`` nodes, or ``chunk.chapter`` as fallback).

    :param genre: Genre slug.
    :param book: Book directory name.
    :returns: ``{"book", "chapters": [{"id", "title", "index"}, ...]}``, or an
        ``"error"`` key if the book/store can't be resolved.
    """
    store = _dockg_store_ro()
    if store is None:
        return {"error": "DocKG store unavailable"}
    file_path = _resolve_book_file_path(genre, book)
    if file_path is None:
        return {"error": f"book not found: {genre}/{book}"}

    sections = store.query_nodes(kinds=["section"], file_path=file_path)
    if sections:
        chapters = [
            {"id": s["id"], "title": s.get("title") or s.get("name"), "index": i}
            for i, s in enumerate(sections)
        ]
        return {"book": book, "chapters": chapters}

    # Verse-chunked genres (sacred-texts) may carry no section nodes — fall back
    # to grouping chunks by their `chapter` column.
    chunks = store.query_nodes(kinds=["chunk"], file_path=file_path)
    seen_chapters: list[int] = []
    for c in chunks:
        ch = c.get("chapter")
        if ch is not None and ch not in seen_chapters:
            seen_chapters.append(ch)
    chapters = [
        {"id": f"chapter:{ch}", "title": f"Chapter {ch}", "index": i}
        for i, ch in enumerate(seen_chapters)
    ]
    return {"book": book, "chapters": chapters}


def _get_chapter(genre: str, book: str, section_id: str) -> dict:
    """Reconstruct one chapter's text by concatenating its chunks in order.

    :param genre: Genre slug.
    :param book: Book directory name.
    :param section_id: A chapter id from :func:`_get_chapters` — either a
        ``section`` node id, or a synthetic ``"chapter:<n>"`` id from the
        chunk-grouping fallback.
    :returns: ``{"title", "text", "index", "total", "prev_id", "next_id"}``, or
        an ``"error"`` key if the book/section can't be resolved.
    """
    store = _dockg_store_ro()
    if store is None:
        return {"error": "DocKG store unavailable"}
    file_path = _resolve_book_file_path(genre, book)
    if file_path is None:
        return {"error": f"book not found: {genre}/{book}"}

    sections = store.query_nodes(kinds=["section"], file_path=file_path)
    if sections:
        index = next((i for i, s in enumerate(sections) if s["id"] == section_id), None)
        if index is None:
            return {"error": f"unknown section: {section_id}"}
        start = sections[index]["char_start"]
        end = sections[index + 1]["char_start"] if index + 1 < len(sections) else None
        chunks = store.query_nodes(kinds=["chunk"], file_path=file_path)
        text = "\n\n".join(
            c["text"]
            for c in chunks
            if c["char_start"] >= start and (end is None or c["char_start"] < end)
        )
        return {
            "title": sections[index].get("title") or sections[index].get("name"),
            "text": text,
            "index": index,
            "total": len(sections),
            "prev_id": sections[index - 1]["id"] if index > 0 else None,
            "next_id": sections[index + 1]["id"] if index + 1 < len(sections) else None,
        }

    # Chunk-grouping fallback (verse-chunked genres).
    if not section_id.startswith("chapter:"):
        return {"error": f"unknown section: {section_id}"}
    chapter_num = int(section_id.split(":", 1)[1])
    chunks = store.query_nodes(kinds=["chunk"], file_path=file_path)
    seen_chapters: list[int] = []
    for c in chunks:
        ch = c.get("chapter")
        if ch is not None and ch not in seen_chapters:
            seen_chapters.append(ch)
    if chapter_num not in seen_chapters:
        return {"error": f"unknown chapter: {chapter_num}"}
    index = seen_chapters.index(chapter_num)
    text = "\n\n".join(c["text"] for c in chunks if c.get("chapter") == chapter_num)
    prev_ch = seen_chapters[index - 1] if index > 0 else None
    next_ch = seen_chapters[index + 1] if index + 1 < len(seen_chapters) else None
    return {
        "title": f"Chapter {chapter_num}",
        "text": text,
        "index": index,
        "total": len(seen_chapters),
        "prev_id": f"chapter:{prev_ch}" if prev_ch is not None else None,
        "next_id": f"chapter:{next_ch}" if next_ch is not None else None,
    }


def _enrich_catalog(hits: list[dict]) -> None:
    """Join author/title/genre from catalog.json onto DocKG hits."""
    for h in hits:
        if h.get("kg_kind") in ("KGKind.GUTENBERG", "gutenberg"):
            src = h.get("source_path", "")
            parts = src.split("/")
            if len(parts) >= 2:
                key = f"{parts[0]}/{parts[1]}"
                meta = _catalog.get(key, {})
                h["genre"] = meta.get("genre") or parts[0]
                h["title"] = meta.get("title") or parts[1]
                h["author"] = meta.get("author")
        # Diary hits: fall back to static map keyed by slug.
        diary = _DIARY_META.get(h.get("kg_name", ""))
        if diary and not h.get("author"):
            h["genre"] = diary["genre"]
            h["title"] = diary["title"]
            h["author"] = diary["author"]


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handler(job: dict) -> dict:
    """RunPod serverless entry point: search the corpus and optionally synthesise an answer.

    :param job: RunPod job dict; ``job["input"]`` holds the request schema described
        in this module's docstring (query, corpus, k, min_score, semantic_floor,
        synthesize, model, secret, op).
    :returns: A result dict with hits, timing, and optional synthesis text, or
        ``{"error": ...}`` on validation/auth failure.
    """
    inp = job.get("input", {})

    if HANDLER_SECRET and inp.get("secret") != HANDLER_SECRET:
        return {"error": "unauthorized"}

    aux_result = handle_aux_ops(inp, _synth_for_backend, _image_for_backend)
    if aux_result is not None:
        return aux_result

    op = inp.get("op", "")
    if op == "stats":
        return _corpus_stats()
    if op == "list_genres":
        return _list_genres()
    if op == "list_books":
        return _list_books(inp.get("genre", ""))
    if op == "get_chapters":
        return _get_chapters(inp.get("genre", ""), inp.get("book", ""))
    if op == "get_chapter":
        return _get_chapter(inp.get("genre", ""), inp.get("book", ""), inp.get("section_id", ""))

    query = inp.get("query", "").strip()
    corpus = inp.get("corpus", "all")
    k = max(1, int(inp.get("k", 8)))
    min_score = float(inp.get("min_score", 0.0))
    semantic_floor = float(inp.get("semantic_floor", 0.0))
    synthesize = bool(inp.get("synthesize", False))
    model = (inp.get("model") or "").strip() or None

    if not query:
        return {"error": "query is required"}

    genre_filter: str | None = None
    if corpus in _ALL_GENRES:
        genre_filter = corpus
    elif corpus not in ("all", "diary", "gutenberg"):
        return {
            "error": (
                f"unknown corpus {corpus!r}; choose: all, gutenberg, diary, "
                f"or a genre name ({', '.join(sorted(_ALL_GENRES))})"
            )
        }

    t0_search = time.perf_counter()

    if corpus == "diary":
        # Diaries only — semantic-first across the DiaryKG vector tables.
        hits = _semantic_search_diaries(
            query, k=k, min_score=min_score, semantic_floor=semantic_floor
        )
        _enrich_catalog(hits)
        kgs_queried = len(_DIARY_TABLES)
    else:
        # Semantic-first: rank chunks by their own cosine distance (no graph-hop
        # expansion), so a query that names a book surfaces that book on top.
        hits = _semantic_search(
            query,
            k=k,
            min_score=min_score,
            semantic_floor=semantic_floor,
            genre_filter=genre_filter,
        )
        _enrich_catalog(hits)
        kgs_queried = 1  # the consolidated 'gutenberg' DocKG
        if corpus == "all":
            # Fold in the diaries on the *same* true-cosine scale, then re-rank
            # the merged set by score so neither corpus's scoring dominates.
            dhits = _semantic_search_diaries(
                query, k=k, min_score=min_score, semantic_floor=semantic_floor
            )
            _enrich_catalog(dhits)
            hits = sorted(hits + dhits, key=lambda h: h.get("score", 0.0), reverse=True)[:k]
            kgs_queried += len(_DIARY_TABLES)

    search_ms = (time.perf_counter() - t0_search) * 1000
    print(f"[query] {len(hits)} matching results found in {search_ms:.0f}ms")

    synthesis = None
    synthesis_ms: float | None = None
    active_synth = _synth_for_backend(inp.get("backend", ""))
    if synthesize:
        t0_synth = time.perf_counter()
        synthesis = active_synth.synthesize_rag(query, hits, model=model, max_k=SYNTH_MAX_K)
        synthesis_ms = (time.perf_counter() - t0_synth) * 1000
        print(f"[query] synthesis returned in {synthesis_ms:.0f}ms")

    return {
        "query": query,
        "corpus": corpus,
        "total_hits": len(hits),
        "kgs_queried": kgs_queried,
        "hits": hits,
        "search_ms": round(search_ms),
        "synthesis": synthesis,
        "synthesis_ms": round(synthesis_ms) if synthesis_ms is not None else None,
        "model": (model or active_synth._cfg.resolved_model()) if synthesize else None,
    }


def main() -> None:
    """Start the RunPod serverless worker (``gutenkg-handler`` entry point)."""
    runpod.serverless.start({"handler": handler})


if __name__ == "__main__":
    main()
