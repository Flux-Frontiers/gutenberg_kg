"""Unit tests for gutenberg_kg.bundle_spec -- selective bundle specs.

Every test builds its own tiny corpus tree under ``tmp_path`` rather than
touching the real corpus, so these stay hermetic and fast, and a resolver
bug shows up as a specific, minimal failing case instead of a diff against
whatever the real corpus happens to contain this week.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gutenberg_kg.bundle_spec import (
    BundleSpec,
    BundleSpecError,
    ResolvedSelection,
    load_spec,
    resolve_selection,
    validate_spec,
)


def _make_book(corpus_root: Path, genre: str, title: str, *, ebook_id: int | None = None) -> Path:
    """Create a minimal ``<genre>/<title>/reference.md`` under ``corpus_root``."""
    book_dir = corpus_root / genre / title
    book_dir.mkdir(parents=True)
    lines = [f"# Reference: {title}", "", "## Source", ""]
    if ebook_id is not None:
        lines.append(f"- **Project Gutenberg ID**: {ebook_id}")
    (book_dir / "reference.md").write_text("\n".join(lines), encoding="utf-8")
    return book_dir


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A small corpus: two genres, three books, one with a Gutenberg ID."""
    root = tmp_path / "corpus"
    _make_book(root, "philosophy", "The Republic", ebook_id=1497)
    _make_book(root, "philosophy", "Meditations", ebook_id=2680)
    _make_book(root, "english-literature", "Pride and Prejudice", ebook_id=1342)
    return root


# --- load_spec ---------------------------------------------------------


