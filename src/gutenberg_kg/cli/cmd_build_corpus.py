"""build-corpus subcommand — build a single consolidated DocKG over the corpus."""

from pathlib import Path

import click

from gutenberg_kg import build_corpus as bc
from gutenberg_kg.bundle_spec import (
    BundleSpec,
    BundleSpecError,
    load_spec,
    resolve_selection,
    validate_spec,
)
from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES

_VALID_STRATEGIES = ("semantic", "sentence_group", "fixed", "verse")


def _parse_strategy(ctx, param, value):  # noqa: ARG001
    """Parse ``genre:strategy`` pairs into a dict."""
    result: dict[str, str] = {}
    for item in value:
        if ":" not in item:
            raise click.BadParameter(
                f"Expected genre:strategy, got {item!r}. "
                f"Valid strategies: {', '.join(_VALID_STRATEGIES)}",
                param=param,
            )
        genre, strategy = item.split(":", 1)
        if genre not in ALL_GENRES:
            raise click.BadParameter(
                f"Unknown genre {genre!r}. Valid genres: {', '.join(sorted(ALL_GENRES))}",
                param=param,
            )
        if strategy not in _VALID_STRATEGIES:
            raise click.BadParameter(
                f"Unknown strategy {strategy!r} for genre {genre!r}. "
                f"Valid: {', '.join(_VALID_STRATEGIES)}",
                param=param,
            )
        result[genre] = strategy
    return result


