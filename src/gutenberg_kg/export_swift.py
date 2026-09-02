# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Build the on-device corpus packs the native app searches locally.

Phase 0 of ``analysis/APP_ARCHITECTURE.md``: turn ``bundles/gutenberg-all/``
— a 2.9 GB DocKG ``graph.sqlite`` plus a 1.1 GB vector store plus four diary
KGs — into three SQLite files small enough to sit on a phone, carrying exactly
what the query path reads and nothing else.

Layout produced
---------------
::

    <out>/
      manifest.json      pack versions, checksums, the embedder the packs require
      core.pack          catalog: genres, books, the Browse entry points
      gutenberg.pack     passages + FTS5 for the 241 books
      gutenberg.vectors  their embeddings, row-major, memory-mappable
      diaries.pack       the same, for the four diaries, with timestamps
      diaries.vectors
      golden.json        reference top-k per query — the Swift parity gate

What is dropped, and why it is safe
-----------------------------------
The served query path (``serve/handler.py:_semantic_search``) is a dense kNN
plus an FTS5/BM25 query plus RRF over ``kind IN ('chunk','section')``, with
content hydrated from SQLite afterwards. It never hops the graph. So the packs
carry chunk and section nodes only: the 324 K topic/entity/keyword nodes, every
edge, and the structured *embed-text* duplicate of each passage all stay behind.
Vectors are re-encoded from fp32 to int8, which is where most of the remaining
size goes.

Why the vectors sit beside the pack, not inside it
--------------------------------------------------
A ``vec0`` virtual table cannot be read without the sqlite-vec C extension
compiled into the reader, and iOS ships stock SQLite — so a pack built that way
would not open on the device it was built for. Vendoring ten thousand lines of C
would buy nothing either: vec0's search is exhaustive, and so is the dot product
the app does instead over a memory-mapped file, with SIMD and no allocation.

The sidecar is therefore a 32-byte header (magic, dtype, dim, count) followed by
row-major vectors. ``passages.vector_index`` is a *dense* row number into it, so
a passage whose vector the source store lacks leaves no hole in the file. The
header lets a reader reject a truncated download instead of interpreting
whatever bytes it finds as embeddings.

Schema notes
------------
Two title columns are deliberate: ``title`` is the *work's* title, which the
hit cards show, while ``node_title`` is the node's own — a section's chapter
name, which the Browse tab lists. Collapsing them loses the chapter list.

The FTS5 index is rebuilt here over *clean* passage text rather than copied,
because the worker's ``nodes_fts`` indexes the embed-text form. Lexical results
will therefore not match the worker's token for token — which is why
``golden.json`` is generated from the pack itself. It is the contract the Swift
engine must reproduce, not a record of what the worker happened to return.

Reading the source
------------------
Column sets differ across the fleet's stores (a diary carries ``timestamp``, a
book carries ``chapter``), and they change as KGs are rebuilt, so every read
here is driven by ``PRAGMA table_info`` rather than a hardcoded ``SELECT``.
Missing columns become ``NULL`` in the pack; they never become a crash three
hundred thousand rows into an export.

Usage
-----
::

    gutenkg export-swift                       # bundles/gutenberg-all → bundles/gutenberg-all/swift
    gutenkg export-swift --dtype float         # fp32 vectors, ~3x larger, exact
    gutenkg export-swift --verify              # measure int8 recall against the source
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "GOLDEN_QUERIES",
    "BundlePaths",
    "DiarySource",
    "ExportError",
    "ExportOptions",
    "ExportReport",
    "PackStats",
    "export_swift",
    "locate_bundle",
]

# --------------------------------------------------------------------------
# Constants — every one of these mirrors something the worker already does.
# --------------------------------------------------------------------------

PACK_VERSION = 1
DEFAULT_BUNDLE = Path("bundles/gutenberg-all")
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384

#: The node kinds ``_semantic_search`` ranks. Nothing else is searchable, so
#: nothing else is shipped.
SEARCHED_KINDS = ("chunk", "section")

#: Reciprocal-rank-fusion constant. Must match ``handler._RRF_K`` and doc_kg's
#: ``_fused_seeds`` or the packs rank differently from the worker.
RRF_K = 60

#: Golden queries for the parity gate — genre coverage plus the known-hard
#: cases (a name the embedder buries, a term that only BM25 finds).
#: ``benchmarks/bench_sqlite_vec.py`` imports this list so the two cannot drift.
GOLDEN_QUERIES: tuple[str, ...] = (
    "pillar of salt",
    "circles of Hell",
    "What does the Quran say about Moses?",
    "the whiteness of the whale",
    "descriptions of the Great Fire of London",
    "the categorical imperative and moral duty",
    "a monster assembled from dead body parts",
    "time travel to the distant future",
    "the fall of the House of Usher",
    "how to wire an electric bell",
    "shipwreck on a desert island",
    "a dinner party with too much wine in a London diary",
)

#: Magic for the vector sidecar. The app refuses a file that does not start
#: with this, rather than reading whatever bytes it finds as embeddings.
VECTOR_MAGIC = b"GKGVEC01"

#: Header bytes before the vector rows. 32 keeps the data 16-byte aligned, so
#: the device can mmap it and hand it straight to SIMD.
VECTOR_HEADER_BYTES = 32

_DTYPE_CODES = {"int8": 0, "float": 1}
_DTYPE_ITEMSIZE = {"int8": 1, "float": 4}

_CORE_SCHEMA = """
CREATE TABLE pack_meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE genres (
  genre      TEXT PRIMARY KEY,
  book_count INTEGER NOT NULL
);

CREATE TABLE books (
  key       TEXT PRIMARY KEY,   -- "<genre>/<book>", the catalog.json key
  genre     TEXT NOT NULL,
  book      TEXT NOT NULL,      -- directory name; the list_books "book" field
  title     TEXT,
  author    TEXT,
  ebook_id  INTEGER,
  file_path TEXT                -- the content document's node file_path
);
CREATE INDEX idx_books_genre ON books(genre);

CREATE TABLE corpus_stats (
  books       INTEGER,
  genres      INTEGER,
  diaries     INTEGER,
  nodes       INTEGER,
  edges       INTEGER,
  embed_model TEXT
);
"""

