# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""gutenkg export-embedder — convert the query embedder to Core ML."""

from __future__ import annotations

from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.export_embedder import (
    MODEL_ID,
    EmbedderExportError,
    export_embedder,
)


@cli.command("export-embedder")
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=Path("bundles/gutenberg-all/swift"),
    show_default=True,
    help="Directory to write the model into — normally beside the packs.",
)
@click.option(
    "--compute-units",
    type=click.Choice(["ALL", "CPU_AND_GPU", "CPU_ONLY"]),
    default="ALL",
    show_default=True,
    help="Core ML compute units.  ALL lets the Neural Engine take it.",
)
def export_embedder_cmd(out: Path, compute_units: str) -> None:
    """Convert the corpus embedder to Core ML for on-device query embedding.

    The packs hold vectors from this model, and a query embedded by any other
    lands in a different space — so the app has to carry it.  Needs torch,
    transformers and coremltools, which are not project dependencies:

    \b
      poetry run pip install torch transformers coremltools
      gutenkg export-embedder

    Writes BGEEmbedder.mlpackage, vocab.txt and embedder.json, then checks the
    converted model against PyTorch and refuses to ship one that disagrees.
    \f

    :param out: Output directory.
    :param compute_units: Core ML compute units to compile for.
    :raises click.ClickException: If conversion or the parity check fails.
    """
    click.echo(f"Converting {MODEL_ID} → Core ML")
    try:
        report = export_embedder(out, compute_units=compute_units, progress=click.echo)
    except EmbedderExportError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("")
    click.echo(f"  {report.package.name:<24} {report.bytes / 1024 / 1024:,.1f} MB")
    click.echo(f"  {report.vocab.name:<24} {report.vocab.stat().st_size / 1024:,.0f} KB")
    click.echo(f"  {report.metadata.name:<24}")
    click.echo(f"\n  parity vs PyTorch: cosine {report.parity:.5f}")
    click.echo(f"\nWrote {out}")
