# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""gutenkg chat — launch the Streamlit chat UI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

from gutenberg_kg.cli.main import cli


@cli.command("chat")
@click.option("--port", default=8501, show_default=True, help="Streamlit server port.")
@click.option("--address", default="localhost", show_default=True, help="Bind address.")
@click.option(
    "--worker",
    "worker_url",
    default=None,
    help="KGRAG worker URL (sets KGRAG_ENDPOINT, default http://localhost:8000).",
)
def chat_cmd(port: int, address: str, worker_url: str | None) -> None:
    """Launch the Streamlit chat UI (needs the [chat] extra and a running worker).

    Streamlit apps are launched by file path, not module import, so this
    resolves the packaged ``gutenberg_kg/serve/chat.py`` (the ``pages/``
    directory beside it provides the multi-page nav) and execs
    ``streamlit run`` on it.

    :param port: Streamlit server port.
    :param address: Streamlit bind address.
    :param worker_url: Override the KGRAG worker endpoint for this session.
    """
    try:
        import streamlit  # noqa: F401
    except ImportError as exc:
        raise click.ClickException(
            "streamlit is not installed — install with: pip install 'gutenberg-kg[chat]'"
        ) from exc

    app = Path(__file__).resolve().parent.parent / "serve" / "chat.py"
    env = os.environ.copy()
    if worker_url:
        env["KGRAG_ENDPOINT"] = worker_url
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.port",
        str(port),
        "--server.address",
        address,
    ]
    raise SystemExit(subprocess.call(cmd, env=env))
