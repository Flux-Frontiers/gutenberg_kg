"""gutenkg imagine — generate an image from a text prompt or corpus query."""

from __future__ import annotations

import os
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli


@cli.command("imagine")
@click.argument("prompt", required=False, default=None)
@click.option(
    "--query",
    "-q",
    default=None,
    help="Query the corpus for context (used as/with prompt).",
)
@click.option(
    "--book",
    "-b",
    default=None,
    help="Restrict corpus query to this book title substring.",
)
@click.option(
    "--size",
    "-r",
    "size",
    default="1536x1024",
    show_default=True,
    help="Output size WIDTHxHEIGHT, e.g. 768x512, 1152x768, 1536x1024.",
)
@click.option("--seed", "-s", default=None, type=int, help="Random seed for reproducibility.")
@click.option("--output", "-o", default=None, type=click.Path(), help="Save PNG to this path.")
@click.option(
    "--endpoint",
    default=None,
    help="Image endpoint base URL. Defaults to GUTENKG_IMAGE_ENDPOINT.",
)
@click.option(
    "--steps",
    default=4,
    show_default=True,
    type=int,
    help="Inference steps (4=fast, 25=quality).",
)
@click.option(
    "--open/--no-open",
    "open_image",
    default=True,
    help="Open the image after generation.",
)
@click.option(
    "--corpus-only",
    is_flag=True,
    default=False,
    help="Print the retrieved corpus text and exit (don't generate).",
)
@click.option(
    "--no-vlm",
    is_flag=True,
    default=False,
    help="Skip VLM rewrite — pass corpus text directly to FLUX (faster, lower quality).",
)
def imagine_cmd(
    prompt,
    query,
    book,
    size,
    seed,
    output,
    endpoint,
    steps,
    open_image,
    corpus_only,
    no_vlm,
):
    """Generate an image from a text prompt or corpus content.

    When --query is used, the relevant corpus text is retrieved and rewritten
    into a visual scene description by a local VLM (oMLX) before image generation.

    \b
    Examples:
      gutenkg imagine "the great fire of London at night, oil painting"
      gutenkg imagine --query "great fire" --book pepys
      gutenkg imagine --query "great fire" --book pepys --size 1536x864 -o fire.png
      gutenkg imagine --query "great fire" --book pepys --no-vlm
    """
    from gutenberg_kg import image_gen

    endpoint = endpoint or os.environ.get("GUTENKG_IMAGE_ENDPOINT")
    if not endpoint:
        # Nothing configured is not the same as nothing running. `make up`
        # picks a backend for this host and binds it without exporting
        # anything, so probe before refusing.
        endpoint = image_gen.discover_image_endpoint()
        if endpoint:
            click.echo(f"Using image server at {endpoint} (discovered).")
    if not endpoint:
        probed = ", ".join(image_gen.DEFAULT_IMAGE_ENDPOINTS)
        raise click.UsageError(
            "No image server found. Start one with  make image-server  "
            "(Apple Silicon / CUDA) or  make sdxl-server  (anywhere else), "
            "or point --endpoint / GUTENKG_IMAGE_ENDPOINT at a running one.\n"
            f"Probed: {probed}"
        )

    # Build the final prompt
    final_prompt = _resolve_prompt(prompt, query, book, corpus_only, use_vlm=not no_vlm)

    click.echo(f"Prompt: {final_prompt[:120]}{'…' if len(final_prompt) > 120 else ''}")
    click.echo(f"Size:   {size}  Steps: {steps}  Seed: {seed or 'random'}")
    click.echo("Generating…")

    try:
        pil = image_gen.generate_via_server(
            final_prompt,
            server_url=endpoint,
            size=size,
            seed=seed,
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(f"Image endpoint request failed: {exc}") from exc

    # Determine output path
    if output:
        out_path = Path(output)
    else:
        import tempfile
        import time

        out_path = Path(tempfile.mkdtemp()) / f"imagine_{int(time.time())}.png"

    pil.save(str(out_path))
    click.echo(f"Saved → {out_path}")

    if open_image:
        import subprocess

        subprocess.Popen(["open", str(out_path)])


def _resolve_prompt(
    prompt: str | None,
    query: str | None,
    book: str | None,
    corpus_only: bool,
    use_vlm: bool = True,
) -> str:
    """Return the final generation prompt, optionally enriched with corpus text."""
    if query is None:
        if prompt is None:
            raise click.UsageError("Provide a PROMPT argument or --query.")
        return prompt

    # Retrieve relevant corpus text via DocKG / DiaryKG
    corpus_text = _query_corpus(query, book)

    if corpus_only:
        click.echo("\n── Corpus text ──────────────────────────────────────────")
        click.echo(corpus_text)
        raise SystemExit(0)

    # Rewrite corpus prose into a visual scene description via local VLM
    if use_vlm:
        user_input = corpus_text
        if prompt:
            user_input = f"{corpus_text}\n\nAdditional style/scene notes: {prompt}"
        return _vlm_rewrite(user_input)

    if prompt:
        return f"{prompt}\n\nHistorical context from the corpus:\n{corpus_text}"
    return corpus_text


def _vlm_rewrite(corpus_text: str) -> str:
    """Rewrite corpus prose into an image-generation prompt via the local VLM."""
    from gutenberg_kg.image_gen import vlm_rewrite

    click.echo("Rewriting via VLM…")
    result, error = vlm_rewrite(corpus_text)
    if error:
        click.echo(f"VLM rewrite failed ({error}); using raw corpus text.", err=True)
    else:
        click.echo(f"VLM prompt: {result[:120]}{'…' if len(result) > 120 else ''}")
    return result


def _query_corpus(query: str, book: str | None) -> str:
    """Pull the most relevant chunks from the corpus for *query*."""
    try:
        from doc_kg import DocKG
    except ImportError:
        click.echo("doc-kg not available; using raw query as prompt.", err=True)
        return query

    # Resolve corpus roots relative to the repo root
    repo_root = Path(__file__).parents[3]  # .../src/gutenberg_kg/cli/cmd_imagine.py → repo root
    diary_roots = [
        repo_root / "corpus" / "diaries",
        repo_root / "bundles" / "gutenberg-all" / "diaries",
    ]

    results: list[str] = []

    for root in diary_roots:
        if not root.exists():
            continue
        for diary_dir in sorted(root.iterdir()):
            if book and book.lower() not in diary_dir.name.lower():
                continue
            diarykg = diary_dir / ".diarykg"
            if not diarykg.exists():
                continue
            try:
                kg = DocKG(
                    corpus_root=str(diarykg / "corpus"),
                    db_path=str(diarykg / "graph.sqlite"),
                    lancedb_dir=str(diarykg / "lancedb"),
                )
                result = kg.query(query, k=8)
                for node in result.nodes:
                    text = node.get("text", "")
                    if text and len(text) > 40:
                        results.append(text)
            except Exception:  # noqa: BLE001
                continue
        if results:
            break  # diary hit — don't also search the prose bundle

    # Fall back to main prose DocKG bundle
    if not results:
        bundle = repo_root / "bundles" / "gutenberg-all" / ".dockg"
        if bundle.exists():
            try:
                kg = DocKG(
                    corpus_root=(
                        str(bundle / "corpus") if (bundle / "corpus").exists() else str(bundle)
                    ),
                    db_path=str(bundle / "graph.sqlite"),
                    lancedb_dir=str(bundle / "lancedb"),
                )
                result = kg.query(query, k=8)
                for node in result.nodes:
                    text = node.get("text", "")
                    fp = node.get("file_path", "")
                    if text and len(text) > 40:
                        if book is None or book.lower() in fp.lower():
                            results.append(text)
            except Exception:  # noqa: BLE001
                pass

    if not results:
        return query

    # Trim to a sensible prompt length (~800 chars)
    combined = " ".join(r.strip() for r in results if r.strip())
    return combined[:800]
