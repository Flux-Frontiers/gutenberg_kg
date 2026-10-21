# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""gutenkg converse -- two books hold a moot (see gutenberg_kg.serve.entmoot)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
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


#: Border colors of the first and second tree's speech bubbles.
_TREE_STYLES = ("green", "magenta")
# Quoted spans (straight or curly marks) and citation tags, for highlighting.
_OPEN_DQ, _CLOSE_DQ = chr(0x201C), chr(0x201D)  # curly double quotes
_QUOTED = f'["{_OPEN_DQ}][^"{_CLOSE_DQ}]+["{_CLOSE_DQ}]'
_TAGS = r"[\[(][soSO]\d+(?:\s*,\s*[soSO]\d+)*[\])]"


def _snap_note(s: dict) -> str:
    """One line describing a quote :func:`~gutenberg_kg.serve.entmoot.snap_quotes` corrected."""
    if s["action"] == "snapped":
        return f'snapped "{s["text"]}" -> "{s["to"]}"'
    return f'unquoted "{s["text"]}" ({s["reason"]})'


def _machine_description() -> str:
    """CPU brand and installed RAM, as quiltwright's run reports give them.

    :returns: e.g. ``"Apple M5 Max, 64 GB RAM"``, or a coarser fallback off macOS.
    """
    import platform
    import subprocess

    def sysctl(key: str) -> str:
        try:
            done = subprocess.run(
                ["sysctl", "-n", key], capture_output=True, text=True, timeout=5, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return done.stdout.strip()

    brand, memsize = sysctl("machdep.cpu.brand_string"), sysctl("hw.memsize")
    if brand and memsize.isdigit():
        return f"{brand}, {round(int(memsize) / 1024**3)} GB RAM"
    return brand or platform.processor() or platform.machine() or "unknown"


def _run_info(
    started, elapsed: float, turn_seconds: list[float], backend: str, model: str, worker: str
) -> dict:
    """The run summary: timing, machine and model, as recorded in ``--out`` under ``run``.

    :param started: The moot's start time, timezone-aware.
    :param elapsed: Wall-clock seconds for the whole moot.
    :param turn_seconds: Seconds per turn, retrieval and any retry included.
    :param backend: Model provider.
    :param model: Model id, or ``""`` for the backend default.
    :param worker: Worker URL.
    :returns: A JSON-ready dict.
    """
    import platform
    import socket

    from gutenberg_kg import __version__

    return {
        "started": started.isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "turn_seconds": [round(t, 1) for t in turn_seconds],
        "host": socket.gethostname(),
        "machine": _machine_description(),
        "os": f"{platform.system()} {platform.release()} / {platform.machine()}",
        "python": platform.python_version(),
        "gutenberg_kg": __version__,
        "backend": backend,
        "model": model or "the backend default",
        "worker": worker,
    }


def _run_rows(run: dict) -> list[tuple[str, str]]:
    """The run summary as label/value rows, for either output."""
    from gutenberg_kg.ingest import fmt_duration

    turns = run["turn_seconds"]
    per_turn = (
        f"{fmt_duration(sum(turns) / len(turns))} average, {fmt_duration(max(turns))} slowest"
        if turns
        else "-"
    )
    return [
        ("Started", run["started"]),
        ("Elapsed", fmt_duration(run["elapsed_seconds"])),
        ("Per turn", per_turn),
        ("Backend / model", f"{run['backend']} / {run['model']}"),
        ("Worker", run["worker"]),
        ("Host", run["host"]),
        ("Machine", run["machine"]),
        ("OS", run["os"]),
        ("Python / gutenberg-kg", f"{run['python']} / {run['gutenberg_kg']}"),
    ]


def _render_run(console, run: dict) -> None:
    """Print the run summary as a table."""
    from rich.table import Table

    table = Table(title="Run", show_header=False, title_style="bold")
    table.add_column(style="dim")
    table.add_column()
    for label, value in _run_rows(run):
        table.add_row(label, value)
    console.print()
    console.print(table, justify="center")


def _render_header(console, keys: list[str], topic: str | None, backend: str, model: str) -> None:
    """Print the moot's opening rule: both books, the topic and the model."""
    from rich.text import Text

    names = " and ".join(key.split("/", 1)[-1] for key in keys)
    console.rule(Text(f"A moot of {names}", style="bold"))
    if topic:
        console.print(
            Text(f"The moot gathers to discuss: {topic}", style="italic"), justify="center"
        )
    console.print(
        Text(f"Speaking through {backend}: {model or 'the backend default'}", style="dim"),
        justify="center",
    )


def _render_utterance(console, u, first_key: str) -> None:
    """Print one utterance as a speech bubble, the first tree left, the second right.

    :param console: A Rich ``Console``.
    :param u: The utterance.
    :param first_key: The first speaker's key, which takes the left side.
    """
    from rich.align import Align
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    left = u.speaker == first_key
    style = _TREE_STYLES[0 if left else 1]
    body = Text(u.text)
    body.highlight_regex(_QUOTED, "bold")
    body.highlight_regex(_TAGS, "dim cyan")
    notes = Text()
    labels = {r["tag"]: r["label"] for r in u.retrieved}
    if u.cited:
        notes.append("cites " + ", ".join(f"{t} {labels[t]}" for t in u.cited), style="dim")
    if not u.grounded:
        g = u.grounding
        notes.append(
            f"\nungrounded: tags valid {g['tags_valid']}, "
            f"quotes {g['quotes_found']}/{g['quotes_total']} found",
            style="red",
        )
    for s in u.snaps:
        notes.append(f"\n{_snap_note(s)}", style="yellow")
    width = min(console.width, max(40, int(console.width * 0.72)))
    panel = Panel(
        Group(body, Text(""), notes) if notes else body,
        title=Text(f"[{u.turn}] {u.title}", style=f"bold {style}"),
        title_align="left" if left else "right",
        border_style=style,
        width=width,
        padding=(0, 1),
    )
    console.print(Align.left(panel) if left else Align.right(panel))


def _render_stats(console, stats: dict) -> None:
    """Print the moot's grounding stats as a table."""
    from rich.table import Table

    def rate(found: int, total: int) -> str:
        return f"{found}/{total}" + (f" ({found / total:.0%})" if total else "")

    table = Table(title="Grounding", show_header=False, title_style="bold")
    table.add_column(style="dim")
    table.add_column(justify="right")
    table.add_row("Turns with valid tags", f"{stats['tags_valid_turns']}/{stats['turns']}")
    table.add_row("Grounded turns", f"{stats['grounded_turns']}/{stats['turns']}")
    table.add_row("Own-book quotes found", rate(stats["quotes_found"], stats["quotes_total"]))
    table.add_row(
        "Quotes of the other tree valid",
        rate(stats["other_quotes_found"], stats["other_quotes_total"]),
    )
    table.add_row(
        "Quotes of itself valid", rate(stats["self_quotes_found"], stats["self_quotes_total"])
    )
    table.add_row("Quotes per turn", f"{stats['quotes_per_turn']}")
    table.add_row("Snapped / unquoted", f"{stats['quotes_snapped']} / {stats['quotes_unquoted']}")
    table.add_row("Unquoted as too short", f"{stats['quotes_too_short']}")
    console.print()
    console.print(table, justify="center")


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
        click.echo(f"    {_snap_note(s)}")


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
@click.option(
    "--plain",
    is_flag=True,
    help="Print plain text instead of speech bubbles (automatic when not a terminal).",
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
    plain: bool,
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
    :param plain: Print plain text even on a terminal.
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
    console = None
    if not plain:
        from rich.console import Console

        console = Console(highlight=False)
        if not console.is_terminal:
            console = None
    if console is not None:
        _render_header(console, [book_a, book_b], topic, backend, model_name)
        show = lambda u: _render_utterance(console, u, book_a)  # noqa: E731
    else:
        click.echo(f"Speaking through {backend}: {model_name or 'the backend default'}")
        if topic:
            click.echo(f"The moot gathers to discuss: {topic}")
        show = _print_utterance

    started = datetime.now().astimezone()
    t0 = last = time.perf_counter()
    turn_seconds: list[float] = []

    def on_utterance(u) -> None:
        nonlocal last
        now = time.perf_counter()
        turn_seconds.append(now - last)
        last = now
        show(u)

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
            on_utterance=on_utterance,
        )
    except WorkerError as exc:
        raise click.ClickException(f"worker error: {exc}") from exc
    except MootError as exc:
        raise click.ClickException(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise click.ClickException(f"cannot reach the worker at {url}: {exc}") from exc

    run = _run_info(started, time.perf_counter() - t0, turn_seconds, backend, model_name, url)
    stats = transcript.stats()
    if console is not None:
        _render_stats(console, stats)
        _render_run(console, run)
    else:
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
            f", too short {stats['quotes_too_short']}"
        )
        click.echo("Run:")
        for label, value in _run_rows(run):
            click.echo(f"  {label}: {value}")
    if out is not None:
        data = {**transcript.to_dict(), "run": run}
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        click.echo(f"Transcript written to {out}")
