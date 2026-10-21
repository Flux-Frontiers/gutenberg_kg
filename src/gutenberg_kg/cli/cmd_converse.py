# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""gutenkg converse -- two books hold a moot (see gutenberg_kg.serve.entmoot)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli
from gutenberg_kg.serve.entmoot import DEFAULT_MODEL

#: The providers ``--backend`` accepts, as in the chat app's provider picker.
_BACKENDS = ("omlx", "ollama", "openai")

_EPILOG = f"""\b
Backend: --backend picks the provider; it defaults to SYNTH_BACKEND, then omlx.
  omlx    local oMLX. SYNTH_ENDPOINT (default http://localhost:8080/v1)
          and SYNTH_API_KEY apply.
  ollama  local Ollama. OLLAMA_ENDPOINT (default http://localhost:11434/v1).
  openai  OpenAI, or any OpenAI-compatible host. Needs OPENAI_API_KEY or
          SYNTH_API_KEY. SYNTH_ENDPOINT points it at another host when
          SYNTH_BACKEND is also openai.

\b
Model: on omlx a moot uses {DEFAULT_MODEL} unless --model names another;
SYNTH_MODEL does not apply there. For quick runs on omlx,
--model Qwen3-4B-Instruct-2507-MLX-8bit is about three times faster
but quotes its book far less reliably. On ollama and openai the backend's
own default applies (SYNTH_MODEL, when SYNTH_BACKEND names that backend).

\b
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


def _env_backend() -> str:
    """The backend SYNTH_BACKEND names, or ``omlx`` when it names none we accept."""
    backend = os.environ.get("SYNTH_BACKEND", "omlx").strip().lower()
    return backend if backend in _BACKENDS else "omlx"


def _make_synth(backend: str):
    """The text synthesizer for ``backend`` (a seam for tests).

    The backend SYNTH_BACKEND names gets the full environment config
    (SYNTH_ENDPOINT, SYNTH_MODEL, SYNTH_API_KEY). Any other backend gets its
    own settings, the way the worker resolves a per-request backend.

    :param backend: One of :data:`_BACKENDS`.
    :returns: A ``TextSynthesizer``.
    """
    from kg_utils.synthesis import text_synth_for_backend, text_synthesizer_from_env

    env_synth = text_synthesizer_from_env()
    if backend == _env_backend():
        return env_synth
    return text_synth_for_backend(backend, env_synth)


def _resolve_model(backend: str, model: str | None, synth) -> tuple[str | None, str]:
    """Pick the model a moot calls with and the name its transcript records.

    :param backend: One of :data:`_BACKENDS`.
    :param model: The ``--model`` value, or ``None``.
    :param synth: The synthesizer, whose own default applies off omlx.
    :returns: ``(model passed to complete, model name recorded)``. The first is
        ``None`` when the synthesizer's default should apply.
    """
    if model:
        return model, model
    if backend == "omlx":
        return DEFAULT_MODEL, DEFAULT_MODEL
    cfg = getattr(synth, "_cfg", None)  # TextSynthesizer keeps its TextConfig here
    return None, cfg.resolved_model() if cfg is not None else ""


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
    for s in u.snaps:
        if s["action"] == "snapped":
            click.echo(f'    snapped "{s["text"]}" to "{s["to"]}"')
        else:
            click.echo(f'    unquoted "{s["text"]}" (not in its source)')


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
@click.option(
    "--backend",
    type=click.Choice(_BACKENDS),
    default=_env_backend,
    show_default="SYNTH_BACKEND, then omlx",
    help="Model provider.",
)
@click.option(
    "--model",
    default=None,
    help=f"Model id. Default: {DEFAULT_MODEL} on omlx, the backend's own default otherwise.",
)
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
    backend: str,
    model: str | None,
    temperature: float,
    worker_url: str | None,
    out: Path | None,
) -> None:
    """Two books hold a moot: each speaks only from passages of its own text.

    Needs a running worker for retrieval and a model provider for the replies.
    \f

    :param book_a: First speaker's catalog key.
    :param book_b: Second speaker's catalog key.
    :param topic: Seed topic, or ``None``.
    :param turns: Total utterances.
    :param k: Passages retrieved per turn.
    :param backend: Model provider, one of :data:`_BACKENDS`.
    :param model: Model id, or ``None`` for the backend's default.
    :param temperature: Sampling temperature.
    :param worker_url: Worker endpoint override.
    :param out: Transcript path, or ``None`` to print only.
    """
    if book_a == book_b:
        raise click.BadParameter("the two books must differ", param_hint="BOOK_B")
    if backend == "openai" and not (
        os.environ.get("OPENAI_API_KEY") or os.environ.get("SYNTH_API_KEY")
    ):
        raise click.UsageError("--backend openai needs OPENAI_API_KEY or SYNTH_API_KEY set")

    import httpx
    from kg_utils.worker import WorkerError

    from gutenberg_kg.serve.entmoot import MootError, run_moot

    url = worker_url or os.environ.get("KGRAG_ENDPOINT", "http://localhost:8000")
    client = _make_client(url)
    synth = _make_synth(backend)
    call_model, model_name = _resolve_model(backend, model, synth)
    click.echo(f"Speaking through {backend}: {model_name or 'the backend default'}")
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
            model=call_model,
            model_name=model_name,
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
        f"/{stats['other_quotes_total']}, of itself {stats['self_quotes_found']}"
        f"/{stats['self_quotes_total']}"
        f"; snapped {stats['quotes_snapped']}, unquoted {stats['quotes_unquoted']}"
    )
    if out is not None:
        out.write_text(json.dumps(transcript.to_dict(), indent=2, ensure_ascii=False) + "\n")
        click.echo(f"Transcript written to {out}")