_PASSAGE_SCHEMA = """
CREATE TABLE pack_meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE passages (
  id         TEXT PRIMARY KEY,
  kg_name    TEXT NOT NULL,     -- "gutenberg", or a diary slug
  kg_kind    TEXT NOT NULL,     -- the hit's kg_kind, verbatim from the worker
  kind       TEXT NOT NULL,     -- chunk | section
  name       TEXT,
  title      TEXT,             -- the work's title, for hit cards
  node_title TEXT,             -- this node's own title; a section's chapter name
  author     TEXT,
  genre      TEXT,
  book       TEXT,
  file_path  TEXT,
  char_start INTEGER,           -- chapter reconstruction (Browse)
  chapter    INTEGER,           -- verse-chunked genres with no section nodes
  timestamp  TEXT,              -- diaries only
  vector_index INTEGER,         -- dense row in the .vectors sidecar; NULL if none
  content    TEXT NOT NULL
);
CREATE INDEX idx_passages_scope ON passages(genre, kind);
CREATE INDEX idx_passages_vec   ON passages(vector_index);
CREATE INDEX idx_passages_read  ON passages(file_path, kind, char_start);
CREATE INDEX idx_passages_kg    ON passages(kg_name);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE passages_fts USING fts5(
  content,
  content='passages',
  content_rowid='rowid',
  tokenize='porter unicode61 remove_diacritics 2'
);
"""


class ExportError(RuntimeError):
    """A bundle could not be read, or a required dependency is missing."""


# --------------------------------------------------------------------------
# Locating the bundle
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DiarySource:
    """One DiaryKG inside the bundle."""

    slug: str
    graph: Path
    vectors: Path | None
    lancedb: Path | None


@dataclass(frozen=True)
class BundlePaths:
    """Everything the export reads, resolved and checked to exist."""

    root: Path
    graph: Path
    catalog: Path | None
    vectors: Path | None
    lancedb: Path | None
    diaries: tuple[DiarySource, ...] = ()

    @property
    def has_vectors(self) -> bool:
        return self.vectors is not None or self.lancedb is not None


def _resolve_vector_paths(store_dir: Path) -> tuple[Path | None, Path | None]:
    """Return ``(vectors.sqlite, lancedb/)`` for a store directory, at most one set.

    Mirrors :func:`gutenberg_kg.vector_store.resolve_vector_paths`, inlined so
    this module keeps stdlib-only imports at module scope and stays importable
    (and testable) without the rest of the package.

    :param store_dir: A ``.dockg`` / ``.diarykg`` directory.
    :returns: ``(vectors_path, lancedb_path)``; the migrated shape wins.
    """
    vectors = store_dir / "vectors.sqlite"
    if vectors.exists():
        return vectors, None
    lancedb = store_dir / "lancedb"
    if lancedb.exists():
        return None, lancedb
    return None, None


def locate_bundle(root: Path) -> BundlePaths:
    """Resolve a bundle directory into the files the export reads.

    :param root: Bundle root, e.g. ``bundles/gutenberg-all``.
    :returns: Resolved paths, with diaries discovered under ``diaries/``.
    :raises ExportError: If the root or its consolidated ``graph.sqlite`` is
        missing — the one failure worth reporting before any work starts.
    """
    root = Path(root)
    if not root.is_dir():
        raise ExportError(
            f"bundle not found: {root}\nBuild one first with `make build-corpus`, or pass --bundle."
        )
    dockg = root / ".dockg"
    graph = dockg / "graph.sqlite"
    if not graph.exists():
        raise ExportError(f"no consolidated DocKG at {graph} — is {root} a bundle root?")

    vectors, lancedb = _resolve_vector_paths(dockg)
    catalog = dockg / "catalog.json"

    diaries: list[DiarySource] = []
    diaries_root = root / "diaries"
    if diaries_root.is_dir():
        for directory in sorted(p for p in diaries_root.iterdir() if p.is_dir()):
            store = directory / ".diarykg"
            diary_graph = store / "graph.sqlite"
            if not diary_graph.exists():
                continue
            dvec, dlance = _resolve_vector_paths(store)
            diaries.append(
                DiarySource(
                    slug=_diary_slug(directory.name),
                    graph=diary_graph,
                    vectors=dvec,
                    lancedb=dlance,
                )
            )

    return BundlePaths(
        root=root,
        graph=graph,
        catalog=catalog if catalog.exists() else None,
        vectors=vectors,
        lancedb=lancedb,
        diaries=tuple(diaries),
    )


def _diary_slug(directory_name: str) -> str:
    """Slug for a diary directory, deferring to the package's own rule.

    Falls back to a local copy when the package is not importable, so the
    exporter still runs from a checkout without its dependencies installed.

    :param directory_name: Diary directory name.
    :returns: Kebab-case slug, matching the worker's ``kg_name`` for that diary.
    """
    try:
        from gutenberg_kg.diary_meta import diary_slug  # noqa: PLC0415

        return diary_slug(directory_name)
    except Exception:  # noqa: BLE001 — the fallback is the same transformation
        return (
            directory_name.lower()
            .replace("the diary of ", "")
            .replace("the journal of a tour to the hebrides with ", "")
            .replace("samuel pepys", "pepys")
            .replace("john evelyn", "evelyn")
            .replace("samuel johnson", "johnson")
            .replace("—", "")
            .replace("  ", " ")
            .strip()
            .replace(" ", "-")
        )


def _diary_meta() -> dict[str, dict]:
    """Static author/title/genre per diary slug, or ``{}`` when unavailable."""
    try:
        from gutenberg_kg.diary_meta import DIARY_META  # noqa: PLC0415

        return dict(DIARY_META)
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------
# Reading source nodes
# --------------------------------------------------------------------------


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    """Column names present on *table*.

    Every read in this module is shaped by this rather than by a hardcoded
    column list: DocKG and DiaryKG differ, and both change as they are rebuilt.

    :param con: An open connection.
    :param table: Table name.
    :returns: The column names, or an empty set when the table is absent.
    """
    try:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


#: Columns pulled from ``nodes`` when present. ``text`` is the clean passage.
_WANTED_NODE_COLUMNS = (
    "id",
    "kind",
    "name",
    "title",
    "file_path",
    "text",
    "char_start",
    "chapter",
    "timestamp",
)