@cli.command("build-corpus")
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    multiple=True,
    help="Genre to include (repeatable; default: all genres).",
)
@click.option(
    "--output",
    default=None,
    metavar="NAME",
    help="Bundle name under bundles/ (default: gutenberg-all or gutenberg-<genre>).",
)
@click.option(
    "--similar-k",
    type=int,
    default=bc.DEFAULT_SIMILAR_K,
    show_default=True,
    help="Max SIMILAR_TO out-edges per chunk (0 = no cap).",
)
@click.option(
    "--similar/--no-similar",
    "discover_similar",
    default=False,
    show_default=True,
    help="Discover cross-book SIMILAR_TO edges. Default off: the served handler is "
    "semantic-first and never traverses them, so they only bloat the shipped "
    "graph.sqlite. Enable for viz3d arcs or DocKG.query() hop-expansion use.",
)
@click.option(
    "--workers",
    type=int,
    default=4,
    show_default=True,
    help="Embedding worker processes for the CPU path (each loads its own model copy, "
    "~1.2 GB). Ignored on MPS/CUDA, which stream single-process.",
)
@click.option(
    "--embed-batch-size",
    type=int,
    default=64,
    show_default=True,
    help="Embedding batch size passed to sentence-transformers encode(). Unbounded on "
    "the MPS/CUDA streaming path (no internal cap) -- raising this for throughput "
    "on the full corpus risks an attention-memory OOM (batch x seq^2). Safe to raise "
    "on --embed-device cpu, where each worker's own batch is small either way.",
)
@click.option(
    "--embed-device",
    type=click.Choice(["auto", "cpu", "mps", "cuda"]),
    default="auto",
    show_default=True,
    help="Embedding device override (auto prefers MPS, then CUDA, else CPU).",
)
@click.option(
    "--strategy",
    multiple=True,
    metavar="GENRE:STRATEGY",
    callback=_parse_strategy,
    is_eager=False,
    help=(
        "Override chunk strategy for a genre (repeatable). "
        "Format: genre:strategy — e.g. --strategy sacred-texts:verse. "
        f"Valid strategies: {', '.join(_VALID_STRATEGIES)}."
    ),
)
@click.option(
    "--diaries-only",
    is_flag=True,
    default=False,
    help="Skip phases 1-3; re-bundle diary indices into an existing bundle only.",
)
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Incremental rebuild: re-parse the corpus, embed ONLY new/changed nodes, upsert "
    "into the existing vector index, and prune removed ones (skips SIMILAR_TO). Reuses "
    "existing embeddings, so a small corpus change costs minutes instead of a full rebuild.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the build plan without executing.",
)
@click.option(
    "--quiet",
    is_flag=True,
    default=False,
    help="Suppress per-stage DocKG progress output.",
)
@click.option(
    "--book",
    "books",
    multiple=True,
    metavar="SELECTOR",
    help="Restrict to this book within the selected genres: a catalog key, a "
    "Gutenberg ebook_id, or a bare book name unique across genres. Repeatable. "
    "Needs an explicit --output. Not with --spec.",
)
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="A bundle spec TOML (see `gutenkg bundle`). Supplies the selection, "
    "diary policy, output name, and product name/version in one go. Not "
    "with --book or --genre.",
)
@click.option(
    "--diaries/--no-diaries",
    "diaries_flag",
    default=None,
    help="Override diary bundling for this run. Distinct from --diaries-only, "
    "which skips phases 1-3 and only re-bundles diary indices; this affects "
    "phase 4 of an ordinary build. Ignored when --spec supplies its own "
    "diary policy.",
)
@click.option(
    "--force-overwrite-full",
    is_flag=True,
    default=False,
    help="Allow a book-filtered build (--book or --spec) to target the name "
    "'gutenberg-all', overwriting the full corpus bundle.",
)
def build_corpus(
    genre,
    output,
    similar_k,
    discover_similar,
    workers,
    embed_batch_size,
    embed_device,
    strategy,
    diaries_only,
    update,
    dry_run,
    quiet,
    books,
    spec_path,
    diaries_flag,
    force_overwrite_full,
):
    """Build one consolidated DocKG over the whole corpus (or chosen genres).

    Writes a single graph.sqlite + lancedb index to ``bundles/<name>/.dockg/`` —
    the artifact baked into the standalone fat image.  Unlike ``ingest`` (one
    DocKG per book, federated), this is a single index spanning every book, with
    genre recoverable from each node's file_path prefix.

    Genres are processed in strategy groups: sacred-texts uses the verse chunker
    by default; all others use semantic.  Override with ``--strategy genre:strategy``.
    DiaryKG indices are copied verbatim from corpus/diaries/ into the bundle.

    \b
    Examples:
      gutenkg build-corpus
      gutenkg build-corpus --genre philosophy
      gutenkg build-corpus --book "philosophy/The Republic" --output philosophy-starter
      gutenkg build-corpus --spec bundles/specs/philosophy-starter.toml
    \f

    :param genre: Tuple of genres to include (empty = all genres).
    :param output: Override the bundle directory name.
    :param similar_k: Cap on SIMILAR_TO out-edges per chunk (when discovery is enabled).
    :param discover_similar: Discover SIMILAR_TO edges (default off for the served bundle).
    :param workers: Embedding worker processes.
    :param embed_batch_size: Embedding encode() batch size.
    :param embed_device: Embedding device override (auto/cpu/mps).
    :param strategy: Dict of genre→strategy overrides (parsed from CLI).
    :param diaries_only: Skip phases 1-3 and only re-bundle diary indices.
    :param update: Incremental rebuild — embed only new/changed nodes, upsert, prune.
    :param dry_run: Print the plan without building.
    :param quiet: Suppress per-stage progress output.
    :param books: Raw ``--book`` selectors, resolved against ``corpus/``.
    :param spec_path: A bundle spec TOML, in place of ``--book``/``--genre``.
    :param diaries_flag: ``True``/``False`` from ``--diaries``/``--no-diaries``,
        or ``None`` when neither was passed.
    :param force_overwrite_full: Allow a book-filtered build to target
        ``gutenberg-all``.
    :raises click.ClickException: If ``--spec`` is combined with ``--book``/
        ``--genre``, a selector or spec does not resolve, or ``--book`` is
        used without ``--output``.
    """
    if spec_path is not None and (books or genre):
        raise click.ClickException("--spec cannot be combined with --book or --genre.")
    if books and output is None:
        raise click.ClickException(
            "--book needs an explicit --output — an auto-derived name (from the "
            "genres your books happen to sit in) would misrepresent a partial "
            "selection as a complete one."
        )

    catalog_keys: frozenset[str] | None = None
    diary_dirs: tuple[str, ...] | None = None
    product_name: str | None = None
    product_version: str | None = None

    if spec_path is not None:
        try:
            spec = load_spec(spec_path)
        except BundleSpecError as exc:
            raise click.ClickException(str(exc)) from exc
        resolved = resolve_selection(spec)
        problems = validate_spec(spec, resolved)
        if problems:
            lines = "\n".join(f"  - {p}" for p in problems)
            raise click.ClickException(f"{spec_path} is not valid:\n{lines}")
        genres = sorted(resolved.genres_implied)
        catalog_keys = resolved.catalog_keys
        diary_dirs = resolved.diary_dirs
        product_name = spec.name
        product_version = spec.version
        if output is None:
            output = spec.name
    elif books:
        stub = BundleSpec(name="cli", version="0", genres=tuple(genre), books=tuple(books))
        resolved = resolve_selection(stub)
        if resolved.missing:
            raise click.ClickException(f"could not resolve: {list(resolved.missing)}")
        genres = sorted(resolved.genres_implied)
        catalog_keys = resolved.catalog_keys
        diary_dirs = None if diaries_flag is None else (None if diaries_flag else ())
    else:
        genres = list(genre) if genre else list(ALL_GENRES)
        diary_dirs = None if diaries_flag is None else (None if diaries_flag else ())

    opts = bc.BuildCorpusOptions(
        output=output,
        similar_k=similar_k,
        discover_similar=discover_similar,
        n_workers=workers,
        embed_batch_size=embed_batch_size,
        embed_device=embed_device,
        strategy_overrides=strategy,
        diaries_only=diaries_only,
        update=update,
        dry_run=dry_run,
        quiet=quiet,
        catalog_keys=catalog_keys,
        diary_dirs=diary_dirs,
        product_name=product_name,
        product_version=product_version,
        spec_path=spec_path,
        force_overwrite_full=force_overwrite_full,
    )
    rc = bc.run_build_corpus(genres, opts)
    if rc != 0:
        raise SystemExit(rc)
