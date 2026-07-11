"""build-corpus subcommand — build a single consolidated DocKG over the corpus."""

import click

from gutenberg_kg import build_corpus as bc
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
    help="Embedding batch size passed to sentence-transformers encode().",
)
@click.option(
    "--embed-device",
    type=click.Choice(["auto", "cpu", "mps"]),
    default="auto",
    show_default=True,
    help="Embedding device override (auto prefers MPS when available, else CPU).",
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
):
    """Build one consolidated DocKG over the whole corpus (or chosen genres).

    Writes a single graph.sqlite + lancedb index to ``bundles/<name>/.dockg/`` —
    the artifact baked into the standalone fat image.  Unlike ``ingest`` (one
    DocKG per book, federated), this is a single index spanning every book, with
    genre recoverable from each node's file_path prefix.

    Genres are processed in strategy groups: sacred-texts uses the verse chunker
    by default; all others use semantic.  Override with ``--strategy genre:strategy``.
    DiaryKG indices are copied verbatim from corpus/diaries/ into the bundle.

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
    """
    genres = list(genre) if genre else list(ALL_GENRES)
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
    )
    rc = bc.run_build_corpus(genres, opts)
    if rc != 0:
        raise SystemExit(rc)
