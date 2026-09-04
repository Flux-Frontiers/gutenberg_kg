"""Unit tests for gutenberg_kg.export_swift — the on-device corpus packs.

Deliberately free of any ``kg_rag``/``numpy``/``sqlite-vec`` dependency for the
schema half, so the shape of the pack is guarded in CI even where the ML stack
is absent; the vector half skips when sqlite-vec is not importable.

The regressions these guard for are all silent ones — a pack that builds
cleanly and is quietly missing something the app needs: a book's ``reference.md``
boilerplate ranked as prose, a chapter list emptied because section markers
carry no text, or a section's chapter name overwritten by its book's title.
"""

from __future__ import annotations

import json
import sqlite3
from importlib.util import find_spec

import pytest

from gutenberg_kg.export_swift import (
    _PASSAGE_SCHEMA,
    ExportError,
    ExportOptions,
    _truncate,
    export_swift,
    fts_match_expression,
    fts_phrase_expression,
    locate_bundle,
    rrf_fuse,
    split_source_path,
    window_oversized_sections,
)

BOOK_COLUMNS = (
    "id TEXT PRIMARY KEY",
    "kind TEXT",
    "name TEXT",
    "title TEXT",
    "file_path TEXT",
    "text TEXT",
    "char_start INTEGER",
    "chapter INTEGER",
)
DIARY_COLUMNS = (
    "id TEXT PRIMARY KEY",
    "kind TEXT",
    "name TEXT",
    "text TEXT",
    "timestamp TEXT",
)

DOC = "philosophy/Leviathan/leviathan.md"
BIBLE = "sacred-texts/The Bible (King James Version)/the_bible.md"
BOOK_ROWS = [
    ("doc:1", "document", "leviathan.md", "Leviathan", DOC, "", 0, None),
    ("doc:ref", "document", "reference.md", None, "philosophy/Leviathan/reference.md", "", 0, None),
    ("sec:1", "section", "Of Man", "Of Man", DOC, "", 0, None),
    (
        "c:1",
        "chunk",
        "chunk 1",
        None,
        DOC,
        "  The life of man, nasty, brutish, and short.  ",
        10,
        1,
    ),
    ("c:2", "chunk", "chunk 2", None, DOC, "Covenants, without the Sword, are but Words.", 120, 1),
    # A book's metadata sheet: never prose, never a search hit.
    (
        "c:ref",
        "chunk",
        "ref",
        None,
        "philosophy/Leviathan/reference.md",
        "Gutenberg ID 3207",
        0,
        None,
    ),
    ("c:blank", "chunk", "blank", None, DOC, "   ", 300, 1),
    # Not a searched kind — 324K of these stay out of the pack.
    ("t:1", "topic", "sovereignty", None, DOC, "sovereignty", 0, None),
    # A second genre: without one, neither the genre filter nor the fused
    # ranking below is being tested against anything.
    ("doc:2", "document", "the_bible.md", "Genesis", BIBLE, "", 0, None),
    (
        "s:1",
        "chunk",
        "Genesis 19",
        None,
        BIBLE,
        "But his wife looked back from behind him, and she became a pillar of salt.",
        0,
        19,
    ),
]
DIARY_ROWS = [
    (
        "p:1",
        "chunk",
        "September 2nd 1666",
        "The poor pigeons were loth to leave.",
        "1666-09-02T00:00:00",
    ),
    (
        "p:2",
        "chunk",
        "September 3rd 1666",
        "The fire continuing, I took coach.",
        "1666-09-03T00:00:00",
    ),
]