def test_load_spec_reads_required_fields(tmp_path: Path):
    path = tmp_path / "spec.toml"
    path.write_text('name = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    spec = load_spec(path)
    assert spec.name == "demo"
    assert spec.version == "0.1.0"


def test_load_spec_missing_name_is_an_error(tmp_path: Path):
    path = tmp_path / "spec.toml"
    path.write_text('version = "0.1.0"\n', encoding="utf-8")
    with pytest.raises(BundleSpecError, match="name"):
        load_spec(path)


def test_load_spec_invalid_toml_is_an_error(tmp_path: Path):
    path = tmp_path / "spec.toml"
    path.write_text("this is not [ toml", encoding="utf-8")
    with pytest.raises(BundleSpecError):
        load_spec(path)


def test_load_spec_missing_file_is_an_error(tmp_path: Path):
    with pytest.raises(BundleSpecError):
        load_spec(tmp_path / "nope.toml")


def test_load_spec_full_example(tmp_path: Path):
    path = tmp_path / "spec.toml"
    path.write_text(
        """
        name = "philosophy-starter"
        version = "0.1.0"
        description = "Plato, Aristotle, and Kant"
        genres = ["philosophy"]
        books = ["2680"]
        diaries = false
        materialize = "rebuild"
        export_swift = true
        golden_queries = ["a", "b", "c"]
        image_tag = "philosophy-starter-0.1.0"
        """,
        encoding="utf-8",
    )
    spec = load_spec(path)
    assert spec.genres == ("philosophy",)
    assert spec.books == ("2680",)
    assert spec.diaries is False
    assert spec.golden_queries == ("a", "b", "c")
    assert spec.image_tag == "philosophy-starter-0.1.0"


def test_load_spec_diaries_as_list_becomes_tuple(tmp_path: Path):
    path = tmp_path / "spec.toml"
    path.write_text(
        'name = "d"\nversion = "0.1.0"\ndiaries = ["pepys", "evelyn"]\n',
        encoding="utf-8",
    )
    spec = load_spec(path)
    assert spec.diaries == ("pepys", "evelyn")


def test_load_spec_diaries_wrong_type_is_an_error(tmp_path: Path):
    path = tmp_path / "spec.toml"
    path.write_text('name = "d"\nversion = "0.1.0"\ndiaries = "yes"\n', encoding="utf-8")
    with pytest.raises(BundleSpecError, match="diaries"):
        load_spec(path)


# --- BundleSpec.image_tag default ---------------------------------------


def test_image_tag_defaults_to_name_and_version():
    spec = BundleSpec(name="demo", version="0.2.0")
    assert spec.image_tag == "demo-0.2.0"


def test_image_tag_explicit_value_is_kept():
    spec = BundleSpec(name="demo", version="0.2.0", image_tag="custom")
    assert spec.image_tag == "custom"


# --- resolve_selection: genres -------------------------------------------


def test_resolve_genre_selects_every_book_in_it(corpus: Path):
    spec = BundleSpec(name="d", version="0.1.0", genres=("philosophy",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.catalog_keys == {"philosophy/The Republic", "philosophy/Meditations"}
    assert resolved.genres_implied == {"philosophy"}
    assert resolved.missing == ()


def test_resolve_unknown_genre_is_missing(corpus: Path):
    spec = BundleSpec(name="d", version="0.1.0", genres=("nonexistent-genre",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.catalog_keys == frozenset()
    assert resolved.missing == ("nonexistent-genre",)


# --- resolve_selection: books, rule 1 (explicit genre/book) --------------


def test_resolve_explicit_catalog_key(corpus: Path):
    spec = BundleSpec(name="d", version="0.1.0", books=("philosophy/The Republic",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.catalog_keys == {"philosophy/The Republic"}
    assert resolved.missing == ()


def test_resolve_explicit_catalog_key_wrong_genre_is_missing(corpus: Path):
    spec = BundleSpec(name="d", version="0.1.0", books=("english-literature/The Republic",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.missing == ("english-literature/The Republic",)


# --- resolve_selection: books, rule 2 (ebook_id) -------------------------


def test_resolve_by_ebook_id(corpus: Path):
    spec = BundleSpec(name="d", version="0.1.0", books=("2680",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.catalog_keys == {"philosophy/Meditations"}


def test_resolve_by_unknown_ebook_id_is_missing(corpus: Path):
    spec = BundleSpec(name="d", version="0.1.0", books=("999999",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.missing == ("999999",)


# --- resolve_selection: books, rule 3 (bare directory name) --------------


def test_resolve_bare_name_unique_across_genres(corpus: Path):
    spec = BundleSpec(name="d", version="0.1.0", books=("Pride and Prejudice",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.catalog_keys == {"english-literature/Pride and Prejudice"}


def test_resolve_bare_name_ambiguous_across_genres_is_missing(tmp_path: Path):
    root = tmp_path / "corpus"
    _make_book(root, "philosophy", "Republic")
    _make_book(root, "english-literature", "Republic")
    spec = BundleSpec(name="d", version="0.1.0", books=("Republic",))
    resolved = resolve_selection(spec, corpus_root=root)
    assert resolved.missing == ("Republic",)
    assert resolved.catalog_keys == frozenset()


def test_resolve_bare_name_not_found_is_missing(corpus: Path):
    spec = BundleSpec(name="d", version="0.1.0", books=("Nonexistent Title",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.missing == ("Nonexistent Title",)


# --- resolve_selection: no fuzzy matching --------------------------------


def test_resolve_no_fuzzy_matching_on_partial_title(corpus: Path):
    """A partial or misspelled title must not silently match -- v1 has no
    fuzzy search precisely so a typo in a product spec fails loudly instead
    of picking the wrong book."""
    spec = BundleSpec(name="d", version="0.1.0", books=("The Republi",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.missing == ("The Republi",)


# --- resolve_selection: path safety --------------------------------------


@pytest.mark.parametrize(
    "selector",
    [
        "../etc/passwd",
        "philosophy/../../../etc",
        "/etc/passwd",
        "..",
    ],
)
def test_resolve_rejects_path_traversal_in_books(corpus: Path, selector: str):
    spec = BundleSpec(name="d", version="0.1.0", books=(selector,))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.missing == (selector,)
    assert resolved.catalog_keys == frozenset()


def test_resolve_rejects_path_traversal_in_genres(corpus: Path):
    spec = BundleSpec(name="d", version="0.1.0", genres=("../",))
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.missing == ("../",)


# --- resolve_selection: union and dedup ----------------------------------


def test_resolve_unions_genres_and_books_without_duplicates(corpus: Path):
    spec = BundleSpec(
        name="d",
        version="0.1.0",
        genres=("philosophy",),
        books=("philosophy/The Republic", "english-literature/Pride and Prejudice"),
    )
    resolved = resolve_selection(spec, corpus_root=corpus)
    assert resolved.catalog_keys == {
        "philosophy/The Republic",
        "philosophy/Meditations",
        "english-literature/Pride and Prejudice",
    }
    assert resolved.genres_implied == {"philosophy", "english-literature"}


def test_resolve_diary_dirs_pass_through_from_spec_list():
    spec = BundleSpec(name="d", version="0.1.0", diaries=("pepys", "evelyn"))
    resolved = resolve_selection(spec, corpus_root=Path("/nonexistent"))
    assert resolved.diary_dirs == ("pepys", "evelyn")


def test_resolve_diary_dirs_empty_when_diaries_is_false():
    spec = BundleSpec(name="d", version="0.1.0", diaries=False)
    resolved = resolve_selection(spec, corpus_root=Path("/nonexistent"))
    assert resolved.diary_dirs == ()


def test_resolve_diary_dirs_true_with_no_diaries_directory_is_empty():
    """``diaries = true`` means "all of them" -- with none present, that is none."""
    spec = BundleSpec(name="d", version="0.1.0", diaries=True)
    resolved = resolve_selection(spec, corpus_root=Path("/nonexistent"))
    assert resolved.diary_dirs == ()


def test_resolve_diary_dirs_true_enumerates_every_diary(tmp_path: Path):
    root = tmp_path / "corpus"
    _make_book(root, "diaries", "The Diary of Samuel Pepys")
    _make_book(root, "diaries", "The Diary of John Evelyn")
    _make_book(root, "philosophy", "The Republic")  # not a diary; must not appear
    spec = BundleSpec(name="d", version="0.1.0", diaries=True)
    resolved = resolve_selection(spec, corpus_root=root)
    assert set(resolved.diary_dirs) == {"pepys", "evelyn"}


def test_resolve_diary_dirs_true_and_false_are_distinguishable(tmp_path: Path):
    """The bug this guards: both used to resolve to the same empty tuple."""
    root = tmp_path / "corpus"
    _make_book(root, "diaries", "The Diary of Samuel Pepys")
    true_spec = BundleSpec(name="d", version="0.1.0", diaries=True)
    false_spec = BundleSpec(name="d", version="0.1.0", diaries=False)
    assert resolve_selection(true_spec, corpus_root=root).diary_dirs != ()
    assert resolve_selection(false_spec, corpus_root=root).diary_dirs == ()


# --- ResolvedSelection.ok -------------------------------------------------


def test_resolved_selection_ok_true_when_complete():
    resolved = ResolvedSelection(
        catalog_keys=frozenset({"a/b"}),
        genres_implied=frozenset({"a"}),
        diary_dirs=(),
        missing=(),
    )
    assert resolved.ok


def test_resolved_selection_ok_false_when_missing():
    resolved = ResolvedSelection(
        catalog_keys=frozenset(),
        genres_implied=frozenset(),
        diary_dirs=(),
        missing=("x",),
    )
    assert not resolved.ok


def test_resolved_selection_ok_false_when_empty():
    resolved = ResolvedSelection(
        catalog_keys=frozenset(),
        genres_implied=frozenset(),
        diary_dirs=(),
        missing=(),
    )
    assert not resolved.ok


# --- validate_spec ---------------------------------------------------------


def _resolved_ok() -> ResolvedSelection:
    return ResolvedSelection(
        catalog_keys=frozenset({"philosophy/The Republic"}),
        genres_implied=frozenset({"philosophy"}),
        diary_dirs=(),
        missing=(),
    )


def test_validate_accepts_a_well_formed_spec():
    spec = BundleSpec(
        name="d", version="0.1.0", golden_queries=("a", "b", "c"), materialize="rebuild"
    )
    assert validate_spec(spec, _resolved_ok()) == []


def test_validate_rejects_bad_materialize():
    spec = BundleSpec(
        name="d", version="0.1.0", golden_queries=("a", "b", "c"), materialize="slice"
    )
    problems = validate_spec(spec, _resolved_ok())
    assert any("materialize" in p for p in problems)


def test_validate_requires_at_least_three_golden_queries():
    spec = BundleSpec(name="d", version="0.1.0", golden_queries=("a", "b"))
    problems = validate_spec(spec, _resolved_ok())
    assert any("golden_queries" in p for p in problems)


def test_validate_rejects_colon_in_image_tag():
    spec = BundleSpec(
        name="d",
        version="0.1.0",
        golden_queries=("a", "b", "c"),
        image_tag="repo:tag",
    )
    problems = validate_spec(spec, _resolved_ok())
    assert any("image_tag" in p for p in problems)


def test_validate_rejects_slash_in_image_tag():
    spec = BundleSpec(
        name="d",
        version="0.1.0",
        golden_queries=("a", "b", "c"),
        image_tag="repo/tag",
    )
    problems = validate_spec(spec, _resolved_ok())
    assert any("image_tag" in p for p in problems)


def test_validate_reports_missing_selectors():
    spec = BundleSpec(name="d", version="0.1.0", golden_queries=("a", "b", "c"))
    resolved = ResolvedSelection(
        catalog_keys=frozenset(),
        genres_implied=frozenset(),
        diary_dirs=(),
        missing=("nope",),
    )
    problems = validate_spec(spec, resolved)
    assert any("nope" in p for p in problems)


def test_validate_rejects_empty_selection():
    spec = BundleSpec(name="d", version="0.1.0", golden_queries=("a", "b", "c"))
    resolved = ResolvedSelection(
        catalog_keys=frozenset(),
        genres_implied=frozenset(),
        diary_dirs=(),
        missing=(),
    )
    problems = validate_spec(spec, resolved)
    assert any("empty" in p for p in problems)


def test_validate_materialize_none_requires_export_swift():
    spec = BundleSpec(
        name="d",
        version="0.1.0",
        golden_queries=("a", "b", "c"),
        materialize="none",
        export_swift=False,
        source_bundle=Path("bundles/gutenberg-all"),
    )
    problems = validate_spec(spec, _resolved_ok())
    assert any("export_swift" in p for p in problems)


def test_validate_materialize_none_requires_source_bundle():
    spec = BundleSpec(
        name="d",
        version="0.1.0",
        golden_queries=("a", "b", "c"),
        materialize="none",
        export_swift=True,
        source_bundle=None,
    )
    problems = validate_spec(spec, _resolved_ok())
    assert any("source_bundle" in p for p in problems)


def test_validate_materialize_none_with_source_bundle_and_export_is_fine():
    spec = BundleSpec(
        name="d",
        version="0.1.0",
        golden_queries=("a", "b", "c"),
        materialize="none",
        export_swift=True,
        source_bundle=Path("bundles/gutenberg-all"),
    )
    assert validate_spec(spec, _resolved_ok()) == []
