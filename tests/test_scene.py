"""Tests for the Qt-free scene layer: KG discovery, layout, headless build."""

import sqlite3

import numpy as np
import pytest

# The modules under test import pyvista at module scope, which CI does not
# install (the viz3d extra is optional).  Skip at collection time rather than
# letting the import blow up the whole run.
pytest.importorskip("pyvista")

from gutenberg_kg.scene import (  # noqa: E402
    KG_DIRS,
    BookMeta,
    ForestLayout,
    SceneFilters,
    load_book_graph,
    load_entry_times,
    scan_corpus,
)

pv = pytest.importorskip("pyvista")


# ---------------------------------------------------------------------------
# Fixtures — synthetic book graphs in the two schemas the corpus actually holds
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE nodes (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
    title TEXT, file_path TEXT, text TEXT, timestamp TEXT
);
CREATE TABLE edges (src TEXT, rel TEXT, dst TEXT);
"""


def _write_graph(db_path, nodes, edges):
    """Create a minimal DocKG/DiaryKG-shaped SQLite graph."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(_SCHEMA)
    con.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?,?)", nodes)
    con.executemany("INSERT INTO edges VALUES (?,?,?)", edges)
    con.commit()
    con.close()


def _prose_book(book_dir, n_sections=4, chunks_per_section=5):
    """A .dockg book: one document, sections, chunks under each section."""
    nodes = [("doc:book", "document", "book", "Book", "book.md", None, None)]
    edges = []
    for s in range(n_sections):
        sid = f"sec:{s}"
        nodes.append((sid, "section", f"s{s}", f"Section {s}", "book.md", None, None))
        edges.append(("doc:book", "CONTAINS", sid))
        for c in range(chunks_per_section):
            cid = f"chunk:{s}:{c}"
            nodes.append((cid, "chunk", f"c{s}{c}", None, "book.md", "text", None))
            edges.append((sid, "CONTAINS", cid))
    _write_graph(book_dir / ".dockg" / "graph.sqlite", nodes, edges)


def _diary_book(book_dir, years=(1660, 1661, 1662), entries_per_year=6):
    """A .diarykg book: one document per dated entry, no sections."""
    nodes, edges = [], []
    i = 0
    for year in years:
        for _ in range(entries_per_year):
            did = f"doc:entry_{i:04d}.md"
            nodes.append((did, "document", f"entry_{i:04d}", None, f"e{i}.md", None, None))
            for c in range(2):
                cid = f"chunk:entry_{i:04d}:{c}"
                nodes.append(
                    (cid, "chunk", f"c{i}{c}", None, f"e{i}.md", "text", f"{year}-01-01T00:00")
                )
                edges.append((did, "CONTAINS", cid))
            i += 1
    _write_graph(book_dir / ".diarykg" / "graph.sqlite", nodes, edges)


@pytest.fixture
def corpus(tmp_path):
    """A corpus with one prose genre and one diary genre."""
    _prose_book(tmp_path / "philosophy" / "A Treatise")
    _diary_book(tmp_path / "diaries" / "A Diary")
    return tmp_path


# ---------------------------------------------------------------------------
# KG discovery
# ---------------------------------------------------------------------------


class TestBookMeta:
    def test_dockg_and_diarykg_are_both_probed(self):
        assert KG_DIRS == (".dockg", ".diarykg")

    def test_prose_book_resolves_to_dockg(self, corpus):
        meta = BookMeta("A Treatise", "philosophy", corpus / "philosophy" / "A Treatise")
        assert meta.has_kg
        assert meta.kg_dir is not None and meta.kg_dir.name == ".dockg"

    def test_diary_book_resolves_to_diarykg(self, corpus):
        meta = BookMeta("A Diary", "diaries", corpus / "diaries" / "A Diary")
        assert meta.has_kg
        assert meta.kg_dir is not None and meta.kg_dir.name == ".diarykg"

    def test_book_without_any_graph_is_not_ingested(self, tmp_path):
        (tmp_path / "empty").mkdir()
        assert not BookMeta("empty", "g", tmp_path / "empty").has_kg

    def test_db_path_is_defined_even_without_a_graph(self, tmp_path):
        meta = BookMeta("empty", "g", tmp_path / "empty")
        assert meta.db_path.name == "graph.sqlite"

    def test_slug_is_filesystem_safe(self):
        meta = BookMeta("The Diary of John Evelyn — Volume 1", "diaries", None)  # type: ignore[arg-type]
        assert meta.slug == "the_diary_of_john_evelyn_volume_1"