def _graph(path, columns, rows, *, edges=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute(f"CREATE TABLE nodes ({', '.join(columns)})")
    if edges:
        con.execute("CREATE TABLE edges (src TEXT, rel TEXT, dst TEXT)")
        con.execute("INSERT INTO edges VALUES ('doc:1','CONTAINS','c:1')")
    con.executemany(f"INSERT INTO nodes VALUES ({', '.join('?' * len(columns))})", rows)
    con.commit()
    con.close()


@pytest.fixture
def bundle(tmp_path):
    """A miniature bundle in the real layout: one book, one diary."""
    root = tmp_path / "bundle"
    _graph(root / ".dockg" / "graph.sqlite", BOOK_COLUMNS, BOOK_ROWS)
    (root / ".dockg" / "catalog.json").write_text(
        json.dumps(
            {
                "philosophy/Leviathan": {
                    "genre": "philosophy",
                    "book": "Leviathan",
                    "title": "Leviathan",
                    "author": "Thomas Hobbes",
                    "ebook_id": 3207,
                },
                "sacred-texts/The Bible (King James Version)": {
                    "genre": "sacred-texts",
                    "book": "The Bible (King James Version)",
                    "title": "The Bible (King James Version)",
                    "author": None,
                    "ebook_id": 10,
                },
            }
        ),
        encoding="utf-8",
    )
    # No file_path column at all — a DiaryKG's schema differs from DocKG's, and
    # the exporter reads whatever columns each store actually has.
    _graph(
        root / "diaries" / "The Diary of Samuel Pepys — Complete" / ".diarykg" / "graph.sqlite",
        DIARY_COLUMNS,
        DIARY_ROWS,
        edges=False,
    )
    return root


@pytest.fixture
def packs(bundle, tmp_path):
    """A built export, without the vector or golden stages."""
    out = tmp_path / "swift"
    report = export_swift(
        ExportOptions(bundle=bundle, out=out, with_vectors=False, golden=False, force=True)
    )
    return report, out


def _rows(pack, sql, params=()):
    con = sqlite3.connect(str(pack))
    con.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in con.execute(sql, params)]
    finally:
        con.close()


class TestLocateBundle:
    def test_finds_stores_and_diaries(self, bundle):
        found = locate_bundle(bundle)
        assert found.catalog is not None
        assert [d.slug for d in found.diaries] == ["pepys-complete"]

    def test_missing_bundle_names_the_fix(self, tmp_path):
        with pytest.raises(ExportError, match="make build-corpus"):
            locate_bundle(tmp_path / "nope")

    def test_directory_without_a_graph_is_rejected(self, tmp_path):
        (tmp_path / "empty").mkdir()
        with pytest.raises(ExportError, match="no consolidated DocKG"):
            locate_bundle(tmp_path / "empty")


class TestPassageSelection:
    def test_carries_only_searchable_nodes(self, packs):
        _, out = packs
        ids = {r["id"] for r in _rows(out / "gutenberg.pack", "SELECT id FROM passages")}
        assert ids == {"gutenberg:c:1", "gutenberg:c:2", "gutenberg:sec:1", "gutenberg:s:1"}

    def test_reference_sheets_never_become_passages(self, packs):
        _, out = packs
        ids = {r["id"] for r in _rows(out / "gutenberg.pack", "SELECT id FROM passages")}
        assert "gutenberg:c:ref" not in ids

    def test_empty_sections_survive_because_browse_needs_them(self, packs):
        """A section marker carries no prose but is still a chapter."""
        _, out = packs
        rows = _rows(out / "gutenberg.pack", "SELECT id FROM passages WHERE kind='section'")
        assert [r["id"] for r in rows] == ["gutenberg:sec:1"]

    def test_content_is_stripped(self, packs):
        _, out = packs
        (row,) = _rows(
            out / "gutenberg.pack", "SELECT content FROM passages WHERE id='gutenberg:c:1'"
        )
        assert row["content"].startswith("The life")
        assert row["content"].endswith("short.")


class TestCatalogJoin:
    def test_hits_carry_the_works_title_and_author(self, packs):
        _, out = packs
        (row,) = _rows(
            out / "gutenberg.pack",
            "SELECT title, author, genre, book FROM passages WHERE id='gutenberg:c:1'",
        )
        assert row == {
            "title": "Leviathan",
            "author": "Thomas Hobbes",
            "genre": "philosophy",
            "book": "Leviathan",
        }

    def test_section_keeps_its_own_chapter_name(self, packs):
        """`title` is the work; `node_title` is the chapter. Browse needs both."""
        _, out = packs
        (row,) = _rows(
            out / "gutenberg.pack",
            "SELECT title, node_title FROM passages WHERE id='gutenberg:sec:1'",
        )
        assert row == {"title": "Leviathan", "node_title": "Of Man"}


