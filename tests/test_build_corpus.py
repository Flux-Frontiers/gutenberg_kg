"""Unit tests for gutenberg_kg.build_corpus — the consolidated corpus build.

Scoped to what is testable without doc_kg's embedder: the pure selection and
filtering logic (derive_exclude, assert_selection, build_catalog,
bundle_diaries, write_product_json), plus the two run_build_corpus paths that
return before touching doc_kg at all (the force-overwrite-full guard and
--dry-run). The real embedding pipeline is exercised by hand
(`make build-corpus`), not here — the same boundary test_export_swift.py
draws around sqlite-vec/numpy.

These are the first tests this module has had. Phase 2's `test_export_swift.py`
established the pattern followed here: monkeypatch the module's CORPUS_ROOT to
a synthetic fixture tree rather than depend on the real corpus's contents.
"""

from __future__ import annotations

import json

import pytest

from gutenberg_kg.build_corpus import (
    BuildCorpusOptions,
    BuildError,
    _diary_dirs_for_product,
    assert_selection,
    build_catalog,
    bundle_diaries,
    derive_exclude,
    run_build_corpus,
    write_product_json,
)


def _make_book(corpus_root, genre, title, *, ebook_id=None, author="A. Author"):
    """Create a minimal ``<genre>/<title>/reference.md`` under ``corpus_root``."""
    book_dir = corpus_root / genre / title
    book_dir.mkdir(parents=True)
    lines = [f"# Reference: {title}", "", "## Source", ""]
    if ebook_id is not None:
        lines.append(f"- **Project Gutenberg ID**: {ebook_id}")
    lines += ["", "## Author", "", f"- **Name**: {author}"]
    (book_dir / "reference.md").write_text("\n".join(lines), encoding="utf-8")
    return book_dir


def _make_diary(corpus_root, name, *, marker="graph.sqlite"):
    """A minimal ``corpus/diaries/<name>/`` in the real shape: a
    ``reference.md`` sibling of the ``.diarykg/`` index, the same
    genre-shaped layout ``_all_diary_slugs`` expects."""
    diary_dir = corpus_root / "diaries" / name
    diarykg = diary_dir / ".diarykg"
    diarykg.mkdir(parents=True)
    (diarykg / marker).write_text("not a real index", encoding="utf-8")
    (diary_dir / "reference.md").write_text(f"# Reference: {name}", encoding="utf-8")
    return diarykg


@pytest.fixture
def corpus(tmp_path):
    """Two genres, three books, one with a Gutenberg ID; two diaries."""
    root = tmp_path / "corpus"
    _make_book(root, "philosophy", "The Republic", ebook_id=1497)
    _make_book(root, "philosophy", "Meditations", ebook_id=2680)
    _make_book(root, "english-literature", "Pride and Prejudice", ebook_id=1342)
    _make_diary(root, "The Diary of Samuel Pepys")
    _make_diary(root, "The Diary of John Evelyn")
    return root


# --- derive_exclude --------------------------------------------------------


