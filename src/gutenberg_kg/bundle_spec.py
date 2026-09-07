"""Bundle specs: select books or genres, name and version the result.

A bundle spec is a small TOML file naming a subset of the corpus (by genre,
by book, or both), a diary policy, and a materialization mode. Resolving one
turns those human-facing names into ``<genre>/<book>`` catalog keys that
``build-corpus`` and ``export-swift`` can filter against.

Stdlib only (``tomllib``, ``dataclasses``, ``pathlib``) plus the existing
``authors.parse_reference`` and ``export_swift._diary_slug`` helpers -- no
new runtime dependency; both are stdlib-only themselves; ``export_swift``
only reaches for numpy/sqlite-vec lazily, inside the functions that need
them, so importing it here does not pull those in at module load.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from gutenberg_kg.authors import parse_reference
from gutenberg_kg.export_swift import _diary_slug
from gutenberg_kg.gutenberg import CORPUS_ROOT

CORPUS_ROOT_PATH = Path(CORPUS_ROOT)
#: ``corpus/diaries/`` holds one book-shaped directory per diary, the same
#: ``reference.md``-per-subdirectory layout as every genre.
DIARIES_DIR_NAME = "diaries"


class BundleSpecError(Exception):
    """Raised for a malformed spec file or a selection that cannot resolve."""


@dataclass(frozen=True)
class BundleSpec:
    """A bundle's declared identity, selection, and product requirements.

    :param name: Bundle name; also the default image tag prefix.
    :param version: Bundle version, free-form (semver by convention).
    :param genres: Genre directory names to include in full.
    :param books: Raw book selectors -- a catalog key, a Gutenberg ebook_id
        as digits, or a bare book directory name. Resolved by
        ``resolve_selection``.
    :param diaries: ``False`` (none), ``True`` (all), or specific diary
        directory names.
    :param source_bundle: Bundle directory read when ``materialize == "none"``.
    :param materialize: ``"rebuild"`` (default) or ``"none"`` (packs only,
        read from ``source_bundle``).
    :param golden_queries: At least 3 queries the exported pack must answer
        correctly; enforced by ``bundle validate``.
    :param image_tag: Container tag suffix. Defaults to ``f"{name}-{version}"``.
    :param export_swift: Whether this bundle produces on-device Swift packs.
    :param description: Free-form, for human readers only.
    """

    name: str
    version: str
    genres: tuple[str, ...] = field(default_factory=tuple)
    books: tuple[str, ...] = field(default_factory=tuple)
    diaries: bool | tuple[str, ...] = False
    source_bundle: Path | None = None
    materialize: str = "rebuild"
    golden_queries: tuple[str, ...] = field(default_factory=tuple)
    image_tag: str = ""
    export_swift: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if not self.image_tag:
            object.__setattr__(self, "image_tag", f"{self.name}-{self.version}")


@dataclass(frozen=True)
class ResolvedSelection:
    """The result of resolving a spec's ``genres``/``books`` against the corpus.

    :param catalog_keys: Every selected book, as ``"<genre>/<book>"``.
    :param genres_implied: The genres actually touched by ``catalog_keys``.
    :param diary_dirs: Diary slugs to bundle -- every diary when the spec set
        ``diaries = true``, the named ones for an explicit list, empty for
        ``false``. Always a concrete list by the time resolution finishes;
        nothing downstream needs to re-interpret the spec's tri-state.
    :param missing: Raw ``books:`` entries that did not resolve to exactly
        one book. Non-empty means resolution failed.
    """

    catalog_keys: frozenset[str]
    genres_implied: frozenset[str]
    diary_dirs: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """True when every entry resolved and there is something to bundle."""
        return not self.missing and bool(self.catalog_keys)


def load_spec(path: Path) -> BundleSpec:
    """Parse a bundle spec TOML file.

    :param path: Path to the spec file.
    :returns: The parsed, unvalidated spec.
    :raises BundleSpecError: If the file cannot be read or parsed, or a
        required field is missing or the wrong type.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise BundleSpecError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise BundleSpecError(f"{path} is not valid TOML: {exc}") from exc

    for required in ("name", "version"):
        if required not in raw:
            raise BundleSpecError(f"{path}: missing required field {required!r}")

    diaries_raw = raw.get("diaries", False)
    if isinstance(diaries_raw, list):
        diaries: bool | tuple[str, ...] = tuple(diaries_raw)
    elif isinstance(diaries_raw, bool):
        diaries = diaries_raw
    else:
        raise BundleSpecError(
            f"{path}: 'diaries' must be a boolean or a list of directory names, got {diaries_raw!r}"
        )

    source_bundle_raw = raw.get("source_bundle")
    source_bundle = Path(source_bundle_raw) if source_bundle_raw else None

    try:
        return BundleSpec(
            name=raw["name"],
            version=raw["version"],
            genres=tuple(raw.get("genres", [])),
            books=tuple(raw.get("books", [])),
            diaries=diaries,
            source_bundle=source_bundle,
            materialize=raw.get("materialize", "rebuild"),
            golden_queries=tuple(raw.get("golden_queries", [])),
            image_tag=raw.get("image_tag", ""),
            export_swift=raw.get("export_swift", True),
            description=raw.get("description", ""),
        )
    except TypeError as exc:
        raise BundleSpecError(f"{path}: {exc}") from exc


