"""audit subcommand — verify Project Gutenberg corpus integrity."""

from pathlib import Path

import click

from gutenberg_kg import audit as au
from gutenberg_kg import sections as sec
from gutenberg_kg.cli.main import cli
from gutenberg_kg.cli.options import ALL_GENRES, CORPUS_ROOT


@cli.command("audit")
@click.option(
    "--genre",
    type=click.Choice(ALL_GENRES),
    multiple=True,
    help="Genre to audit (repeatable; default: all).",
)
@click.option(
    "--json", "as_json", is_flag=True, default=False, help="Emit JSON instead of a table."
)
@click.option(
    "--registry",
    type=click.Path(),
    default=None,
    help="Override the KGRAG registry path.",
)
@click.option(
    "--sections",
    is_flag=True,
    default=False,
    help="Also report books with most of their text in one oversized section.",
)
@click.option(
    "--baseline",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="With --sections: CSV to diff section counts against.",
)
@click.option(
    "--csv-out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="With --sections: write every book's section measurements as CSV.",
)
def audit(genre, as_json, registry, sections, baseline, csv_out):
    """Verify corpus integrity and report problems.

    Checks every book for a present, parseable full-text ``.md`` and
    ``reference.md``; that diaries parse with their ``.diary_format`` and carry a
    ``.diarykg/`` (never a stray ``.dockg/``); that no Gutenberg ID is shared by
    two books; and that registered KGs point at an existing index of the right
    type.  "Not built" / "not registered" are warnings (expected before a
    rebuild); anything else is an error.

    Exits non-zero when any error is found, so it is safe to run in CI.

    --sections adds a structure report: books with more than 90% of their text
    in one section over 100,000 characters, which usually means headings the
    parser missed. It is advisory and does not change the exit code.
    \f

    :param genre: Tuple of genres to audit (empty = all).
    :param as_json: Emit machine-readable JSON.
    :param registry: Override the KGRAG registry path.
    :param sections: Also run the oversized-section report.
    :param baseline: Baseline CSV for the section report.
    :param csv_out: Where to write the section report's CSV.
    """
    if (baseline or csv_out) and not sections:
        raise click.UsageError("--baseline and --csv-out need --sections")
    rc = au.run_audit(list(genre), registry=registry, as_json=as_json)
    if sections:
        _section_report(list(genre), baseline, csv_out)
    if rc != 0:
        raise SystemExit(rc)


def _section_report(genres: list[str], baseline: Path | None, csv_out: Path | None) -> None:
    """Print the oversized-section report.

    :param genres: Genres to measure (empty = all).
    :param baseline: Baseline CSV to diff section counts against.
    :param csv_out: Where to write every book's measurements.
    """
    results = sec.scan_corpus(CORPUS_ROOT, genres)
    flagged = sec.flagged(results)
    click.echo(
        f"\n{len(flagged)} books have >{sec.FLAG_SHARE:.0%} of their text in a single "
        f"section over {sec.FLAG_CHARS:,} characters:"
    )
    for r in flagged:
        click.echo(
            f"{r.share_in_largest * 100:5.1f}%  {r.sections:3d} secs  {r.largest_chars:>10,} ch  "
            f"[{r.genre}]  {r.book}  -- {r.largest_section_title}"
        )
    if csv_out:
        sec.write_csv(results, csv_out)
        click.echo(f"\nWrote {len(results)} rows to {csv_out}")
    if baseline:
        changed = sec.baseline_changes(results, sec.load_baseline(baseline))
        if changed:
            click.echo(f"\n{len(changed)} book(s) changed section count vs baseline:")
            for book, old, new in changed:
                click.echo(f"  {book}: {old} -> {new}")
        else:
            click.echo("\nNo section-count changes vs baseline.")