class TestDeriveExclude:
    def test_only_books_none_leaves_every_sibling_alone(self, corpus, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        exclude = derive_exclude(["philosophy"])
        assert "The Republic" not in exclude
        assert "Meditations" not in exclude

    def test_only_books_excludes_unlisted_siblings(self, corpus, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        exclude = derive_exclude(["philosophy"], only_books={"The Republic"})
        assert "The Republic" not in exclude
        assert "Meditations" in exclude

    def test_only_books_never_touches_an_unselected_genre(self, corpus, monkeypatch):
        """english-literature isn't in `genres`, so its books are irrelevant to
        the only_books loop -- it is excluded wholesale either way, by name,
        the same as any other unselected genre."""
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        exclude = derive_exclude(["philosophy"], only_books={"The Republic"})
        assert "english-literature" in exclude

    def test_missing_genre_directory_is_tolerated(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", tmp_path)
        # No such directory under tmp_path -- must not raise.
        assert derive_exclude(["nonexistent-genre"], only_books={"x"}) is not None


# --- assert_selection --------------------------------------------------------


class TestAssertSelection:
    def test_passes_when_every_file_is_inside_the_selection(self, corpus, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        files = [
            corpus / "philosophy" / "The Republic" / "the_republic.md",
            corpus / "philosophy" / "The Republic" / "reference.md",
        ]
        assert_selection(files, frozenset({"philosophy/The Republic"}))  # no raise

    def test_raises_when_exclude_leaked_an_unselected_book(self, corpus, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        files = [
            corpus / "philosophy" / "The Republic" / "the_republic.md",
            corpus / "philosophy" / "Meditations" / "meditations.md",
        ]
        with pytest.raises(BuildError, match="Meditations"):
            assert_selection(files, frozenset({"philosophy/The Republic"}))

    def test_empty_file_list_never_raises(self):
        assert_selection([], frozenset({"philosophy/The Republic"}))  # no raise

    def test_a_real_cross_genre_name_collision_is_caught_end_to_end(self, tmp_path, monkeypatch):
        """The gap derive_exclude accepts, forced for real and caught by the
        guard it exists for.

        Two genres each have a book directory named "Republic". Only
        philosophy's is wanted, but derive_exclude's only_books check is a
        flat basename set with no genre context: once "Republic" is in it for
        philosophy's sake, ancient-classical's "Republic" survives the same
        exclude too. This walks the real doc_kg.dockg.iter_text_files with
        that exact exclude set -- not a hand-built file list -- so the
        collision is real, not simulated, before assert_selection is asked
        to catch it.
        """
        pytest.importorskip("doc_kg")
        from doc_kg.dockg import iter_text_files

        root = tmp_path / "corpus"
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", root)
        philosophy_republic = _make_book(root, "philosophy", "Republic")
        ancient_republic = _make_book(root, "ancient-classical", "Republic")
        (philosophy_republic / "the_republic.md").write_text("Plato", encoding="utf-8")
        (ancient_republic / "the_republic.md").write_text("Also Plato", encoding="utf-8")

        catalog_keys = frozenset({"philosophy/Republic"})
        exclude = derive_exclude(["philosophy", "ancient-classical"], only_books={"Republic"})

        # The gap: ancient-classical's Republic was never excluded.
        assert "Republic" not in exclude

        walked = iter_text_files(root, exclude=exclude)
        with pytest.raises(BuildError, match="ancient-classical/Republic"):
            assert_selection(walked, catalog_keys)


# --- build_catalog -----------------------------------------------------------


class TestBuildCatalog:
    def test_no_catalog_keys_catalogues_every_book_in_the_genres(
        self, corpus, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        n_cat, n_auth = build_catalog(["philosophy"], out_dir)
        assert n_cat == 2
        assert n_auth == 2
        catalog = json.loads((out_dir / "catalog.json").read_text())
        assert set(catalog) == {"philosophy/The Republic", "philosophy/Meditations"}

    def test_catalog_keys_filters_to_the_given_books(self, corpus, tmp_path, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        n_cat, _ = build_catalog(
            ["philosophy"], out_dir, catalog_keys=frozenset({"philosophy/The Republic"})
        )
        assert n_cat == 1
        catalog = json.loads((out_dir / "catalog.json").read_text())
        assert set(catalog) == {"philosophy/The Republic"}

    def test_ebook_id_and_author_survive_the_filter(self, corpus, tmp_path, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        build_catalog(["philosophy"], out_dir, catalog_keys=frozenset({"philosophy/The Republic"}))
        catalog = json.loads((out_dir / "catalog.json").read_text())
        assert catalog["philosophy/The Republic"]["ebook_id"] == 1497
        assert catalog["philosophy/The Republic"]["author"] == "A. Author"


# --- bundle_diaries ------------------------------------------------------------


class TestBundleDiaries:
    def test_none_copies_every_diary_found(self, corpus, tmp_path, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        out_dir = tmp_path / "bundle" / ".dockg"
        out_dir.mkdir(parents=True)
        n = bundle_diaries(out_dir)
        assert n == 2
        copied = {p.name for p in (tmp_path / "bundle" / "diaries").iterdir()}
        assert copied == {"The Diary of Samuel Pepys", "The Diary of John Evelyn"}

    def test_empty_tuple_copies_none(self, corpus, tmp_path, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        out_dir = tmp_path / "bundle" / ".dockg"
        out_dir.mkdir(parents=True)
        n = bundle_diaries(out_dir, diary_dirs=())
        assert n == 0
        assert not (tmp_path / "bundle" / "diaries").exists()

    def test_explicit_slug_copies_only_the_matching_diary(self, corpus, tmp_path, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        out_dir = tmp_path / "bundle" / ".dockg"
        out_dir.mkdir(parents=True)
        n = bundle_diaries(out_dir, diary_dirs=("pepys",))
        assert n == 1
        copied = {p.name for p in (tmp_path / "bundle" / "diaries").iterdir()}
        assert copied == {"The Diary of Samuel Pepys"}

    def test_no_diaries_directory_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", tmp_path / "empty-corpus")
        out_dir = tmp_path / "bundle" / ".dockg"
        out_dir.mkdir(parents=True)
        assert bundle_diaries(out_dir) == 0


# --- write_product_json -------------------------------------------------------


class TestWriteProductJson:
    def test_records_selection_and_checksums(self, tmp_path):
        bundle_dir = tmp_path / "philosophy-starter"
        dockg = bundle_dir / ".dockg"
        dockg.mkdir(parents=True)
        (dockg / "graph.sqlite").write_bytes(b"fake graph")
        (dockg / "catalog.json").write_text("{}", encoding="utf-8")
        # vectors.sqlite deliberately absent -- must not be required.

        path = write_product_json(
            bundle_dir,
            name="philosophy-starter",
            version="0.1.0",
            catalog_keys=frozenset({"philosophy/The Republic", "philosophy/Meditations"}),
            diary_dirs=(),
        )
        assert path == bundle_dir / "product.json"
        doc = json.loads(path.read_text())
        assert doc["name"] == "philosophy-starter"
        assert doc["version"] == "0.1.0"
        assert doc["book_count"] == 2
        assert doc["catalog_keys"] == ["philosophy/Meditations", "philosophy/The Republic"]
        assert doc["diary_dirs"] == []
        assert set(doc["dockg_sha256"]) == {"graph.sqlite", "catalog.json"}
        assert len(doc["dockg_sha256"]["graph.sqlite"]) == 64
        assert doc["spec_sha256"] is None

    def test_spec_sha256_set_when_a_spec_file_is_given(self, tmp_path):
        bundle_dir = tmp_path / "b"
        (bundle_dir / ".dockg").mkdir(parents=True)
        spec_path = tmp_path / "spec.toml"
        spec_path.write_text('name = "d"\nversion = "0.1.0"\n', encoding="utf-8")

        path = write_product_json(
            bundle_dir,
            name="d",
            version="0.1.0",
            catalog_keys=frozenset(),
            diary_dirs=(),
            spec_path=spec_path,
        )
        doc = json.loads(path.read_text())
        assert len(doc["spec_sha256"]) == 64


# --- _diary_dirs_for_product ---------------------------------------------


class TestDiaryDirsForProduct:
    def test_explicit_value_passes_through_unchanged(self):
        assert _diary_dirs_for_product(("pepys",), n_diaries=1) == ("pepys",)

    def test_explicit_empty_tuple_passes_through(self):
        assert _diary_dirs_for_product((), n_diaries=0) == ()

    def test_none_with_no_diaries_bundled_is_empty(self):
        assert _diary_dirs_for_product(None, n_diaries=0) == ()

    def test_none_with_diaries_bundled_enumerates_the_real_corpus(self, corpus, monkeypatch):
        """The bug this guards: None used to write [] to product.json even
        though bundle_diaries had just copied every diary it found."""
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        result = _diary_dirs_for_product(None, n_diaries=2)
        assert set(result) == {"pepys", "evelyn"}


# --- run_build_corpus: the two paths that never touch doc_kg -----------------


class TestRunBuildCorpusEarlyExits:
    def test_force_overwrite_full_guard_blocks_gutenberg_all(self, corpus, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        monkeypatch.setattr(
            "gutenberg_kg.build_corpus.ALL_GENRES", ["philosophy", "english-literature"]
        )
        opts = BuildCorpusOptions(catalog_keys=frozenset({"philosophy/The Republic"}), quiet=True)
        rc = run_build_corpus(["philosophy", "english-literature"], opts)
        assert rc == 1

    def test_force_overwrite_full_flag_lets_it_through_to_dry_run(self, corpus, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        monkeypatch.setattr(
            "gutenberg_kg.build_corpus.ALL_GENRES", ["philosophy", "english-literature"]
        )
        opts = BuildCorpusOptions(
            catalog_keys=frozenset({"philosophy/The Republic"}),
            force_overwrite_full=True,
            dry_run=True,
            quiet=True,
        )
        rc = run_build_corpus(["philosophy", "english-literature"], opts)
        assert rc == 0

    def test_a_named_output_needs_no_force_flag(self, corpus, monkeypatch):
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        monkeypatch.setattr("gutenberg_kg.build_corpus.ALL_GENRES", ["philosophy"])
        opts = BuildCorpusOptions(
            output="philosophy-starter",
            catalog_keys=frozenset({"philosophy/The Republic"}),
            dry_run=True,
            quiet=True,
        )
        rc = run_build_corpus(["philosophy"], opts)
        assert rc == 0

    def test_dry_run_with_no_catalog_keys_is_unaffected(self, corpus, monkeypatch):
        """The plain, flag-free path: no behavior change from phase 3 at all."""
        monkeypatch.setattr("gutenberg_kg.build_corpus.CORPUS_ROOT", corpus)
        monkeypatch.setattr("gutenberg_kg.build_corpus.ALL_GENRES", ["philosophy"])
        opts = BuildCorpusOptions(dry_run=True, quiet=True)
        rc = run_build_corpus(["philosophy"], opts)
        assert rc == 0