class TestDiaries:
    def test_timestamps_and_static_metadata_survive(self, packs):
        _, out = packs
        rows = _rows(
            out / "diaries.pack",
            "SELECT id, kg_name, kg_kind, author, timestamp FROM passages ORDER BY id",
        )
        assert rows[0]["kg_name"] == "pepys-complete"
        assert rows[0]["kg_kind"] == "KGKind.DIARY"
        assert rows[0]["author"] == "Samuel Pepys"
        assert rows[0]["timestamp"] == "1666-09-02T00:00:00"

    def test_excluded_on_request(self, bundle, tmp_path):
        out = tmp_path / "books-only"
        export_swift(
            ExportOptions(
                bundle=bundle,
                out=out,
                with_vectors=False,
                golden=False,
                include_diaries=False,
                force=True,
            )
        )
        assert not (out / "diaries.pack").exists()


class TestFullTextIndex:
    def test_matches_passage_prose(self, packs):
        _, out = packs
        rows = _rows(
            out / "gutenberg.pack",
            "SELECT p.id FROM passages_fts f JOIN passages p ON p.rowid = f.rowid "
            "WHERE passages_fts MATCH ?",
            ('"brutish"',),
        )
        assert [r["id"] for r in rows] == ["gutenberg:c:1"]

    def test_stems_so_a_singular_query_finds_a_plural(self, packs):
        _, out = packs
        rows = _rows(
            out / "gutenberg.pack",
            "SELECT p.id FROM passages_fts f JOIN passages p ON p.rowid = f.rowid "
            "WHERE passages_fts MATCH ?",
            ('"covenant"',),
        )
        assert [r["id"] for r in rows] == ["gutenberg:c:2"]


class TestCorePack:
    def test_books_genres_and_stats(self, packs):
        _, out = packs
        books = {b["key"]: b for b in _rows(out / "core.pack", "SELECT * FROM books")}
        assert books["philosophy/Leviathan"]["ebook_id"] == 3207
        # reference.md is never a book's entry point.
        assert books["philosophy/Leviathan"]["file_path"] == DOC

        genres = _rows(out / "core.pack", "SELECT * FROM genres ORDER BY genre")
        assert genres == [
            {"genre": "philosophy", "book_count": 1},
            {"genre": "sacred-texts", "book_count": 1},
        ]

        (stats,) = _rows(out / "core.pack", "SELECT * FROM corpus_stats")
        assert (stats["books"], stats["genres"], stats["diaries"]) == (2, 2, 1)

    def test_chapter_list_is_servable_from_the_packs(self, packs):
        """The Browse drill, entirely offline: book → its chapters."""
        _, out = packs
        (book,) = _rows(
            out / "core.pack", "SELECT file_path FROM books WHERE key='philosophy/Leviathan'"
        )
        chapters = _rows(
            out / "gutenberg.pack",
            "SELECT id, COALESCE(node_title, name) AS title FROM passages "
            "WHERE kind='section' AND file_path=? ORDER BY char_start",
            (book["file_path"],),
        )
        assert chapters == [{"id": "gutenberg:sec:1", "title": "Of Man"}]


class TestManifest:
    def test_names_the_embedder_the_packs_require(self, packs):
        report, out = packs
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["embedder"]["model"] == "BAAI/bge-small-en-v1.5"
        assert manifest["embedder"]["dim"] == 384
        assert manifest["rrf_k"] == 60
        assert {p["name"] for p in manifest["packs"]} == {
            "core.pack",
            "gutenberg.pack",
            "diaries.pack",
        }
        assert manifest["total_bytes"] == report.total_bytes

    def test_every_pack_is_checksummed(self, packs):
        _, out = packs
        manifest = json.loads((out / "manifest.json").read_text())
        for pack in manifest["packs"]:
            assert len(pack["sha256"]) == 64