def iter_source_passages(
    graph: Path,
    *,
    max_chars: int = 0,
) -> Iterator[dict]:
    """Yield searchable passages from a ``graph.sqlite``.

    Applies the worker's own scope — ``kind IN ('chunk','section')``, and never
    a book's ``reference.md`` metadata sheet — so the pack holds the same set
    the served query ranks.

    Empty chunks are dropped. Empty *sections* are not: they carry no prose but
    they are the chapter markers ``get_chapters`` lists and ``get_chapter``
    slices between, so dropping them would take the Browse tab with them.

    :param graph: Path to a DocKG/DiaryKG ``graph.sqlite``.
    :param max_chars: Truncate ``content`` to this many characters, at a word
        boundary; 0 keeps the passage whole.
    :yields: Row dicts keyed by the columns in :data:`_WANTED_NODE_COLUMNS`,
        with absent columns set to ``None``.
    """
    con = sqlite3.connect(f"file:{graph}?mode=ro", uri=True)
    try:
        present = table_columns(con, "nodes")
        if not present:
            raise ExportError(f"{graph} has no `nodes` table")
        if "text" not in present:
            raise ExportError(
                f"{graph} has no `nodes.text` column — this store predates the "
                "clean-content schema and cannot be exported."
            )
        selected = [c for c in _WANTED_NODE_COLUMNS if c in present]

        kinds = ", ".join("?" for _ in SEARCHED_KINDS)
        sql = f"SELECT {', '.join(selected)} FROM nodes WHERE kind IN ({kinds})"
        params: list[object] = list(SEARCHED_KINDS)
        if "file_path" in present:
            sql += " AND (file_path IS NULL OR file_path NOT LIKE '%reference.md')"
        sql += " ORDER BY rowid"

        con.row_factory = sqlite3.Row
        for row in con.execute(sql, params):
            record = {column: None for column in _WANTED_NODE_COLUMNS}
            for column in selected:
                record[column] = row[column]
            content = (record["text"] or "").strip()
            # A chunk with no text is nothing; a section with no text is still
            # a chapter marker, and Browse builds its chapter list from those.
            if not content and record["kind"] != "section":
                continue
            record["text"] = _truncate(content, max_chars) if max_chars else content
            yield record
    finally:
        con.close()


def _truncate(text: str, limit: int) -> str:
    """Cut *text* to *limit* characters at the last word boundary.

    :param text: Passage text.
    :param limit: Maximum characters; values <= 0 return the text unchanged.
    :returns: The passage, possibly shortened with an ellipsis.
    """
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > 0 else cut).rstrip() + "…"


def load_catalog(path: Path | None) -> dict[str, dict]:
    """Load ``catalog.json``: ``"<genre>/<book>" -> {genre, title, author, ...}``.

    :param path: Path to the catalog, or None.
    :returns: The catalog, or ``{}`` when it is missing or unreadable.
    """
    if path is None or not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def split_source_path(file_path: str | None) -> tuple[str | None, str | None]:
    """Split a node ``file_path`` into ``(genre, book)``.

    Paths are ``"<genre>/<book>/<document>.md"``. This is the same split
    ``handler._enrich_catalog`` does to key into the catalog.

    :param file_path: A node's file path, or None.
    :returns: ``(genre, book)``; either may be None for an unexpected shape.
    """
    if not file_path:
        return None, None
    parts = file_path.split("/")
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]


# --------------------------------------------------------------------------
# Vectors
# --------------------------------------------------------------------------


def _load_numpy():
    """Import numpy, with an actionable message when it is absent."""
    try:
        import numpy  # noqa: PLC0415

        return numpy
    except ImportError as exc:  # pragma: no cover — environment-dependent
        raise ExportError("vector export needs numpy: `poetry install` in the repo root.") from exc