def _catalog_key_for_directory(genre_dir: Path, book_dir: Path) -> str:
    return f"{genre_dir.name}/{book_dir.name}"


def _is_safe_path_component(name: str) -> bool:
    """Reject anything that could step outside ``corpus_root`` once joined.

    A spec's ``genres:``/``books:`` entries become path segments in a
    ``corpus_root / segment`` join. Without this, a selector like
    ``"../../etc"`` (or a leading ``/``, which ``Path.__truediv__`` treats
    as an absolute-path reset, discarding everything joined before it) would
    resolve outside the corpus.

    Checked on every ``/``-separated part of ``name``, not just the whole
    string: after ``_resolve_book`` rule 1 splits ``"genre/book"`` on its
    first ``/``, a selector like ``"philosophy/../../../etc"`` leaves
    ``"../../../etc"`` as the book half, whose *first* segment is ``".."``
    but which is not equal to ``".."`` as a whole string -- a check against
    the whole string alone misses exactly this case.
    """
    if not name or name.startswith("/") or "\\" in name:
        return False
    return all(part not in ("", ".", "..") for part in name.split("/"))


def _resolve_book(selector: str, corpus_root: Path) -> str | list[str]:
    """Resolve one raw ``books:`` entry to a single catalog key.

    :param selector: A catalog key (``genre/book``), an all-digit
        Gutenberg ebook_id, or a bare book directory name.
    :param corpus_root: The corpus root to resolve against.
    :returns: The resolved ``"genre/book"`` key, or a list of every genre
        the bare name matched (empty if none) when it is ambiguous, absent,
        or unsafe -- the caller treats anything but a single string as
        unresolved.
    """
    # Rule 1: an explicit "genre/book" catalog key.
    if "/" in selector:
        genre_name, _, book_name = selector.partition("/")
        if not (_is_safe_path_component(genre_name) and _is_safe_path_component(book_name)):
            return []
        candidate = corpus_root / genre_name / book_name / "reference.md"
        if candidate.is_file():
            return f"{genre_name}/{book_name}"
        return []

    # Rule 2: an all-digit Gutenberg ebook_id, searched across every genre.
    if selector.isdigit():
        ebook_id = int(selector)
        matches = []
        for ref in sorted(corpus_root.glob("*/*/reference.md")):
            try:
                meta = parse_reference(ref)
            except OSError:
                continue
            if meta.get("ebook_id") == ebook_id:
                matches.append(_catalog_key_for_directory(ref.parent.parent, ref.parent))
        if len(matches) == 1:
            return matches[0]
        return matches

    # Rule 3: a bare book directory name, unique across all genres.
    if not _is_safe_path_component(selector):
        return []
    matches = []
    for genre_dir in sorted(corpus_root.iterdir()):
        if not genre_dir.is_dir():
            continue
        candidate = genre_dir / selector
        if (candidate / "reference.md").is_file():
            matches.append(_catalog_key_for_directory(genre_dir, candidate))
    if len(matches) == 1:
        return matches[0]
    return matches