class TestGuards:
    def test_refuses_to_clobber_without_force(self, bundle, tmp_path):
        out = tmp_path / "swift"
        options = ExportOptions(bundle=bundle, out=out, with_vectors=False, golden=False)
        export_swift(options)
        with pytest.raises(ExportError, match="--force"):
            export_swift(options)

    def test_rejects_an_unknown_dtype(self, bundle, tmp_path):
        with pytest.raises(ExportError, match="int8"):
            export_swift(
                ExportOptions(bundle=bundle, out=tmp_path / "x", dtype="fp16", golden=False)
            )


class TestHelpers:
    def test_rrf_matches_the_handlers_arithmetic(self):
        # A hit both channels rank wins over one only the dense channel found.
        assert rrf_fuse(["a", "b", "c"], ["c", "d"], 3) == ["c", "a", "b"]

    def test_fts_expression_survives_punctuation(self):
        assert fts_match_expression("What does the Quran say about Moses?").endswith('"Moses"')
        assert "?" not in fts_match_expression("Moses?")

    def test_fts_expression_of_pure_punctuation_is_empty(self):
        assert fts_match_expression("!!! ???") == ""

    def test_phrase_expression_keeps_the_terms_adjacent(self):
        assert fts_phrase_expression("pillar of salt") == '"pillar of salt"'
        assert fts_phrase_expression("Moses?") == '"Moses"'
        assert fts_phrase_expression("!!! ???") == ""

    def test_truncate_cuts_at_a_word_boundary(self):
        assert _truncate("the quick brown fox", 12) == "the quick…"
        assert _truncate("short", 100) == "short"

    def test_split_source_path(self):
        assert split_source_path("philosophy/Leviathan/leviathan.md") == (
            "philosophy",
            "Leviathan",
        )
        assert split_source_path(None) == (None, None)
        assert split_source_path("bare.md") == (None, None)


def _seed_source_vectors(bundle, axes, *, store=None):
    """Give a store in the fixture bundle a vec0 source, as a real bundle has.

    The *source* is still sqlite-vec — that is what `dockg convert-index`
    produces — even though the pack it becomes is not.

    :param store: The `.dockg`/`.diarykg` directory to seed; defaults to the
        bundle's consolidated `.dockg`.
    """
    import numpy as np

    from gutenberg_kg.export_swift import EMBED_DIM, _connect_with_vec

    con = _connect_with_vec((store or bundle / ".dockg") / "vectors.sqlite")
    con.execute("CREATE TABLE vec_meta(id TEXT PRIMARY KEY, kind TEXT)")
    con.execute(
        f"CREATE VIRTUAL TABLE vec_nodes USING vec0(embedding float[{EMBED_DIM}] "
        "distance_metric=cosine)"
    )
    for rowid, (node_id, axis) in enumerate(axes, start=1):
        vector = np.zeros(EMBED_DIM, dtype=np.float32)
        vector[axis] = 1.0
        con.execute(
            "INSERT INTO vec_meta(rowid, id, kind) VALUES (?, ?, 'chunk')", (rowid, node_id)
        )
        con.execute(
            "INSERT INTO vec_nodes(rowid, embedding) VALUES (?, ?)", (rowid, vector.tobytes())
        )
    con.commit()
    con.close()


