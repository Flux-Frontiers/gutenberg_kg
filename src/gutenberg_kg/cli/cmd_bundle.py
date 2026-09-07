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
from gutenberg_kg.cli.main import cli


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
