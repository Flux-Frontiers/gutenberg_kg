"""``gutenkg bundle`` -- validate and resolve selective bundle specs.

Phase 1 of the selective bundle export design
(``analysis/SELECTIVE_BUNDLE_EXPORT_PLAN.md``): the spec model and its
resolver against the corpus. No build or export behavior changes here --
``bundle resolve``/``validate`` only report what a spec would select.
"""

from __future__ import annotations

from pathlib import Path

import click

from gutenberg_kg.bundle_spec import (
    BundleSpecError,
    load_spec,
    resolve_selection,
    validate_spec,
)
from gutenberg_kg.cli.cmd_export_swift import _human
from gutenberg_kg.cli.main import cli
from gutenberg_kg.export_swift import ExportError, ExportOptions, export_swift


@cli.group("bundle")
def bundle_group():
    """Work with selective bundle specs."""
    pass


@bundle_group.command("validate")
@click.argument("spec_path", metavar="SPEC", type=click.Path(exists=True, path_type=Path))
def bundle_validate(spec_path: Path):
    """Validate a bundle spec against the corpus.
    \f

    :param spec_path: Path to the spec's TOML file.
    """
    try:
        spec = load_spec(spec_path)
    except BundleSpecError as exc:
        click.echo(f"invalid spec: {exc}", err=True)
        raise SystemExit(1) from exc

    resolved = resolve_selection(spec)
    problems = validate_spec(spec, resolved)

    if problems:
        click.echo(f"{spec.name}: {len(problems)} problem(s):")
        for problem in problems:
            click.echo(f"  - {problem}")
        raise SystemExit(1)

    click.echo(
        f"{spec.name} {spec.version}: ok — {len(resolved.catalog_keys)} book(s) across "
        f"{len(resolved.genres_implied)} genre(s)"
    )


@bundle_group.command("resolve")
@click.argument("spec_path", metavar="SPEC", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--print-bundle-name",
    is_flag=True,
    default=False,
    help="Print only the bundle's name (for scripting) and exit.",
)
@click.option(
    "--print-image-tag",
    is_flag=True,
    default=False,
    help="Print only the resolved image tag (for scripting) and exit.",
)
def bundle_resolve(spec_path: Path, print_bundle_name: bool, print_image_tag: bool):
    """Resolve a bundle spec's selection against the corpus.
    \f

    :param spec_path: Path to the spec's TOML file.
    :param print_bundle_name: When set, print only ``spec.name`` and exit —
        for a Makefile or shell script that needs the name without parsing
        the full report.
    :param print_image_tag: Same, for ``spec.image_tag``.
    """
    try:
        spec = load_spec(spec_path)
    except BundleSpecError as exc:
        click.echo(f"invalid spec: {exc}", err=True)
        raise SystemExit(1) from exc

    if print_bundle_name:
        click.echo(spec.name)
        return
    if print_image_tag:
        click.echo(spec.image_tag)
        return

    resolved = resolve_selection(spec)

    click.echo(f"{spec.name} {spec.version}")
    if spec.description:
        click.echo(f"  {spec.description}")
    click.echo(f"  materialize:  {spec.materialize}")
    click.echo(f"  image tag:    {spec.image_tag}")
    click.echo(f"  diaries:      {spec.diaries}")
    click.echo(f"  genres:       {len(resolved.genres_implied)}")
    for genre in sorted(resolved.genres_implied):
        click.echo(f"    - {genre}")
    click.echo(f"  books:        {len(resolved.catalog_keys)}")
    for key in sorted(resolved.catalog_keys):
        click.echo(f"    - {key}")

    if resolved.missing:
        click.echo(f"  unresolved:   {len(resolved.missing)}")
        for selector in resolved.missing:
            click.echo(f"    - {selector!r}")
        raise SystemExit(1)


@bundle_group.command("export")
@click.argument("spec_path", metavar="SPEC", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory.  [default: bundles/<name>/swift]",
)
@click.option(
    "--verify",
    is_flag=True,
    help="Measure the packs' recall against exact fp32 ground truth.",
)
@click.option("--force", is_flag=True, help="Overwrite a non-empty output directory.")
def bundle_export(spec_path: Path, out: Path | None, verify: bool, force: bool):
    """Export a spec's Swift packs, filtered at export from its source bundle.
    \f

    Only ``materialize = "none"`` is supported here — phase 2 filters an
    already-built bundle's packs, it does not build one. A spec with
    ``materialize = "rebuild"`` needs phase 3's ``build-corpus`` support
    first; run ``export-swift --spec`` once that has produced the bundle.

    :param spec_path: Path to the spec's TOML file.
    :param out: Output directory; defaults to ``bundles/<name>/swift``.
    :param verify: Compare the packs against exact fp32 ground truth.
    :param force: Overwrite a non-empty output directory.
    :raises click.ClickException: If the spec is invalid, requires a rebuild,
        or the export itself fails.
    """
    try:
        spec = load_spec(spec_path)
    except BundleSpecError as exc:
        click.echo(f"invalid spec: {exc}", err=True)
        raise SystemExit(1) from exc

    resolved = resolve_selection(spec)
    problems = validate_spec(spec, resolved)
    if problems:
        click.echo(f"{spec.name}: {len(problems)} problem(s):")
        for problem in problems:
            click.echo(f"  - {problem}")
        raise SystemExit(1)

    if spec.materialize != "none":
        raise click.ClickException(
            f"{spec_path} has materialize = {spec.materialize!r}; `bundle export` "
            'currently supports materialize = "none" only. Set materialize = '
            '"none" and source_bundle in the spec, or wait for phase 3\'s '
            "build-corpus support to rebuild a filtered bundle first."
        )
    # validate_spec already enforces this for materialize = "none" (the branch
    # above just confirmed we are in), so this narrows the type rather than
    # handling a real gap -- the message is defensive, not an expected path.
    if spec.source_bundle is None:
        raise click.ClickException(f"{spec_path}: source_bundle is required")

    options = ExportOptions(
        bundle=spec.source_bundle,
        out=out or (Path("bundles") / spec.name / "swift"),
        catalog_keys=resolved.catalog_keys,
        diary_dirs=resolved.diary_dirs,
        golden_queries=spec.golden_queries or None,
        product_name=spec.name,
        product_version=spec.version,
        verify=verify,
        force=force,
    )

    try:
        report = export_swift(options, progress=click.echo)
    except ExportError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("")
    for pack in report.packs:
        click.echo(f"  {pack.name:<16} {_human(pack.bytes):>12}   {pack.passages:,} rows")
    click.echo(f"  {'total':<16} {_human(report.total_bytes):>12}")
    click.echo(f"\nWrote {report.out} in {report.elapsed_s:.1f}s")
