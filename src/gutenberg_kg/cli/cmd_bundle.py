"""``gutenkg bundle`` -- validate, resolve, build, export, and image a spec.

The selective bundle export design's orchestrator
(``analysis/SELECTIVE_BUNDLE_EXPORT_PLAN.md``). ``validate``/``resolve`` are
phase 1; ``export`` is phase 2, extended here to cover both materialization
modes now that phase 3 exists; ``build``/``image``/``make`` are phase 4 --
they do not replace the Make targets, they are what those targets call.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

from gutenberg_kg.build_corpus import BuildCorpusOptions, run_build_corpus
from gutenberg_kg.bundle_spec import (
    BundleSpec,
    BundleSpecError,
    ResolvedSelection,
    load_spec,
    resolve_selection,
    validate_spec,
)
from gutenberg_kg.cli.cmd_export_swift import _human
from gutenberg_kg.cli.main import cli
from gutenberg_kg.export_swift import ExportError, ExportOptions, export_swift

#: Mirrors the Makefile's own ``IMAGE`` variable (Decision 8: the repository
#: name is fixed, only the tag varies). Two copies rather than one shared
#: source because Make and this CLI are separate control paths that neither
#: parses the other's config -- keep them equal if either ever changes.
IMAGE_REPOSITORY = "corpus-gutenberg"


def _load_and_validate(spec_path: Path) -> tuple[BundleSpec, ResolvedSelection]:
    """Load a spec, resolve it, and validate it -- the first step of every
    ``bundle`` subcommand.

    :param spec_path: Path to the spec's TOML file.
    :returns: The spec and its resolved selection.
    :raises click.ClickException: If the spec cannot be parsed.
    :raises SystemExit: If validation finds any problem, after printing all
        of them (matching ``bundle validate``'s own behavior).
    """
    try:
        spec = load_spec(spec_path)
    except BundleSpecError as exc:
        raise click.ClickException(str(exc)) from exc

    resolved = resolve_selection(spec)
    problems = validate_spec(spec, resolved)
    if problems:
        click.echo(f"{spec.name}: {len(problems)} problem(s):")
        for problem in problems:
            click.echo(f"  - {problem}")
        raise SystemExit(1)
    return spec, resolved


def _bundle_dir(spec: BundleSpec) -> Path:
    """Where a ``materialize = "rebuild"`` spec's DocKG lives."""
    return Path("bundles") / spec.name


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
    spec, resolved = _load_and_validate(spec_path)
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
    # Printing for a script needs no resolution or validation -- a spec with
    # an unresolved selector still has a name and an image tag, and a
    # Makefile recipe calling --print-bundle-name should not have to pay for
    # (or fail on) a full corpus resolve just to learn the directory name.
    try:
        spec = load_spec(spec_path)
    except BundleSpecError as exc:
        raise click.ClickException(str(exc)) from exc

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


@bundle_group.command("build")
@click.argument("spec_path", metavar="SPEC", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--force",
    is_flag=True,
    help="Rebuild even if bundles/<name>/.dockg/graph.sqlite already exists.",
)
def bundle_build(spec_path: Path, force: bool):
    """Build a spec's DocKG bundle from source. A no-op for materialize = "none".
    \f

    :param spec_path: Path to the spec's TOML file.
    :param force: Rebuild even when the bundle already has an index.
    :raises click.ClickException: If the spec is invalid or the build fails.
    """
    spec, resolved = _load_and_validate(spec_path)

    if spec.materialize == "none":
        click.echo(f'{spec.name}: materialize = "none" -- nothing to build.')
        return

    graph_path = _bundle_dir(spec) / ".dockg" / "graph.sqlite"
    if graph_path.exists() and not force:
        raise click.ClickException(f"{graph_path} already exists — pass --force to rebuild it.")

    opts = BuildCorpusOptions(
        output=spec.name,
        catalog_keys=resolved.catalog_keys,
        diary_dirs=resolved.diary_dirs,
        product_name=spec.name,
        product_version=spec.version,
        spec_path=spec_path,
        force_overwrite_full=force,
    )
    rc = run_build_corpus(sorted(resolved.genres_implied), opts)
    if rc != 0:
        raise SystemExit(rc)


def _export_options_for_spec(
    spec: BundleSpec,
    resolved: ResolvedSelection,
    *,
    out: Path | None,
    verify: bool,
    force: bool,
) -> ExportOptions:
    """The right :class:`ExportOptions` for a spec, whichever materialization
    it names.

    ``materialize = "none"`` filters ``source_bundle`` (normally
    ``gutenberg-all``) at export time, the same as phase 2 always did.
    ``materialize = "rebuild"`` reads from ``bundles/<name>/``, which
    ``bundle build`` already filtered when it walked the corpus -- so
    ``catalog_keys`` does no filtering work there, every book left in that
    bundle already matches -- but it is still passed through, because the
    manifest's ``"product"`` block is gated on it being set, and a
    rebuild-mode spec's identity belongs in the Swift manifest exactly as
    much as a filter-at-export one's does.

    :param spec: The spec being exported.
    :param resolved: Its resolved selection.
    :param out: Output directory override.
    :param verify: Compare the packs against exact fp32 ground truth.
    :param force: Overwrite a non-empty output directory.
    :raises click.ClickException: If ``materialize = "none"`` with no
        ``source_bundle``, or ``materialize = "rebuild"`` with no built
        bundle yet.
    """
    if spec.materialize == "none":
        if spec.source_bundle is None:
            # validate_spec already enforces this for materialize = "none",
            # so this narrows the type rather than handling a real gap.
            raise click.ClickException(f"{spec.name}: source_bundle is required")
        return ExportOptions(
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

    bundle_dir = _bundle_dir(spec)
    if not (bundle_dir / ".dockg").exists():
        raise click.ClickException(
            f"{bundle_dir / '.dockg'} does not exist — run `gutenkg bundle build "
            f"{spec.name}`'s spec first."
        )
    return ExportOptions(
        bundle=bundle_dir,
        out=out or (bundle_dir / "swift"),
        # Redundant as a *filter* -- bundle_build already walked the corpus
        # down to exactly this selection -- but _manifest()'s "product" block
        # is gated on catalog_keys being set, and a rebuild-mode spec's
        # identity belongs in the Swift manifest exactly as much as a
        # filter-at-export one's does. Passing it here costs one more (cheap,
        # since the bundle is already small) vector scan predicate in
        # exchange for the manifest actually saying what shipped.
        catalog_keys=resolved.catalog_keys,
        golden_queries=spec.golden_queries or None,
        product_name=spec.name,
        product_version=spec.version,
        verify=verify,
        force=force,
    )


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
    """Export a spec's Swift packs.
    \f

    ``materialize = "none"`` filters ``source_bundle`` at export time.
    ``materialize = "rebuild"`` reads ``bundles/<name>/``, which
    ``gutenkg bundle build`` must have produced first.

    :param spec_path: Path to the spec's TOML file.
    :param out: Output directory override.
    :param verify: Compare the packs against exact fp32 ground truth.
    :param force: Overwrite a non-empty output directory.
    :raises click.ClickException: If the spec is invalid, its bundle is not
        ready, or the export itself fails.
    """
    spec, resolved = _load_and_validate(spec_path)
    options = _export_options_for_spec(spec, resolved, out=out, verify=verify, force=force)

    try:
        report = export_swift(options, progress=click.echo)
    except ExportError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo("")
    for pack in report.packs:
        click.echo(f"  {pack.name:<16} {_human(pack.bytes):>12}   {pack.passages:,} rows")
    click.echo(f"  {'total':<16} {_human(report.total_bytes):>12}")
    click.echo(f"\nWrote {report.out} in {report.elapsed_s:.1f}s")


def _detect_runtime() -> str | None:
    """Which container runtime is available: ``"docker"``, ``"apple"``, or None."""
    if shutil.which("docker") is not None:
        return "docker"
    if shutil.which("container") is not None:
        return "apple"
    return None


@bundle_group.command("image")
@click.argument("spec_path", metavar="SPEC", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--runtime",
    type=click.Choice(["docker", "apple"]),
    default=None,
    help="Container runtime to use.  [default: docker if installed, else apple]",
)
def bundle_image(spec_path: Path, runtime: str | None):
    """Bake a spec's bundle into a tagged container image.
    \f

    Requires a materialized DocKG at ``bundles/<name>/`` — ``materialize =
    "none"`` (Swift-only) is refused, per Decision 9: the worker reads
    ``GUTENBERG_ROOT/.dockg/graph.sqlite`` plus ``catalog.json``, and a
    packs-only directory is not a worker root. Never retags ``:latest``;
    that name is reserved for ``gutenberg-all``.

    :param spec_path: Path to the spec's TOML file.
    :param runtime: ``"docker"`` or ``"apple"``; autodetected when omitted.
    :raises click.ClickException: If the spec is invalid, is Swift-only,
        has no built bundle yet, or no runtime is available.
    """
    spec, _resolved = _load_and_validate(spec_path)

    if spec.materialize == "none":
        raise click.ClickException(
            f'{spec.name}: materialize = "none" is Swift-only and cannot be imaged — '
            "an image bake never silently COPYs source_bundle under a product tag. "
            'Set materialize = "rebuild" and run `gutenkg bundle build` first.'
        )

    dockg_dir = _bundle_dir(spec) / ".dockg"
    if not dockg_dir.exists():
        raise click.ClickException(
            f"{dockg_dir} does not exist — run `gutenkg bundle build` first."
        )

    chosen = runtime or _detect_runtime()
    if chosen is None:
        raise click.ClickException("neither docker nor Apple's `container` CLI is available.")
    tool = "docker" if chosen == "docker" else "container"
    tag = f"{IMAGE_REPOSITORY}:{spec.image_tag}"

    command = [
        tool,
        "build",
        "-f",
        "docker/Dockerfile",
        "--build-arg",
        f"BUNDLE={spec.name}",
        "-t",
        tag,
        ".",
    ]
    click.echo(f"$ {' '.join(command)}")
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    click.echo(f"built {tag}")


@bundle_group.command("make")
@click.argument("spec_path", metavar="SPEC", type=click.Path(exists=True, path_type=Path))
@click.option("--verify", is_flag=True, help="Measure recall against exact fp32 ground truth.")
@click.option("--force", is_flag=True, help="Rebuild/overwrite even if already present.")
@click.option("--image", "with_image", is_flag=True, help="Also bake and tag a container image.")
@click.option(
    "--runtime",
    type=click.Choice(["docker", "apple"]),
    default=None,
    help="Container runtime for --image.  [default: docker if installed, else apple]",
)
@click.pass_context
def bundle_make(
    ctx: click.Context,
    spec_path: Path,
    verify: bool,
    force: bool,
    with_image: bool,
    runtime: str | None,
):
    """Run a spec end to end: validate, build (unless Swift-only), export.
    \f

    ``--image`` is refused up front for ``materialize = "none"`` — better to
    fail before spending minutes on a build/export pass than after.

    :param spec_path: Path to the spec's TOML file.
    :param verify: Compare the packs against exact fp32 ground truth.
    :param force: Rebuild/overwrite even where already present.
    :param with_image: Also bake and tag a container image.
    :param runtime: ``"docker"`` or ``"apple"``, for ``--image``.
    :raises click.ClickException: If the spec is invalid, or ``--image`` is
        combined with ``materialize = "none"``.
    """
    spec, resolved = _load_and_validate(spec_path)

    if with_image and spec.materialize == "none":
        raise click.ClickException(
            f'{spec.name}: --image needs materialize = "rebuild" — materialize = "none" '
            "is Swift-only."
        )

    if spec.materialize == "none":
        click.echo(f'{spec.name}: materialize = "none" -- skipping build.')
    else:
        click.echo(f"{spec.name}: building …")
        graph_path = _bundle_dir(spec) / ".dockg" / "graph.sqlite"
        if graph_path.exists() and not force:
            click.echo(f"  {graph_path} already exists — skipping (pass --force to rebuild).")
        else:
            opts = BuildCorpusOptions(
                output=spec.name,
                catalog_keys=resolved.catalog_keys,
                diary_dirs=resolved.diary_dirs,
                product_name=spec.name,
                product_version=spec.version,
                spec_path=spec_path,
                force_overwrite_full=force,
            )
            rc = run_build_corpus(sorted(resolved.genres_implied), opts)
            if rc != 0:
                raise SystemExit(rc)

    click.echo(f"{spec.name}: exporting …")
    # Always force here, independent of --force above: --force there guards
    # the *build* step's idempotence (skip an existing graph.sqlite), while
    # exporting is cheap enough that `make` re-running it every time (the
    # design's own Makefile sketch does the same, unconditionally) is the
    # simpler contract than a second flag meaning something different.
    ctx.invoke(bundle_export, spec_path=spec_path, out=None, verify=verify, force=True)

    if with_image:
        click.echo(f"{spec.name}: imaging …")
        ctx.invoke(bundle_image, spec_path=spec_path, runtime=runtime)