def _connect_with_vec(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    """Open *path* with the sqlite-vec extension loaded.

    :param path: SQLite file.
    :param read_only: Open the file read-only.
    :returns: A connection with ``vec0`` available.
    :raises ExportError: If sqlite-vec is missing, or this Python's sqlite3 was
        built without extension loading — the two failures that look identical
        from the outside and have completely different fixes.
    """
    try:
        import sqlite_vec  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover — environment-dependent
        raise ExportError(
            "sqlite-vec is required to read and write vector stores: "
            "`poetry install` (it ships with kgmodule-utils[sqlite-vec])."
        ) from exc

    uri = f"file:{path}?mode=ro" if read_only else str(path)
    con = sqlite3.connect(uri, uri=read_only)
    try:
        con.enable_load_extension(True)
    except AttributeError as exc:  # pragma: no cover — stock system Python
        con.close()
        raise ExportError(
            "this Python's sqlite3 was built without extension loading, which "
            "sqlite-vec needs. A Poetry/pyenv-built interpreter works."
        ) from exc
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    return con


def iter_source_vectors(vectors: Path | None, lancedb: Path | None) -> Iterator[tuple[str, object]]:
    """Stream ``(node_id, vector)`` from whichever store shape the bundle has.

    Streams rather than materialising: the consolidated store holds 688 K
    vectors, and only the ~364 K searchable ones end up in the pack.

    :param vectors: A migrated ``vectors.sqlite``, or None.
    :param lancedb: A legacy ``lancedb/`` directory, or None.
    :yields: ``(id, numpy float32 array)`` pairs.
    :raises ExportError: If neither store is present.
    """
    numpy = _load_numpy()
    if vectors is not None:
        con = _connect_with_vec(vectors, read_only=True)
        try:
            rows = con.execute(
                "SELECT vec_meta.id, vec_nodes.embedding "
                "FROM vec_nodes JOIN vec_meta ON vec_meta.rowid = vec_nodes.rowid"
            )
            for node_id, blob in rows:
                yield node_id, numpy.frombuffer(blob, dtype=numpy.float32)
        finally:
            con.close()
        return

    if lancedb is not None:
        try:
            import lancedb as lancedb_module  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover — environment-dependent
            raise ExportError(
                f"{lancedb} is a LanceDB store; reading it needs the lancedb "
                "package. Convert it first with `dockg convert-index`."
            ) from exc
        database = lancedb_module.connect(str(lancedb))
        table = database.open_table(database.table_names()[0])
        arrow = table.to_arrow()
        ids = arrow["id"].to_pylist()
        raw = arrow["vector"].to_pylist()
        for node_id, vector in zip(ids, raw, strict=False):
            yield node_id, numpy.asarray(vector, dtype=numpy.float32)
        return

    raise ExportError("no vector store found in the bundle (.dockg/vectors.sqlite or lancedb/)")


def encode_vector(vector, dtype: str) -> bytes:
    """Encode one vector for a ``vec0`` column.

    Vectors are L2-normalised before int8 quantisation. Cosine distance is
    scale-invariant, so this changes no ranking — but it does guarantee the
    ``* 127`` scaling lands inside int8 range instead of clipping whatever the
    embedder happened to emit.

    :param vector: A numpy float32 array.
    :param dtype: ``"float"`` or ``"int8"``.
    :returns: The packed bytes for the column.
    """
    numpy = _load_numpy()
    array = numpy.asarray(vector, dtype=numpy.float32)
    if dtype == "float":
        return array.tobytes()
    norm = float(numpy.linalg.norm(array))
    if norm > 0:
        array = array / norm
    return numpy.clip(numpy.round(array * 127.0), -128, 127).astype(numpy.int8).tobytes()


# --------------------------------------------------------------------------
# Pack construction
# --------------------------------------------------------------------------


@dataclass
class PackStats:
    """What a finished pack contains."""

    path: Path
    passages: int = 0
    vectors: int = 0
    missing_vectors: int = 0
    bytes: int = 0
    sha256: str = ""
    #: The ``.vectors`` sidecar, when this pack has one.
    sidecar: Path | None = None
    sidecar_bytes: int = 0
    sidecar_sha256: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def total_bytes(self) -> int:
        """Pack plus sidecar — what actually has to reach the device."""
        return self.bytes + self.sidecar_bytes


def _fresh_db(path: Path, schema: str) -> sqlite3.Connection:
    """Create *path* from scratch with *schema* applied.

    :param path: Destination file; replaced if it exists.
    :param schema: DDL to execute.
    :returns: An open connection with fast bulk-write pragmas set.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(str(path))
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    con.executescript(schema)
    return con


def _stamp(con: sqlite3.Connection, entries: dict[str, object]) -> None:
    """Write ``pack_meta`` rows. Every pack says what it is and what built it."""
    con.executemany(
        "INSERT OR REPLACE INTO pack_meta(key, value) VALUES (?, ?)",
        [(key, str(value)) for key, value in entries.items()],
    )


def _finalise(path: Path, stats: PackStats) -> PackStats:
    """Vacuum, then record the pack's size and checksum.

    :param path: The pack file.
    :param stats: Stats to fill in.
    :returns: *stats*, with ``bytes`` and ``sha256`` set.
    """
    con = sqlite3.connect(str(path))
    try:
        con.execute("VACUUM")
    finally:
        con.close()
    stats.bytes = path.stat().st_size
    stats.sha256 = _sha256(path)
    return stats


def _sha256(path: Path) -> str:
    """Streamed SHA-256 of a file, so a 1 GB pack is not read into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_core_pack(
    dest: Path,
    *,
    bundle: BundlePaths,
    catalog: dict[str, dict],
    diary_count: int,
) -> PackStats:
    """Write ``core.pack`` — the catalog the Browse tab and the scope picker read.

    :param dest: Output path.
    :param bundle: Resolved bundle paths.
    :param catalog: Parsed ``catalog.json``.
    :param diary_count: Diaries included in this export.
    :returns: Stats for the finished pack.
    """
    con = _fresh_db(dest, _CORE_SCHEMA)
    try:
        file_paths = _document_paths(bundle.graph)
        rows = []
        genre_counts: dict[str, int] = {}
        for key, meta in sorted(catalog.items()):
            genre = meta.get("genre") or key.split("/")[0]
            book = meta.get("book") or key.split("/")[-1]
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
            rows.append(
                (
                    key,
                    genre,
                    book,
                    meta.get("title"),
                    meta.get("author"),
                    meta.get("ebook_id"),
                    file_paths.get(key),
                )
            )
        con.executemany(
            "INSERT OR REPLACE INTO books"
            "(key, genre, book, title, author, ebook_id, file_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.executemany(
            "INSERT OR REPLACE INTO genres(genre, book_count) VALUES (?, ?)",
            sorted(genre_counts.items()),
        )

        nodes, edges = _graph_totals(bundle.graph)
        con.execute(
            "INSERT INTO corpus_stats(books, genres, diaries, nodes, edges, embed_model) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (len(rows), len(genre_counts), diary_count, nodes, edges, EMBED_MODEL),
        )
        _stamp(
            con,
            {
                "pack": "core",
                "pack_version": PACK_VERSION,
                "generated": datetime.now(UTC).isoformat(timespec="seconds"),
                "embed_model": EMBED_MODEL,
            },
        )
        con.commit()
    finally:
        con.close()
    return _finalise(dest, PackStats(path=dest, passages=len(catalog)))


def _document_paths(graph: Path) -> dict[str, str]:
    """Map ``"<genre>/<book>"`` to its content document's ``file_path``.

    The Browse tab needs this to reach a book's chapters; it is the pack's
    equivalent of ``handler._resolve_book_file_path``.

    :param graph: The consolidated ``graph.sqlite``.
    :returns: Catalog key → document file path.
    """
    out: dict[str, str] = {}
    con = sqlite3.connect(f"file:{graph}?mode=ro", uri=True)
    try:
        if "file_path" not in table_columns(con, "nodes"):
            return out
        rows = con.execute(
            "SELECT file_path FROM nodes WHERE kind='document' "
            "AND file_path IS NOT NULL AND file_path NOT LIKE '%reference.md'"
        )
        for (file_path,) in rows:
            genre, book = split_source_path(file_path)
            if genre and book:
                out.setdefault(f"{genre}/{book}", file_path)
    except sqlite3.Error:
        return out
    finally:
        con.close()
    return out


def _graph_totals(graph: Path) -> tuple[int, int]:
    """Node and edge counts, for the header caption. Zeros when unreadable."""
    con = sqlite3.connect(f"file:{graph}?mode=ro", uri=True)
    try:
        nodes = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        try:
            edges = con.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        except sqlite3.Error:
            edges = 0
        return int(nodes), int(edges)
    except sqlite3.Error:
        return 0, 0
    finally:
        con.close()


@dataclass(frozen=True)
class _PassageSource:
    """One KG feeding a passage pack."""

    graph: Path
    kg_name: str
    kg_kind: str
    vectors: Path | None
    lancedb: Path | None
    #: Fixed title/author/genre for a whole KG (diaries), or None to take them
    #: from the catalog per book.
    fixed_meta: dict | None = None


def build_passage_pack(
    dest: Path,
    sources: Sequence[_PassageSource],
    *,
    catalog: dict[str, dict],
    dtype: str = "int8",
    max_chars: int = 0,
    with_vectors: bool = True,
    progress=None,
) -> PackStats:
    """Write a passage pack: content, an FTS5 index over it, and the vectors.

    Passages are written first so SQLite assigns their rowids; vectors are then
    streamed in against those same rowids. A passage whose vector is missing
    from the source store is kept — it stays findable lexically and readable in
    Browse — and counted in ``missing_vectors`` so a partial store is visible
    rather than silent.

    :param dest: Output path.
    :param sources: KGs to merge into this pack (one for books, four for diaries).
    :param catalog: Parsed ``catalog.json``, for per-book title/author.
    :param dtype: ``"int8"`` (default, ~3x smaller) or ``"float"``.
    :param max_chars: Per-passage truncation; 0 keeps passages whole.
    :param with_vectors: Skip the vector stage entirely when False.
    :param progress: Optional ``callable(str)`` for status lines.
    :returns: Stats for the finished pack.
    """
    say = progress or (lambda _message: None)
    diary_meta = _diary_meta()

    con = _fresh_db(dest, _PASSAGE_SCHEMA)
    rowid_by_id: dict[str, int] = {}
    stats = PackStats(path=dest)
    try:
        insert = (
            "INSERT OR IGNORE INTO passages"
            "(id, kg_name, kg_kind, kind, name, title, node_title, author, genre, "
            " book, file_path, char_start, chapter, timestamp, content) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        for source in sources:
            fixed = source.fixed_meta or diary_meta.get(source.kg_name)
            written = 0
            batch: list[tuple] = []
            for record in iter_source_passages(source.graph, max_chars=max_chars):
                genre, book = split_source_path(record["file_path"])
                meta = catalog.get(f"{genre}/{book}", {}) if genre and book else {}
                batch.append(
                    (
                        record["id"],
                        source.kg_name,
                        source.kg_kind,
                        record["kind"],
                        record["name"],
                        (fixed or {}).get("title") or meta.get("title") or book,
                        record["title"],
                        (fixed or {}).get("author") or meta.get("author"),
                        (fixed or {}).get("genre") or meta.get("genre") or genre,
                        book,
                        record["file_path"],
                        record["char_start"],
                        record["chapter"],
                        record["timestamp"],
                        record["text"],
                    )
                )
                if len(batch) >= 2000:
                    con.executemany(insert, batch)
                    written += len(batch)
                    batch = []
            if batch:
                con.executemany(insert, batch)
                written += len(batch)
            con.commit()
            stats.passages += written
            say(f"  {source.kg_name}: {written:,} passages")

        for node_id, rowid in con.execute("SELECT id, rowid FROM passages"):
            rowid_by_id[node_id] = rowid

        say("  building the FTS5 index over clean passage text…")
        con.executescript(_FTS_SCHEMA)
        con.execute("INSERT INTO passages_fts(passages_fts) VALUES('rebuild')")
        con.commit()
        _stamp(
            con,
            {
                "pack": dest.stem,
                "pack_version": PACK_VERSION,
                "generated": datetime.now(UTC).isoformat(timespec="seconds"),
                "embed_model": EMBED_MODEL,
                "embed_dim": EMBED_DIM,
                "vector_dtype": dtype if with_vectors else "none",
                "rrf_k": RRF_K,
                "kgs": ",".join(s.kg_name for s in sources),
            },
        )
        con.commit()
    finally:
        con.close()

    if with_vectors:
        stats.sidecar, stats.vectors, stats.missing_vectors = write_vector_sidecar(
            dest, sources, rowid_by_id, dtype=dtype, progress=say
        )
        if stats.sidecar is not None:
            stats.sidecar_bytes = stats.sidecar.stat().st_size
            stats.sidecar_sha256 = _sha256(stats.sidecar)

    return _finalise(dest, stats)


def write_vector_sidecar(
    pack: Path,
    sources: Sequence[_PassageSource],
    rowid_by_id: dict[str, int],
    *,
    dtype: str,
    progress,
) -> tuple[Path | None, int, int]:
    """Write ``<pack>.vectors`` and point each passage at its row.

    The sidecar is a header plus row-major vectors — nothing else. The device
    memory-maps it and multiplies straight out of the mapping, so a query never
    allocates and the OS pages in only the part it touches. That is also why
    the vectors do not live in the pack as a ``vec0`` table: reading one needs
    the sqlite-vec C extension compiled into the app, and vec0's search is
    brute force regardless, so the extension would buy nothing.

    ``passages.vector_index`` is dense (0..N-1) rather than the passage rowid,
    because a passage whose vector the source store lacks must not leave a hole
    in the file.

    :param pack: The pack whose passages were just written.
    :param sources: KGs whose vector stores to stream.
    :param rowid_by_id: Node id → the rowid its passage got.
    :param dtype: ``"int8"`` or ``"float"``.
    :param progress: Status callable.
    :returns: ``(sidecar_path, vectors_written, passages_without_a_vector)``.
    """
    _load_numpy()  # fail before writing a partial file, not halfway through one
    sidecar = pack.with_suffix(".vectors")
    itemsize = _DTYPE_ITEMSIZE[dtype]

    con = sqlite3.connect(str(pack))
    written = 0
    try:
        con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
        with open(sidecar, "wb") as handle:
            handle.write(b"\0" * VECTOR_HEADER_BYTES)  # backfilled once count is known
            seen: set[int] = set()
            assignments: list[tuple[int, int]] = []
            for source in sources:
                if source.vectors is None and source.lancedb is None:
                    progress(f"  {source.kg_name}: no vector store — lexical search only")
                    continue
                for node_id, vector in iter_source_vectors(source.vectors, source.lancedb):
                    rowid = rowid_by_id.get(node_id)
                    if rowid is None or rowid in seen:
                        continue
                    seen.add(rowid)
                    encoded = encode_vector(vector, dtype)
                    if len(encoded) != EMBED_DIM * itemsize:
                        raise ExportError(
                            f"{node_id} has {len(encoded) // itemsize} dimensions, "
                            f"expected {EMBED_DIM}"
                        )
                    handle.write(encoded)
                    assignments.append((written, rowid))
                    written += 1
                progress(f"  {source.kg_name}: {written:,} vectors written ({dtype})")

            handle.flush()
            handle.seek(0)
            handle.write(_vector_header(dtype, EMBED_DIM, written))

        with con:
            con.executemany("UPDATE passages SET vector_index = ? WHERE rowid = ?", assignments)
    finally:
        con.close()

    if written == 0:
        sidecar.unlink(missing_ok=True)
        return None, 0, len(rowid_by_id)
    return sidecar, written, len(rowid_by_id) - written


def _vector_header(dtype: str, dim: int, count: int) -> bytes:
    """Build the sidecar's fixed 32-byte header.

    :param dtype: ``"int8"`` or ``"float"``.
    :param dim: Embedding dimensionality.
    :param count: Vectors in the file.
    :returns: Exactly :data:`VECTOR_HEADER_BYTES` bytes.
    """
    header = bytearray(VECTOR_HEADER_BYTES)
    header[0:8] = VECTOR_MAGIC
    header[8] = _DTYPE_CODES[dtype]
    header[12:16] = int(dim).to_bytes(4, "little")
    header[16:24] = int(count).to_bytes(8, "little")
    return bytes(header)


def read_vector_sidecar(sidecar: Path):
    """Memory-map a sidecar and return ``(matrix, dtype)``.

    :param sidecar: A ``.vectors`` file.
    :returns: An ``(count, dim)`` numpy array viewing the file, and its dtype
        name.
    :raises ExportError: If the magic, dimension or length do not agree — a
        truncated download is the failure this catches.
    """
    numpy = _load_numpy()
    with open(sidecar, "rb") as handle:
        header = handle.read(VECTOR_HEADER_BYTES)
    if len(header) < VECTOR_HEADER_BYTES or header[0:8] != VECTOR_MAGIC:
        raise ExportError(f"{sidecar} is not a GutenbergKG vector sidecar")
    codes = {code: name for name, code in _DTYPE_CODES.items()}
    dtype = codes.get(header[8])
    if dtype is None:
        raise ExportError(f"{sidecar} has an unknown vector dtype ({header[8]})")
    dim = int.from_bytes(header[12:16], "little")
    count = int.from_bytes(header[16:24], "little")
    expected = VECTOR_HEADER_BYTES + count * dim * _DTYPE_ITEMSIZE[dtype]
    actual = sidecar.stat().st_size
    if actual != expected:
        raise ExportError(
            f"{sidecar} is {actual} bytes, expected {expected} for "
            f"{count} x {dim} {dtype} — truncated?"
        )
    numpy_dtype = numpy.int8 if dtype == "int8" else numpy.float32
    matrix = numpy.memmap(
        sidecar, dtype=numpy_dtype, mode="r", offset=VECTOR_HEADER_BYTES, shape=(count, dim)
    )
    return matrix, dtype


# --------------------------------------------------------------------------
# Reference retrieval over a finished pack
#
# This is the specification the Swift LocalRetrieval must reproduce, and the
# thing golden.json records. It is a direct translation of
# handler._semantic_search onto the pack's schema — same oversampling, same
# RRF constant, same score arithmetic.
# --------------------------------------------------------------------------


def fts_match_expression(query: str) -> str:
    """Turn a natural-language query into a safe FTS5 MATCH expression.

    Every term is quoted and the terms are OR-ed, so an apostrophe or a
    question mark in the query cannot become FTS5 syntax — and a query is never
    rejected wholesale for one odd character.

    :param query: The user's query text.
    :returns: An FTS5 MATCH expression, or ``""`` when nothing is searchable.
    """
    terms = [t for t in ("".join(c if c.isalnum() else " " for c in query)).split() if t]
    return " OR ".join(f'"{term}"' for term in terms)


def _scope_clause(*, genre: str | None, prefix: str = "") -> str:
    """The worker's search scope as SQL: searchable kinds, optionally one genre.

    :param genre: Genre slug to restrict to, or None.
    :param prefix: Table alias prefix (``"p."``) when the clause sits in a join.
    :returns: A WHERE fragment; a bound ``?`` follows for the genre when given.
    """
    kinds = ", ".join(f"'{kind}'" for kind in SEARCHED_KINDS)
    clause = f"{prefix}kind IN ({kinds})"
    if genre:
        clause += f" AND {prefix}genre = ?"
    return clause


def search_pack(
    pack: Path,
    query_vector,
    query_text: str,
    *,
    k: int = 10,
    genre: str | None = None,
    min_score: float = 0.0,
) -> list[dict]:
    """Run the packed corpus's own hybrid search — dense + BM25, fused by RRF.

    A direct translation of ``handler._semantic_search`` onto the pack: same
    ``k * 3`` oversampling in both channels, same :data:`RRF_K`, same
    ``round(1 - distance, 4)`` score, and the same hydrate-missing-cosine step
    so every fused hit carries an honest score.

    The dense channel is a dot product over the memory-mapped sidecar rather
    than a vec0 query, which is what the Swift engine does with Accelerate.
    Both are exhaustive, so this is the same ranking by a simpler route.

    :param pack: A passage pack (its sidecar sits beside it).
    :param query_vector: The query embedding (numpy float32, 384-d).
    :param query_text: The raw query, for the lexical channel.
    :param k: Hits to return.
    :param genre: Restrict to one genre, as the worker's ``genre_filter`` does.
    :param min_score: Drop hits below this cosine score.
    :returns: Hit dicts in the worker's shape, best-first.
    """
    numpy = _load_numpy()
    con = sqlite3.connect(f"file:{pack}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        scope = _scope_clause(genre=genre)
        params: list[object] = [genre] if genre else []

        dense_ids: list[str] = []
        distance_by_id: dict[str, float] = {}
        sidecar = pack.with_suffix(".vectors")
        if sidecar.exists():
            matrix, dtype = read_vector_sidecar(sidecar)
            rows = con.execute(
                f"SELECT id, vector_index FROM passages WHERE vector_index IS NOT NULL AND {scope}",
                params,
            ).fetchall()
            if rows:
                ids = [row["id"] for row in rows]
                indices = numpy.fromiter(
                    (row["vector_index"] for row in rows), dtype=numpy.int64, count=len(rows)
                )
                # int8 rows are unit vectors scaled by 127; the scale cancels
                # once the similarity is renormalised, so ranking is unaffected.
                candidates = numpy.asarray(matrix[indices], dtype=numpy.float32)
                norms = numpy.linalg.norm(candidates, axis=1).clip(min=1e-12)
                query = numpy.asarray(query_vector, dtype=numpy.float32)
                query = query / max(float(numpy.linalg.norm(query)), 1e-12)
                similarity = (candidates @ query) / norms
                order = numpy.argsort(-similarity)[: k * 3]
                dense_ids = [ids[i] for i in order]
                distance_by_id = {ids[i]: 1.0 - float(similarity[i]) for i in order}
                # Keep every candidate's score available for the lexical
                # hydration step below, without re-reading the sidecar.
                _all_scores = {ids[i]: float(similarity[i]) for i in range(len(ids))}
            else:
                _all_scores = {}
        else:
            _all_scores = {}

        lexical_ids: list[str] = []
        expression = fts_match_expression(query_text)
        if expression:
            lex_sql = (
                "SELECT p.id AS id FROM passages_fts f "
                "JOIN passages p ON p.rowid = f.rowid "
                f"WHERE passages_fts MATCH ? AND {_scope_clause(genre=genre, prefix='p.')} "
                "ORDER BY bm25(passages_fts) LIMIT ?"
            )
            try:
                lexical_ids = [r["id"] for r in con.execute(lex_sql, [expression, *params, k * 3])]
            except sqlite3.Error:
                lexical_ids = []

        # Hydrate cosine for lexical-only ids so every fused hit carries an
        # honest score — handler._semantic_search does exactly this.
        for node_id in lexical_ids:
            if node_id not in distance_by_id and node_id in _all_scores:
                distance_by_id[node_id] = 1.0 - _all_scores[node_id]
        lexical_ids = [i for i in lexical_ids if i in distance_by_id]

        ordered = rrf_fuse(dense_ids, lexical_ids, k) if lexical_ids else dense_ids[:k]
        if not ordered:
            return []

        placeholders = ", ".join("?" for _ in ordered)
        by_id = {
            row["id"]: dict(row)
            for row in con.execute(f"SELECT * FROM passages WHERE id IN ({placeholders})", ordered)
        }
        hits = []
        for node_id in ordered:
            row = by_id.get(node_id)
            if row is None:
                continue
            score = round(1.0 - distance_by_id.get(node_id, 1.0), 4)
            if score < min_score:
                continue
            hits.append(
                {
                    "kg_name": row["kg_name"],
                    "kg_kind": row["kg_kind"],
                    "node_id": node_id,
                    "name": row["name"] or row["title"] or "",
                    "kind": row["kind"],
                    "score": score,
                    "summary": row["content"],
                    "source_path": row["file_path"] or "",
                    "content": row["content"],
                    "timestamp": row["timestamp"],
                    "genre": row["genre"],
                    "title": row["title"],
                    "author": row["author"],
                }
            )
        return hits
    finally:
        con.close()


def rrf_fuse(dense_ids: Sequence[str], lexical_ids: Sequence[str], k: int) -> list[str]:
    """Blend two rank lists with reciprocal rank fusion.

    Byte-for-byte the arithmetic in ``handler._rrf_fuse``, at the same
    :data:`RRF_K`. A hit ranked well by either channel floats up; one ranked by
    both wins.

    :param dense_ids: Ids best-first by cosine.
    :param lexical_ids: Ids best-first by BM25.
    :param k: How many fused ids to return.
    :returns: Fused ids, best-first.
    """
    scores: dict[str, float] = {}
    for rank, node_id in enumerate(dense_ids):
        scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (RRF_K + rank)
    for rank, node_id in enumerate(lexical_ids):
        scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores, key=lambda i: -scores[i])[:k]


def _make_embedder():
    """Load the corpus embedder — the same model the vectors were built with.

    :returns: An embedder exposing ``embed_texts``.
    :raises ExportError: When the embedder cannot be loaded, naming the flag
        that skips the step instead.
    """
    try:
        from kg_rag._embedders import SentenceTransformerEmbedder  # noqa: PLC0415

        return SentenceTransformerEmbedder(EMBED_MODEL)
    except Exception as exc:  # noqa: BLE001 — any import/download failure
        raise ExportError(
            f"could not load the embedder {EMBED_MODEL} ({exc}). "
            "Pass --no-golden to build the packs without the parity file."
        ) from exc


def build_golden(
    packs: dict[str, Path],
    *,
    k: int,
    dtype: str,
    queries: Sequence[str] = GOLDEN_QUERIES,
    progress=None,
) -> dict:
    """Record each golden query's top-k, as the packs themselves answer it.

    The Swift engine is correct when it reproduces this file: same node ids in
    roughly the same order, same scores to two decimal places. Divergence
    localises to one of two places — the WordPiece tokenizer in front of the
    Core ML embedder, or the int8 quantisation — which is what makes the gate
    worth having.

    :param packs: ``{"gutenberg": path, "diaries": path}``; missing keys skipped.
    :param k: Hits to record per query.
    :param dtype: The packs' vector dtype.
    :param queries: Queries to record.
    :param progress: Optional status callable.
    :returns: The golden document, ready to serialise.
    """
    say = progress or (lambda _message: None)
    embedder = _make_embedder()
    say(f"  embedding {len(queries)} golden queries…")
    vectors = embedder.embed_texts(list(queries))

    entries = []
    for query, vector in zip(queries, vectors, strict=False):
        record: dict = {"query": query, "packs": {}}
        for name, path in packs.items():
            hits = search_pack(path, vector, query, k=k)
            record["packs"][name] = [
                {"rank": rank, "node_id": hit["node_id"], "score": hit["score"]}
                for rank, hit in enumerate(hits)
            ]
        entries.append(record)

    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "embed_model": EMBED_MODEL,
        "embed_dim": EMBED_DIM,
        "vector_dtype": dtype,
        "rrf_k": RRF_K,
        "k": k,
        "tolerance": {"rank_overlap": 0.9, "score_delta": 0.02},
        "queries": entries,
    }


def verify_pack(
    pack: Path,
    source: _PassageSource,
    *,
    k: int,
    dtype: str,
    queries: Sequence[str] = GOLDEN_QUERIES,
    progress=None,
) -> dict:
    """Measure what quantisation cost, against exact fp32 ground truth.

    Computes the true top-k by brute force over the *source* vectors — the same
    method ``benchmarks/bench_sqlite_vec.py`` uses — and compares it with what
    the pack's dense channel returns. This is a build-time gate: an int8 recall
    that has quietly fallen is something to see here, not in a user's answer.

    :param pack: The finished pack.
    :param source: The KG whose source vectors are the ground truth.
    :param k: Depth to compare at.
    :param dtype: The pack's vector dtype.
    :param queries: Queries to check.
    :param progress: Optional status callable.
    :returns: ``{"recall_at_k", "mean_score_delta", "queries": [...]}``.
    """
    say = progress or (lambda _message: None)
    numpy = _load_numpy()
    embedder = _make_embedder()

    say("  loading source vectors for exact ground truth…")
    ids: list[str] = []
    rows: list = []
    for node_id, vector in iter_source_vectors(source.vectors, source.lancedb):
        ids.append(node_id)
        rows.append(vector)
    if not rows:
        raise ExportError("no source vectors to verify against")
    matrix = numpy.vstack(rows).astype(numpy.float32)
    matrix /= numpy.linalg.norm(matrix, axis=1, keepdims=True).clip(min=1e-12)

    # Ground truth is over the pack's own id set, so a passage the pack
    # deliberately omits never counts as a miss.
    con = sqlite3.connect(f"file:{pack}?mode=ro", uri=True)
    try:
        packed_ids = {row[0] for row in con.execute("SELECT id FROM passages")}
    finally:
        con.close()
    keep = [i for i, node_id in enumerate(ids) if node_id in packed_ids]
    matrix = matrix[keep]
    ids = [ids[i] for i in keep]

    vectors = embedder.embed_texts(list(queries))
    recalls: list[float] = []
    deltas: list[float] = []
    per_query = []
    for query, vector in zip(queries, vectors, strict=False):
        qvec = numpy.asarray(vector, dtype=numpy.float32)
        qvec = qvec / max(float(numpy.linalg.norm(qvec)), 1e-12)
        exact_scores = matrix @ qvec
        top = numpy.argsort(-exact_scores)[:k]
        expected = {ids[i]: float(exact_scores[i]) for i in top}

        got = search_pack(pack, vector, query, k=k)
        got_ids = [hit["node_id"] for hit in got]
        overlap = len(set(got_ids) & set(expected)) / max(len(expected), 1)
        recalls.append(overlap)

        query_deltas = [
            abs(hit["score"] - expected[hit["node_id"]])
            for hit in got
            if hit["node_id"] in expected
        ]
        deltas.extend(query_deltas)
        per_query.append(
            {
                "query": query,
                "recall": round(overlap, 4),
                "mean_score_delta": round(sum(query_deltas) / len(query_deltas), 5)
                if query_deltas
                else None,
            }
        )
        say(f"  {overlap:.2f}  {query}")

    return {
        "k": k,
        "vector_dtype": dtype,
        "recall_at_k": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        "mean_score_delta": round(sum(deltas) / len(deltas), 5) if deltas else None,
        "queries": per_query,
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


@dataclass
class ExportOptions:
    """Inputs to :func:`export_swift`."""

    bundle: Path = DEFAULT_BUNDLE
    out: Path | None = None
    dtype: str = "int8"
    max_chars: int = 0
    include_diaries: bool = True
    with_vectors: bool = True
    golden: bool = True
    golden_k: int = 10
    verify: bool = False
    force: bool = False

    def resolved_out(self) -> Path:
        """Output directory; defaults to ``<bundle>/swift``."""
        return Path(self.out) if self.out else Path(self.bundle) / "swift"


@dataclass
class ExportReport:
    """What an export produced."""

    out: Path
    packs: list[PackStats] = field(default_factory=list)
    golden: dict | None = None
    verification: dict | None = None
    elapsed_s: float = 0.0

    @property
    def total_bytes(self) -> int:
        return sum(pack.total_bytes for pack in self.packs)


def export_swift(options: ExportOptions, *, progress=None) -> ExportReport:
    """Build the on-device packs from a bundle.

    :param options: Export inputs.
    :param progress: Optional ``callable(str)`` for status lines.
    :returns: A report naming every file written.
    :raises ExportError: On a missing bundle, an unreadable store, or an
        existing output directory without ``force``.
    """
    say = progress or (lambda _message: None)
    started = time.perf_counter()

    if options.dtype not in ("int8", "float"):
        raise ExportError(f"dtype must be 'int8' or 'float', got {options.dtype!r}")

    bundle = locate_bundle(Path(options.bundle))
    out = options.resolved_out()
    if out.exists() and any(out.iterdir()) and not options.force:
        raise ExportError(f"{out} is not empty — pass --force to overwrite it.")
    out.mkdir(parents=True, exist_ok=True)

    catalog = load_catalog(bundle.catalog)
    if not catalog:
        say("  WARNING: no catalog.json — books will carry no title or author")

    diaries = bundle.diaries if options.include_diaries else ()
    report = ExportReport(out=out)

    say(f"core.pack  ← {len(catalog)} books")
    report.packs.append(
        build_core_pack(out / "core.pack", bundle=bundle, catalog=catalog, diary_count=len(diaries))
    )

    books_source = _PassageSource(
        graph=bundle.graph,
        kg_name="gutenberg",
        kg_kind="KGKind.GUTENBERG",
        vectors=bundle.vectors,
        lancedb=bundle.lancedb,
    )
    say("gutenberg.pack")
    report.packs.append(
        build_passage_pack(
            out / "gutenberg.pack",
            [books_source],
            catalog=catalog,
            dtype=options.dtype,
            max_chars=options.max_chars,
            with_vectors=options.with_vectors,
            progress=say,
        )
    )

    if diaries:
        say("diaries.pack")
        report.packs.append(
            build_passage_pack(
                out / "diaries.pack",
                [
                    _PassageSource(
                        graph=diary.graph,
                        kg_name=diary.slug,
                        kg_kind="KGKind.DIARY",
                        vectors=diary.vectors,
                        lancedb=diary.lancedb,
                    )
                    for diary in diaries
                ],
                catalog=catalog,
                dtype=options.dtype,
                max_chars=options.max_chars,
                with_vectors=options.with_vectors,
                progress=say,
            )
        )

    pack_paths = {pack.path.stem: pack.path for pack in report.packs if pack.path.stem != "core"}

    if options.golden and options.with_vectors:
        say("golden.json")
        report.golden = build_golden(
            pack_paths, k=options.golden_k, dtype=options.dtype, progress=say
        )
        (out / "golden.json").write_text(
            json.dumps(report.golden, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if options.verify and options.with_vectors and bundle.has_vectors:
        say(f"verifying {options.dtype} recall against exact fp32 ground truth")
        report.verification = verify_pack(
            out / "gutenberg.pack",
            books_source,
            k=options.golden_k,
            dtype=options.dtype,
            progress=say,
        )

    report.elapsed_s = time.perf_counter() - started
    (out / "manifest.json").write_text(
        json.dumps(_manifest(report, bundle, options), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def _manifest(report: ExportReport, bundle: BundlePaths, options: ExportOptions) -> dict:
    """Describe the export for the app to check itself against.

    The embedder block is the important part: the pack's vectors are meaningless
    to a query embedded by a different model, so the app asserts this matches
    the embedder it ships before it searches anything.

    :param report: The finished export.
    :param bundle: The source bundle.
    :param options: The options used.
    :returns: The manifest document.
    """
    return {
        "pack_version": PACK_VERSION,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_bundle": str(bundle.root),
        "embedder": {
            "model": EMBED_MODEL,
            "dim": EMBED_DIM,
            "normalized": True,
            "note": "Query vectors must come from this model; the packs are unusable without it.",
        },
        "vector_dtype": options.dtype if options.with_vectors else "none",
        "rrf_k": RRF_K,
        "searched_kinds": list(SEARCHED_KINDS),
        "max_passage_chars": options.max_chars or None,
        "vector_sidecar": {
            "magic": VECTOR_MAGIC.decode("ascii"),
            "header_bytes": VECTOR_HEADER_BYTES,
            "layout": "row-major, one vector per row, indexed by passages.vector_index",
        },
        "packs": [
            {
                "name": pack.name,
                "bytes": pack.bytes,
                "sha256": pack.sha256,
                "passages": pack.passages,
                "vectors": pack.vectors,
                "passages_without_vectors": pack.missing_vectors,
                "sidecar": (
                    {
                        "name": pack.sidecar.name,
                        "bytes": pack.sidecar_bytes,
                        "sha256": pack.sidecar_sha256,
                    }
                    if pack.sidecar is not None
                    else None
                ),
            }
            for pack in report.packs
        ],
        "total_bytes": report.total_bytes,
        "golden": "golden.json" if report.golden else None,
        "verification": report.verification,
        "elapsed_s": round(report.elapsed_s, 1),
    }