class TestScanCorpus:
    def test_scan_finds_both_kg_flavours(self, corpus):
        found = scan_corpus(corpus)
        assert set(found) == {"philosophy", "diaries"}

    def test_diary_books_are_no_longer_invisible(self, corpus):
        # Regression: scan_corpus probed only .dockg, so every diary in the
        # corpus was silently absent from the forest.
        assert [b.title for b in scan_corpus(corpus)["diaries"]] == ["A Diary"]


class TestLoadEntryTimes:
    def test_diary_entries_carry_dates_from_their_chunks(self, corpus):
        meta = BookMeta("A Diary", "diaries", corpus / "diaries" / "A Diary")
        times = load_entry_times(meta)
        assert len(times) == 18
        assert all(t.startswith(("1660", "1661", "1662")) for t in times.values())

    def test_ids_are_namespaced_like_the_graph(self, corpus):
        meta = BookMeta("A Diary", "diaries", corpus / "diaries" / "A Diary")
        assert all(k.startswith(f"{meta.slug}:") for k in load_entry_times(meta))

    def test_prose_book_has_no_dates(self, corpus):
        meta = BookMeta("A Treatise", "philosophy", corpus / "philosophy" / "A Treatise")
        assert load_entry_times(meta) == {}


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def _load(corpus, genre, title):
    meta = BookMeta(title, genre, corpus / genre / title)
    nodes, edges = load_book_graph(meta)
    return meta, nodes, edges


class TestForestLayoutProse:
    def test_every_node_is_placed(self, corpus):
        meta, nodes, edges = _load(corpus, "philosophy", "A Treatise")
        positions = ForestLayout(book_genre_map={meta.slug: meta.genre}).compute(nodes, edges)
        assert set(positions) == {n.id for n in nodes}

    def test_document_marks_the_trunk_base(self, corpus):
        meta, nodes, edges = _load(corpus, "philosophy", "A Treatise")
        layout = ForestLayout(book_genre_map={meta.slug: meta.genre})
        positions = layout.compute(nodes, edges)
        doc = next(n for n in nodes if n.kind == "document")
        assert positions[doc.id][2] == pytest.approx(0.0)
        assert layout.trunk_heights[doc.id] > 0

    def test_prose_books_promote_nothing(self, corpus):
        meta, nodes, edges = _load(corpus, "philosophy", "A Treatise")
        layout = ForestLayout(book_genre_map={meta.slug: meta.genre})
        layout.compute(nodes, edges)
        assert layout.branch_documents == set()
        assert layout.book_periods == {}


class TestForestLayoutDiary:
    def test_entries_become_branches_not_stacked_trunks(self, corpus):
        meta, nodes, edges = _load(corpus, "diaries", "A Diary")
        layout = ForestLayout(book_genre_map={meta.slug: meta.genre})
        layout.compute(nodes, edges)
        # One synthetic trunk, not one per dated entry.
        assert len(layout.trunk_positions) == 1
        assert len(layout.branch_documents) == 18

    def test_dated_limbs_are_calendar_years(self, corpus):
        meta, nodes, edges = _load(corpus, "diaries", "A Diary")
        layout = ForestLayout(
            book_genre_map={meta.slug: meta.genre}, entry_times=load_entry_times(meta)
        )
        layout.compute(nodes, edges)
        labels = [label for label, _ in layout.book_periods[meta.slug]]
        assert labels == ["1660", "1661", "1662"]

    def test_limb_weight_is_the_entry_count(self, corpus):
        meta, nodes, edges = _load(corpus, "diaries", "A Diary")
        layout = ForestLayout(
            book_genre_map={meta.slug: meta.genre}, entry_times=load_entry_times(meta)
        )
        layout.compute(nodes, edges)
        assert [count for _, count in layout.book_periods[meta.slug]] == [6, 6, 6]

    def test_undated_entries_fall_back_to_ordered_parts(self, corpus):
        meta, nodes, edges = _load(corpus, "diaries", "A Diary")
        layout = ForestLayout(book_genre_map={meta.slug: meta.genre})  # no entry_times
        layout.compute(nodes, edges)
        labels = [label for label, _ in layout.book_periods[meta.slug]]
        assert labels and all(label.startswith("part ") for label in labels)

    def test_entries_cluster_by_limb_rather_than_one_blob(self, corpus):
        meta, nodes, edges = _load(corpus, "diaries", "A Diary")
        layout = ForestLayout(
            book_genre_map={meta.slug: meta.genre}, entry_times=load_entry_times(meta)
        )
        positions = layout.compute(nodes, edges)
        docs = [n for n in nodes if n.kind == "document"]
        by_year = {}
        for doc in docs:
            year = load_entry_times(meta)[doc.id][:4]
            by_year.setdefault(year, []).append(positions[doc.id])
        centres = {y: np.mean(p, axis=0) for y, p in by_year.items()}
        # Successive years sit at successive heights up the trunk.
        heights = [centres[y][2] for y in sorted(centres)]
        assert heights == sorted(heights)


