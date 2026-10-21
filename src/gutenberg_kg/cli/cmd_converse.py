# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""gutenkg converse -- two books hold a moot (see gutenberg_kg.serve.entmoot)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.serve.entmoot import DEFAULT_MODEL

_EPILOG = f"""\b
Model: a moot uses {DEFAULT_MODEL} unless --model names another.
SYNTH_MODEL and VLLM_MODEL do not apply here. For quick runs,
--model Qwen3-4B-Instruct-2507-MLX-8bit is about three times faster
but quotes its book far less reliably.

\b
Model connection: the synthesizer is built from the environment.
  SYNTH_BACKEND   omlx (default), ollama or openai
  SYNTH_ENDPOINT  falls back to VLLM_ENDPOINT_URL, then http://localhost:8080/v1
  SYNTH_API_KEY   bearer token for the endpoint
The worker secret, when the worker sets one, is read from HANDLER_SECRET.

\b
Book keys are catalog keys, "<genre>/<book>", e.g. "philosophy/Meditations".
A diary is "diaries/<title>". Copy keys from the worker's list_books op or
catalog.json; diary titles contain an em dash.
"""


def _check_key(_ctx, _param, value: str) -> str:
    """Reject a book key that is not ``<genre>/<book>``."""
    genre, _, book = value.partition("/")
    if not genre or not book.strip():
        raise click.BadParameter(f"{value!r} is not a <genre>/<book> key")
    return value


def _make_client(worker_url: str):
    """The worker client (a seam for tests)."""
    from kg_utils.worker import WorkerClient

    return WorkerClient(worker_url, os.environ.get("HANDLER_SECRET", ""))


def _make_synth():
    """The text synthesizer from the environment (a seam for tests)."""
    from kg_utils.synthesis import text_synthesizer_from_env

    return text_synthesizer_from_env()


def _print_utterance(u) -> None:
    """Print one utterance and the sections it cites."""
    click.echo(f"\n[{u.turn}] {u.title}: {u.text}")
    labels = {r["tag"]: r["label"] for r in u.retrieved}
    cited = ", ".join(f"[{t}] {labels[t]}" for t in u.cited)
    click.echo(f"    cites: {cited or '(nothing)'}")
    if not u.grounded:
        g = u.grounding
        click.echo(
            f"    UNGROUNDED: tags_valid={g['tags_valid']}, "
            f"quotes {g['quotes_found']}/{g['quotes_total']} found"
        )


@cli.command("converse", epilog=_EPILOG)
@click.argument("book_a", callback=_check_key)
@click.argument("book_b", callback=_check_key)
@click.option("--topic", default=None, help="The subject the moot discusses (recommended).")
@click.option(
    "--turns",
    type=click.IntRange(2, 40),
    default=8,
    show_default=True,
    help="Total utterances.",
)
@click.option(
    "--k", type=click.IntRange(1, 20), default=6, show_default=True, help="Passages per turn."
)
@click.option("--model", default=DEFAULT_MODEL, show_default=True, help="oMLX model id.")
@click.option(
    "--temperature", type=float, default=0.6, show_default=True, help="Sampling temperature."
)
@click.option(
    "--worker",
    "worker_url",
    default=None,
    help="KGRAG worker URL (default $KGRAG_ENDPOINT or http://localhost:8000).",
)
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the JSON transcript here; default: print only.",
)
def converse_cmd(
    book_a: str,
    book_b: str,
    topic: str | None,
    turns: int,
    k: int,
    model: str,
    temperature: float,
    worker_url: str | None,
    out: Path | None,
) -> None:
    """Two books hold a moot: each speaks only from passages of its own text.

    Needs a running worker for retrieval and a local model for the replies.
    \f

    :param book_a: First speaker's catalog key.
    :param book_b: Second speaker's catalog key.
    :param topic: Seed topic, or ``None``.
    :param turns: Total utterances.
    :param k: Passages retrieved per turn.
    :param model: Model id.
    :param temperature: Sampling temperature.
    :param worker_url: Worker endpoint override.
    :param out: Transcript path, or ``None`` to print only.
    """
    if book_a == book_b:
        raise click.BadParameter("the two books must differ", param_hint="BOOK_B")

    import httpx
    from kg_utils.worker import WorkerError

    from gutenberg_kg.serve.entmoot import MootError, run_moot

    url = worker_url or os.environ.get("KGRAG_ENDPOINT", "http://localhost:8000")
    client = _make_client(url)
    synth = _make_synth()
    if topic:
        click.echo(f"The moot gathers to discuss: {topic}")
    try:
        transcript = run_moot(
            client,
            synth,
            [book_a, book_b],
            topic,
            turns,
            k=k,
            model=model,
            temperature=temperature,
            on_utterance=_print_utterance,
        )
    except WorkerError as exc:
        raise click.ClickException(f"worker error: {exc}") from exc
    except MootError as exc:
        raise click.ClickException(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise click.ClickException(f"cannot reach the worker at {url}: {exc}") from exc

    stats = transcript.stats()
    rate = stats["quote_found_rate"]
    click.echo(
        f"\n{stats['turns']} turns, tags valid in {stats['tags_valid_turns']}, "
        f"{stats['turns_citing']} citing; quotes found "
        f"{stats['quotes_found']}/{stats['quotes_total']}"
        + (f" ({rate:.0%})" if rate is not None else "")
        + f"; [oN] quotes of the other tree valid {stats['other_quotes_found']}"
        f"/{stats['other_quotes_total']}"
    )
    if out is not None:
        out.write_text(json.dumps(transcript.to_dict(), indent=2, ensure_ascii=False) + "\n")
        click.echo(f"Transcript written to {out}")
