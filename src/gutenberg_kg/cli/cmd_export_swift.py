# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""gutenkg export-swift — build the native app's on-device corpus packs."""

from __future__ import annotations

from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.export_swift import (
    DEFAULT_BUNDLE,
    ExportError,
    ExportOptions,
    export_swift,
)


def _human(size: int) -> str:
    """Format a byte count for a build log.

    :param size: Byte count.
    :returns: A short human-readable size, e.g. ``"1.34 GB"``.
    """
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:,.2f} GB"


@cli.command("export-swift")
@click.option(
    "--bundle",
    type=click.Path(path_type=Path),
    default=DEFAULT_BUNDLE,
    show_default=True,
    help="Bundle to export (the output of `make build-corpus`).",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory.  [default: <bundle>/swift]",
)
@click.option(
    "--dtype",
    type=click.Choice(["int8", "float"]),
    default="int8",
    show_default=True,
    help="Vector precision.  int8 is ~3x smaller; float is exact.",
)
@click.option(
    "--max-passage-chars",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help="Truncate passages at a word boundary; 0 keeps them whole.",
)
@click.option("--no-diaries", is_flag=True, help="Export the books only.")
@click.option(
    "--no-vectors",
    is_flag=True,
    help="Skip the vector stage — lexical search only.  Fast, for schema work.",
)
@click.option("--no-golden", is_flag=True, help="Skip golden.json (skips loading the embedder).")
@click.option(
    "--golden-k",
    type=click.IntRange(min=1),
    default=10,
    show_default=True,
    help="Depth recorded per golden query.",
)
@click.option(
    "--verify",
    is_flag=True,
    help="Measure the packs' recall against exact fp32 ground truth.",
)
@click.option("--force", is_flag=True, help="Overwrite a non-empty output directory.")
def export_swift_cmd(
    bundle: Path,
    out: Path | None,
    dtype: str,
    max_passage_chars: int,
    no_diaries: bool,
    no_vectors: bool,
    no_golden: bool,
    golden_k: int,
    verify: bool,
    force: bool,
) -> None:
    """Build the corpus packs the native app searches on device.

    Turns a bundle into ``core.pack`` / ``gutenberg.pack`` / ``diaries.pack``
    plus a ``manifest.json`` and a ``golden.json`` parity file.  Only the nodes
    the query path actually reads are carried over — chunks and sections, their
    clean text, and their vectors re-encoded to int8 — so a 5.7 GB bundle
    becomes something a phone can hold.

    \b
    Examples:
      gutenkg export-swift
      gutenkg export-swift --dtype float --out /tmp/packs
      gutenkg export-swift --verify            # report int8 recall while building
      gutenkg export-swift --no-vectors --no-golden   # quick schema-only pass
    \f

    :param bundle: Bundle directory to read.
    :param out: Output directory; defaults to ``<bundle>/swift``.
    :param dtype: Vector precision, ``int8`` or ``float``.
    :param max_passage_chars: Per-passage truncation; 0 keeps passages whole.
    :param no_diaries: Skip the diary KGs.
    :param no_vectors: Skip the vector stage entirely.
    :param no_golden: Skip the golden-query file.
    :param golden_k: Depth recorded per golden query.
    :param verify: Compare the packs against exact fp32 ground truth.
    :param force: Overwrite a non-empty output directory.
    :raises click.ClickException: If the export cannot complete.
    """
    options = ExportOptions(
        bundle=bundle,
        out=out,
        dtype=dtype,
        max_chars=max_passage_chars,
        include_diaries=not no_diaries,
        with_vectors=not no_vectors,
        golden=not no_golden,
        golden_k=golden_k,
        verify=verify,
        force=force,
    )

    try:
        report = export_swift(options, progress=click.echo)
    except ExportError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("")
    for pack in report.packs:
        detail = f"{pack.passages:,} rows"
        if pack.vectors:
            detail += f", {pack.vectors:,} vectors"
        if pack.missing_vectors:
            detail += f", {pack.missing_vectors:,} without one"
        click.echo(f"  {pack.name:<16} {_human(pack.bytes):>12}   {detail}")
    click.echo(f"  {'total':<16} {_human(report.total_bytes):>12}")

    if report.verification:
        recall = report.verification["recall_at_k"]
        delta = report.verification["mean_score_delta"]
        click.echo(
            f"\n  recall@{report.verification['k']} {recall:.3f}"
            + (f"  ·  mean score delta {delta:.4f}" if delta is not None else "")
        )
        if recall < 0.9:
            click.echo(
                "  WARNING: recall is below the 0.9 parity gate. "
                "Rebuild with --dtype float if answers look thin."
            )

    click.echo(f"\nWrote {report.out} in {report.elapsed_s:.1f}s")
    click.echo(
        "Point the app at that directory (Settings ▸ Corpus pack), or copy it to the device."
    )
