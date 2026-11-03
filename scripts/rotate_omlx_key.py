#!/usr/bin/env python3
"""Set a new oMLX API key in ~/.omlx/settings.json and docker/.env together.

The worker authenticates to oMLX with VLLM_API_KEY from docker/.env; oMLX checks
it against auth.api_key in its settings. When the two differ, /v1/models returns
401 and the chat app's model dropdown comes up empty. This writes one key to both.

Quit the oMLX app first: it can write its settings back on exit and undo the
change. The key itself is never printed.

Usage:
    python scripts/rotate_omlx_key.py               # generate a random key
    python scripts/rotate_omlx_key.py --key sk-...  # use a key of your own
    python scripts/rotate_omlx_key.py --force       # skip the "oMLX running" check

Each run backs the settings up to settings.json.bak-<UTC timestamp>, so a later
rotation never overwrites the backup of an earlier one.

Afterwards relaunch oMLX, then restart the stack:
    make down && make up
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OMLX_SETTINGS = Path.home() / ".omlx" / "settings.json"
ENV_FILE = REPO / "docker" / ".env"


def omlx_running() -> bool:
    """Return ``True`` if oMLX is serving on its configured port or its app is open.

    The server runs as a ``python3.x`` process (only its argv says omlx-server),
    so the port is the reliable signal; the name check catches the app itself.
    """
    server = json.loads(OMLX_SETTINGS.read_text()).get("server", {})
    host = server.get("host", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    try:
        with socket.create_connection((host, int(server.get("port", 8000))), timeout=1):
            return True
    except OSError:
        pass
    # Match process names, not command lines: -f would match this script itself.
    result = subprocess.run(["pgrep", "-i", "^omlx"], capture_output=True, text=True)
    return result.returncode == 0


def backup_path() -> Path:
    """Return an unused ``settings.json.bak-<UTC timestamp>`` path beside the settings."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017
    path = OMLX_SETTINGS.with_name(f"{OMLX_SETTINGS.name}.bak-{stamp}")
    n = 1
    while path.exists():
        path = OMLX_SETTINGS.with_name(f"{OMLX_SETTINGS.name}.bak-{stamp}-{n}")
        n += 1
    return path


def write_settings(key: str) -> Path:
    """Store ``key`` as ``auth.api_key`` in the oMLX settings and return the backup path."""
    settings = json.loads(OMLX_SETTINGS.read_text())
    settings.setdefault("auth", {})["api_key"] = key
    backup = backup_path()
    shutil.copy2(OMLX_SETTINGS, backup)
    OMLX_SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")
    return backup


def write_env(key: str) -> None:
    """Set ``VLLM_API_KEY`` in docker/.env, appending it if absent."""
    text = ENV_FILE.read_text()
    line = f"VLLM_API_KEY={key}"
    if re.search(r"(?m)^VLLM_API_KEY=", text):
        text = re.sub(r"(?m)^VLLM_API_KEY=.*$", lambda _: line, text)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    ENV_FILE.write_text(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key", help="key to use (default: a random sk-… key)")
    parser.add_argument("--force", action="store_true", help="run even if oMLX is running")
    args = parser.parse_args()

    for path in (OMLX_SETTINGS, ENV_FILE):
        if not path.exists():
            print(f"error: {path} not found", file=sys.stderr)
            return 1
    if omlx_running() and not args.force:
        print("error: oMLX is running; quit it first (or pass --force)", file=sys.stderr)
        return 1

    key = args.key or "sk-" + secrets.token_urlsafe(32)
    backup = write_settings(key)
    write_env(key)
    print(f"New key written to {OMLX_SETTINGS} (backup: {backup.name}) and {ENV_FILE}.")
    print("Next: relaunch oMLX, then restart the stack: make down && make up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