# ---------------------------------------------------------------------------
# Headless scene building
# ---------------------------------------------------------------------------


class TestSceneFilters:
    def test_documents_are_always_visible(self):
        assert "document" in SceneFilters(show_sections=False, show_chunks=False).visible_kinds()

    def test_entity_toggle_covers_the_floating_kinds(self):
        kinds = SceneFilters(show_entities=True).visible_kinds()
        assert {"entity", "topic", "keyword"} <= kinds

    def test_relations_follow_their_toggles(self):
        assert SceneFilters().visible_rels() == set()
        assert SceneFilters(show_contains=True, show_next=True).visible_rels() == {
            "CONTAINS",
            "NEXT",
        }


class TestBuildForestScene:
    def test_builds_without_qt(self, corpus):
        from gutenberg_kg.scene import build_forest_scene

        meta, nodes, edges = _load(corpus, "philosophy", "A Treatise")
        plotter = pv.Plotter(off_screen=True)
        info = build_forest_scene(nodes, edges, plotter, book_genre_map={meta.slug: meta.genre})
        assert info.n_books == 1
        assert info.counts["chunk"] == 20
        assert info.positions
        plotter.close()

    def test_progress_is_reported_through_the_callback(self, corpus):
        from gutenberg_kg.scene import build_forest_scene

        meta, nodes, edges = _load(corpus, "philosophy", "A Treatise")
        seen: list[str] = []
        plotter = pv.Plotter(off_screen=True)
        build_forest_scene(
            nodes, edges, plotter, book_genre_map={meta.slug: meta.genre}, progress=seen.append
        )
        assert seen and seen[-1] == "Forest rendered."
        plotter.close()

    def test_diary_entries_are_counted_as_branches(self, corpus):
        from gutenberg_kg.scene import build_forest_scene

        meta, nodes, edges = _load(corpus, "diaries", "A Diary")
        plotter = pv.Plotter(off_screen=True)
        info = build_forest_scene(nodes, edges, plotter, book_genre_map={meta.slug: meta.genre})
        # Promoted entry documents render as sections, not as 18 trunk markers.
        assert info.counts["section"] == 18
        assert info.counts["document"] == 0
        plotter.close()


class TestBuildTreeScene:
    def test_grows_a_branching_tree(self, corpus):
        from gutenberg_kg.scene import build_tree_scene

        meta, nodes, edges = _load(corpus, "philosophy", "A Treatise")
        plotter = pv.Plotter(off_screen=True)
        info = build_tree_scene(nodes, edges, plotter, slug=meta.slug, genre=meta.genre)
        assert info.skeleton is not None
        assert info.skeleton.n_nodes > 1
        assert info.skeleton.radii is not None
        plotter.close()

    def test_tree_stands_at_the_origin(self, corpus):
        from gutenberg_kg.scene import build_tree_scene

        meta, nodes, edges = _load(corpus, "philosophy", "A Treatise")
        plotter = pv.Plotter(off_screen=True)
        build_tree_scene(nodes, edges, plotter, slug=meta.slug, genre=meta.genre)
        xmin, xmax, ymin, ymax, _, _ = plotter.bounds
        assert abs((xmin + xmax) / 2) < 20.0
        assert abs((ymin + ymax) / 2) < 20.0
        plotter.close()

    def test_a_book_without_chunks_is_refused_clearly(self, corpus):
        from gutenberg_kg.scene import build_tree_scene

        meta, nodes, edges = _load(corpus, "philosophy", "A Treatise")
        bare = [n for n in nodes if n.kind != "chunk"]
        plotter = pv.Plotter(off_screen=True)
        with pytest.raises(ValueError, match="no chunk positions"):
            build_tree_scene(bare, edges, plotter, slug=meta.slug, genre=meta.genre)
        plotter.close()