def _all_diary_slugs(corpus_root: Path) -> tuple[str, ...]:
    """Every diary in the corpus, as the slugs ``export_swift`` names them by.

    ``diaries = true`` means "all of them", which only means something once
    "them" is enumerated -- ``corpus/diaries/`` is a book-shaped directory
    like any genre's, one ``reference.md``-bearing subdirectory per diary.

    :param corpus_root: The corpus root to scan.
    :returns: Sorted diary slugs; empty if there is no ``diaries/`` directory.
    """
    diaries_dir = corpus_root / DIARIES_DIR_NAME
    if not diaries_dir.is_dir():
        return ()
    return tuple(
        sorted(
            _diary_slug(entry.name)
            for entry in diaries_dir.iterdir()
            if entry.is_dir() and (entry / "reference.md").is_file()
        )
    )


def resolve_selection(spec: BundleSpec, corpus_root: Path = CORPUS_ROOT_PATH) -> ResolvedSelection:
    """Resolve a spec's ``genres``/``books``/``diaries`` against the corpus.

    Ambiguous or unresolved ``books:`` entries are collected in ``missing``
    rather than raised immediately, so a caller (``bundle validate``) can
    report every problem in one pass instead of one at a time.

    :param spec: The spec to resolve.
    :param corpus_root: The corpus root to resolve against. Overridable for
        tests; defaults to the real corpus.
    :returns: The resolved selection. Check ``.ok`` or inspect ``.missing``
        before using ``.catalog_keys``.
    """
    catalog_keys: set[str] = set()
    missing: list[str] = []

    for genre in spec.genres:
        if not _is_safe_path_component(genre):
            missing.append(genre)
            continue
        genre_dir = corpus_root / genre
        if not genre_dir.is_dir():
            missing.append(genre)
            continue
        for book_dir in sorted(genre_dir.iterdir()):
            if book_dir.is_dir() and (book_dir / "reference.md").is_file():
                catalog_keys.add(_catalog_key_for_directory(genre_dir, book_dir))

    for selector in spec.books:
        result = _resolve_book(selector, corpus_root)
        if isinstance(result, str):
            catalog_keys.add(result)
        else:
            missing.append(selector)

    genres_implied = frozenset(key.split("/", 1)[0] for key in catalog_keys)
    if isinstance(spec.diaries, tuple):
        diary_dirs = spec.diaries
    elif spec.diaries:
        diary_dirs = _all_diary_slugs(corpus_root)
    else:
        diary_dirs = ()

    return ResolvedSelection(
        catalog_keys=frozenset(catalog_keys),
        genres_implied=genres_implied,
        diary_dirs=diary_dirs,
        missing=tuple(missing),
    )


def validate_spec(spec: BundleSpec, resolved: ResolvedSelection) -> list[str]:
    """Check a spec and its resolution against every rule ``bundle validate`` enforces.

    Pure and side-effect-free: takes an already-resolved selection rather
    than resolving one itself, so tests can exercise validation against a
    hand-built ``ResolvedSelection`` without touching the corpus.

    :param spec: The spec being validated.
    :param resolved: The result of ``resolve_selection(spec)``.
    :returns: Human-readable problems, empty when the spec is valid.
    """
    problems: list[str] = []

    if spec.materialize not in ("rebuild", "none"):
        problems.append(f"materialize must be 'rebuild' or 'none', got {spec.materialize!r}")
    if spec.materialize == "none" and not spec.export_swift:
        problems.append("materialize = 'none' with export_swift = false produces nothing")
    if spec.materialize == "none" and spec.source_bundle is None:
        problems.append("materialize = 'none' requires source_bundle")

    if len(spec.golden_queries) < 3:
        problems.append(f"golden_queries needs at least 3 entries, got {len(spec.golden_queries)}")

    if ":" in spec.image_tag or "/" in spec.image_tag:
        problems.append(f"image_tag must not contain ':' or '/', got {spec.image_tag!r}")

    if resolved.missing:
        problems.append(
            f"could not resolve {len(resolved.missing)} selector(s): {list(resolved.missing)}"
        )
    if not resolved.catalog_keys:
        problems.append("selection is empty -- nothing to bundle")

    return problems