@pytest.mark.skipif(
    find_spec("sqlite_vec") is None or find_spec("numpy") is None,
    reason="vector packs need sqlite-vec (to read the source) and numpy",
)
class TestVectorSidecar:
    """The vectors live beside the pack, not inside it.

    A ``vec0`` table cannot be read without the sqlite-vec C extension, and
    iOS ships stock SQLite — so the pack would be unopenable on the device it
    was built for. The sidecar is a header plus row-major vectors, which any
    platform can memory-map.
    """

    def test_sidecar_is_written_with_a_valid_header(self, bundle, tmp_path):
        from gutenberg_kg.export_swift import (
            EMBED_DIM,
            VECTOR_HEADER_BYTES,
            VECTOR_MAGIC,
            read_vector_sidecar,
        )

        _seed_source_vectors(bundle, [("c:1", 0), ("c:2", 1)])
        out = tmp_path / "swift"
        export_swift(ExportOptions(bundle=bundle, out=out, golden=False, force=True))

        sidecar = out / "gutenberg.vectors"
        assert sidecar.read_bytes()[:8] == VECTOR_MAGIC
        matrix, dtype = read_vector_sidecar(sidecar)
        assert matrix.shape == (2, EMBED_DIM)
        assert dtype == "int8"
        assert sidecar.stat().st_size == VECTOR_HEADER_BYTES + 2 * EMBED_DIM

    def test_pack_carries_no_vec0_table(self, bundle, tmp_path):
        """The pack must open on stock SQLite, with no extension loaded."""
        _seed_source_vectors(bundle, [("c:1", 0), ("c:2", 1)])
        out = tmp_path / "swift"
        export_swift(ExportOptions(bundle=bundle, out=out, golden=False, force=True))

        con = sqlite3.connect(str(out / "gutenberg.pack"))
        try:
            names = {
                row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            # A plain connection can read every table in the pack.
            for name in names:
                con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()
        finally:
            con.close()
        assert "vec_nodes" not in names

    def test_vector_index_is_dense_and_points_at_the_right_row(self, bundle, tmp_path):
        """A passage with no source vector must not leave a hole in the file."""
        import numpy as np

        from gutenberg_kg.export_swift import read_vector_sidecar

        _seed_source_vectors(bundle, [("c:1", 0), ("s:1", 7)])
        out = tmp_path / "swift"
        export_swift(ExportOptions(bundle=bundle, out=out, golden=False, force=True))

        rows = _rows(
            out / "gutenberg.pack",
            "SELECT id, vector_index FROM passages ORDER BY vector_index",
        )
        indexed = {r["id"]: r["vector_index"] for r in rows if r["vector_index"] is not None}
        assert sorted(indexed.values()) == [0, 1]
        # c:2 and sec:1 had no vector in the source and stay unindexed.
        assert {r["id"] for r in rows if r["vector_index"] is None} == {
            "gutenberg:c:2",
            "gutenberg:sec:1",
        }

        matrix, _ = read_vector_sidecar(out / "gutenberg.vectors")
        assert int(np.argmax(matrix[indexed["gutenberg:c:1"]])) == 0
        assert int(np.argmax(matrix[indexed["gutenberg:s:1"]])) == 7

    def test_missing_vectors_are_counted_not_hidden(self, bundle, tmp_path):
        _seed_source_vectors(bundle, [("c:1", 0)])
        out = tmp_path / "swift"
        report = export_swift(ExportOptions(bundle=bundle, out=out, golden=False, force=True))
        pack = next(p for p in report.packs if p.name == "gutenberg.pack")
        assert pack.vectors == 1
        assert pack.missing_vectors == pack.passages - 1

    def test_truncated_sidecar_is_rejected(self, bundle, tmp_path):
        from gutenberg_kg.export_swift import ExportError, read_vector_sidecar

        _seed_source_vectors(bundle, [("c:1", 0), ("c:2", 1)])
        out = tmp_path / "swift"
        export_swift(ExportOptions(bundle=bundle, out=out, golden=False, force=True))

        sidecar = out / "gutenberg.vectors"
        sidecar.write_bytes(sidecar.read_bytes()[:-16])
        with pytest.raises(ExportError, match="truncated"):
            read_vector_sidecar(sidecar)

    def test_manifest_lists_the_sidecar(self, bundle, tmp_path):
        _seed_source_vectors(bundle, [("c:1", 0)])
        out = tmp_path / "swift"
        report = export_swift(ExportOptions(bundle=bundle, out=out, golden=False, force=True))
        manifest = json.loads((out / "manifest.json").read_text())
        entry = next(p for p in manifest["packs"] if p["name"] == "gutenberg.pack")
        assert entry["sidecar"]["name"] == "gutenberg.vectors"
        assert len(entry["sidecar"]["sha256"]) == 64
        # Total bytes must include the sidecar: it is what has to reach the phone.
        assert manifest["total_bytes"] == report.total_bytes
        assert manifest["total_bytes"] >= entry["sidecar"]["bytes"]


@pytest.mark.skipif(
    find_spec("sqlite_vec") is None or find_spec("numpy") is None,
    reason="the reference search needs sqlite-vec and numpy",
)
class TestSearchPack:
    """The reference query path — the specification Swift's engine must match.

    Vectors here are one-hot unit vectors, so the cosine ranking is exactly
    known and every assertion is about the retrieval logic rather than about an
    embedder's opinion.
    """

    @staticmethod
    def _basis(axis):
        import numpy as np

        from gutenberg_kg.export_swift import EMBED_DIM

        vector = np.zeros(EMBED_DIM, dtype=np.float32)
        vector[axis] = 1.0
        return vector

    @pytest.fixture
    def searchable(self, bundle, tmp_path):
        """A pack whose three passages sit on three orthogonal axes."""
        _seed_source_vectors(bundle, [("c:1", 0), ("c:2", 1), ("s:1", 2)])
        out = tmp_path / "searchable"
        export_swift(ExportOptions(bundle=bundle, out=out, golden=False, force=True))
        return out / "gutenberg.pack"

    def test_dense_channel_ranks_by_cosine(self, searchable):
        from gutenberg_kg.export_swift import search_pack

        # "zzzz" matches nothing lexically, so this is the dense channel alone.
        hits = search_pack(searchable, self._basis(2), "zzzz", k=3)
        assert hits[0]["node_id"] == "gutenberg:s:1"
        assert hits[0]["score"] == pytest.approx(1.0, abs=0.02)

    def test_hits_carry_the_worker_hit_shape(self, searchable):
        from gutenberg_kg.export_swift import search_pack

        (hit, *_) = search_pack(searchable, self._basis(2), "zzzz", k=1)
        assert set(hit) >= {
            "kg_name",
            "kg_kind",
            "node_id",
            "name",
            "kind",
            "score",
            "source_path",
            "content",
            "timestamp",
            "genre",
            "title",
            "author",
        }
        assert hit["genre"] == "sacred-texts"
        assert "pillar of salt" in hit["content"]

    def test_genre_filter_scopes_both_channels(self, searchable):
        from gutenberg_kg.export_swift import search_pack

        hits = search_pack(searchable, self._basis(2), "pillar of salt", k=5, genre="philosophy")
        assert {hit["node_id"] for hit in hits} <= {
            "gutenberg:c:1",
            "gutenberg:c:2",
            "gutenberg:sec:1",
        }
        assert all(hit["genre"] == "philosophy" for hit in hits)

    def test_lexical_channel_rescues_what_the_embedder_buries(self, searchable):
        """The 'circles of Hell' case, in miniature.

        The query vector points squarely at ``c:1``, so dense ranking alone
        returns it. BM25 finds the literal terms in ``s:1``, and RRF promotes
        it past the dense winner — which is the whole reason the lexical
        channel exists.

        The query is content words only. ``fts_match_expression`` ORs every
        term, so in a four-passage fixture a stop word like "of" is a genuine
        match that shifts the ranks; across 364 K real passages it matches
        almost everything and BM25's IDF weighting reduces it to noise. The
        fixture cannot show that, so it does not pretend to.
        """
        from gutenberg_kg.export_swift import search_pack

        dense_only = search_pack(searchable, self._basis(0), "zzzz", k=1)
        assert dense_only[0]["node_id"] == "gutenberg:c:1"

        fused = search_pack(searchable, self._basis(0), "pillar salt", k=1)
        assert fused[0]["node_id"] == "gutenberg:s:1"

    def test_phrase_beats_the_or_fallback(self, searchable):
        """The "pillar of salt" case — the one that motivated the channel.

        The dense vector points at ``c:1``, so cosine alone returns it. The
        literal verse lives in ``s:1``. Searching the exact phrase must find
        ``s:1`` and let RRF promote it: an OR over the terms puts the stop word
        "of" in play, which across 364 K real passages matches nearly
        everything and dilutes BM25 until the verse is unreachable. That is the
        failure this two-step exists to prevent, so it is asserted here rather
        than left to the corpus to demonstrate.
        """
        from gutenberg_kg.export_swift import search_pack

        fused = search_pack(searchable, self._basis(0), "pillar of salt", k=1)
        assert fused[0]["node_id"] == "gutenberg:s:1"

    def test_or_fallback_runs_when_no_passage_holds_the_phrase(self, searchable):
        """No passage contains "pillar salt" adjacently, so the phrase misses.

        Falling back to the any-term query is what keeps that from returning
        nothing — `s:1` is still reachable through the terms it does hold.
        """
        from gutenberg_kg.export_swift import search_pack

        assert fts_phrase_expression("pillar salt") == '"pillar salt"'
        fused = search_pack(searchable, self._basis(0), "pillar salt", k=1)
        assert fused[0]["node_id"] == "gutenberg:s:1"

    def test_lexical_false_gives_the_dense_channel_alone(self, searchable):
        """`verify_pack` measures quantisation, so it must not fuse BM25.

        Same setup as the rescue test above: lexically, "pillar salt" promotes
        `s:1` past the dense winner. With `lexical=False` that channel is off
        and the dense winner stands — which is what dense-only fp32 ground
        truth expects. Comparing the *hybrid* top-k against dense truth is the
        bug that reported recall 0.567 while true int8 recall was 0.958.
        """
        from gutenberg_kg.export_swift import search_pack

        dense = search_pack(searchable, self._basis(0), "pillar salt", k=1, lexical=False)
        assert dense[0]["node_id"] == "gutenberg:c:1"

    def test_min_score_drops_weak_hits(self, searchable):
        from gutenberg_kg.export_swift import search_pack

        # Orthogonal passages score ~0.0; only the on-axis one clears the floor.
        hits = search_pack(searchable, self._basis(2), "zzzz", k=3, min_score=0.5)
        assert [hit["node_id"] for hit in hits] == ["gutenberg:s:1"]


EVELYN_DIR = "The Diary of John Evelyn — Volume 1"
PEPYS_DIR = "The Diary of Samuel Pepys — Complete"


class TestCrossDiaryIdCollisions:
    """Diary node ids repeat across books, and the pack must survive that.

    Real diary ids look like ``chunk:entry_0000_chunk_0.md:0000`` — the entry
    file within a book, not the book — and every diary numbers its entries
    from ``entry_0000``. Before the ``<kg_name>:`` prefix, merging four
    diaries into one id-keyed table dropped 4,601 of 27,462 passages via
    ``INSERT OR IGNORE``, silently: every later diary lost the rows whose ids
    an earlier diary had already claimed.
    """

    @pytest.fixture
    def colliding_bundle(self, bundle):
        """The fixture bundle plus a second diary reusing the same node ids."""
        _graph(
            bundle / "diaries" / EVELYN_DIR / ".diarykg" / "graph.sqlite",
            DIARY_COLUMNS,
            [
                (
                    "p:1",
                    "chunk",
                    "September 2nd 1666",
                    "The dreadful fire near Fish Street.",
                    "1666-09-02T00:00:00",
                ),
                (
                    "p:2",
                    "chunk",
                    "September 3rd 1666",
                    "The fire increasing to Cheapside.",
                    "1666-09-03T00:00:00",
                ),
            ],
            edges=False,
        )
        return bundle

    def test_colliding_ids_all_survive_with_their_own_content(self, colliding_bundle, tmp_path):
        out = tmp_path / "swift"
        export_swift(
            ExportOptions(
                bundle=colliding_bundle, out=out, with_vectors=False, golden=False, force=True
            )
        )
        rows = _rows(out / "diaries.pack", "SELECT id, kg_name, content FROM passages")
        assert {r["id"] for r in rows} == {
            "evelyn-volume-1:p:1",
            "evelyn-volume-1:p:2",
            "pepys-complete:p:1",
            "pepys-complete:p:2",
        }
        by_id = {r["id"]: r for r in rows}
        assert by_id["evelyn-volume-1:p:1"]["content"].startswith("The dreadful fire")
        assert by_id["pepys-complete:p:1"]["content"].startswith("The poor pigeons")

    def test_reported_passage_count_matches_the_pack(self, colliding_bundle, tmp_path):
        """The log counts real inserts, not attempts — the drop was invisible
        because ``stats.passages`` tallied attempted rows."""
        out = tmp_path / "swift"
        report = export_swift(
            ExportOptions(
                bundle=colliding_bundle, out=out, with_vectors=False, golden=False, force=True
            )
        )
        pack = next(p for p in report.packs if p.name == "diaries.pack")
        (count,) = _rows(out / "diaries.pack", "SELECT COUNT(*) AS n FROM passages")
        assert pack.passages == count["n"] == 4

    @pytest.mark.skipif(
        find_spec("sqlite_vec") is None or find_spec("numpy") is None,
        reason="vector packs need sqlite-vec and numpy",
    )
    def test_each_diary_keeps_its_own_vector(self, colliding_bundle, tmp_path):
        """A diary's vector must not claim another diary's colliding row."""
        import numpy as np

        from gutenberg_kg.export_swift import read_vector_sidecar

        root = colliding_bundle / "diaries"
        _seed_source_vectors(colliding_bundle, [("p:1", 3)], store=root / EVELYN_DIR / ".diarykg")
        _seed_source_vectors(colliding_bundle, [("p:1", 5)], store=root / PEPYS_DIR / ".diarykg")
        out = tmp_path / "swift"
        export_swift(ExportOptions(bundle=colliding_bundle, out=out, golden=False, force=True))

        rows = _rows(
            out / "diaries.pack",
            "SELECT id, vector_index FROM passages WHERE vector_index IS NOT NULL",
        )
        indexed = {r["id"]: r["vector_index"] for r in rows}
        assert set(indexed) == {"evelyn-volume-1:p:1", "pepys-complete:p:1"}

        matrix, _ = read_vector_sidecar(out / "diaries.vectors")
        assert int(np.argmax(matrix[indexed["evelyn-volume-1:p:1"]])) == 3
        assert int(np.argmax(matrix[indexed["pepys-complete:p:1"]])) == 5


class TestWindowOversizedSections:
    """Browse-only splitting of sections too large to read as one chapter."""

    @staticmethod
    def _pack(path, chunk_count):
        con = sqlite3.connect(str(path))
        con.executescript(_PASSAGE_SCHEMA)
        con.execute(
            "INSERT INTO passages (id, kg_name, kg_kind, kind, name, title, node_title, "
            " author, genre, book, file_path, char_start, content) "
            "VALUES ('g:sec:1','gutenberg','doc','section','body','A Book','THE BODY',"
            " 'A. Author','biography','A Book',?,0,'')",
            (DOC,),
        )
        con.executemany(
            "INSERT INTO passages (id, kg_name, kg_kind, kind, name, title, file_path, "
            " char_start, content) VALUES (?,'gutenberg','doc','chunk','c','A Book',?,?,'text')",
            [(f"g:c:{i}", DOC, i * 100) for i in range(chunk_count)],
        )
        con.commit()
        return con

    def test_splits_a_monolithic_section_into_parts(self, tmp_path):
        con = self._pack(tmp_path / "p.pack", 25)
        added = window_oversized_sections(con, max_chunks=10)
        assert added == 2

        rows = list(
            con.execute(
                "SELECT id, node_title, char_start, content, kind FROM passages "
                "WHERE kind='section' ORDER BY char_start"
            )
        )
        assert [r[1] for r in rows] == [
            "THE BODY (Part 1 of 3)",
            "THE BODY (Part 2 of 3)",
            "THE BODY (Part 3 of 3)",
        ]
        # The parent keeps its id, so anything holding one still resolves.
        assert rows[0][0] == "g:sec:1"
        # New markers land on real chunk boundaries and carry no prose.
        assert [r[2] for r in rows] == [0, 900, 1800]
        assert all(r[3] == "" for r in rows[1:])
        con.close()

    def test_leaves_a_section_within_budget_alone(self, tmp_path):
        con = self._pack(tmp_path / "p.pack", 10)
        assert window_oversized_sections(con, max_chunks=10) == 0
        (title,) = con.execute("SELECT node_title FROM passages WHERE kind='section'").fetchone()
        assert title == "THE BODY"
        con.close()

    def test_disabled_by_a_non_positive_budget(self, tmp_path):
        con = self._pack(tmp_path / "p.pack", 500)
        assert window_oversized_sections(con, max_chunks=0) == 0
        con.close()
