#!/usr/bin/env python3
# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Set up the local LLM that fits this Mac, and point the worker at it.

Reads the tier table in scripts/model_tiers.json, picks a tier from this Mac's
memory (or the one named with --tier), and then:

  1. downloads the tier's model into ~/.omlx/models/<org>/<name> with `hf`
     (resumable; a model already there costs one quick check);
  2. asks oMLX to rescan its models and reads back the id it serves;
  3. sends one short chat request, so a model oMLX refuses to load fails here
     with oMLX's own message, and docker/.env is left as it was;
  4. writes VLLM_MODEL, MOOT_MODEL and IMAGE_IDLE_UNLOAD_S to docker/.env,
     after backing it up to docker/.env.bak-<UTC timestamp>.

`make models` runs this, then pulls the worker image. Docker's memory and
oMLX's memory guard are reported, never changed. The oMLX API key is read from
~/.omlx/settings.json and never printed.

Usage:
    python scripts/setup_models.py                   # tier from this Mac's RAM
    python scripts/setup_models.py --tier medium     # pick a tier
    python scripts/setup_models.py --model Qwen/Qwen3-8B-MLX-4bit   # any HF repo
    python scripts/setup_models.py --images openai   # OpenAI renders images
    python scripts/setup_models.py --dry-run         # say what would happen

Afterwards restart the stack: make down && make up
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TIERS_FILE = REPO / "scripts" / "model_tiers.json"
ENV_FILE = REPO / "docker" / ".env"
ENV_EXAMPLE = REPO / "docker" / ".env.example"
OMLX_HOME = Path.home() / ".omlx"
OMLX_SETTINGS = OMLX_HOME / "settings.json"
OMLX_MODELS = OMLX_HOME / "models"
IMAGE_AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / "local.gutenkg-image.plist"

#: Above this, a Docker VM on a Mac of 24 GB or less leaves oMLX too little room.
DOCKER_VM_WARN_GB = 4.5


def load_tiers(path: Path = TIERS_FILE) -> dict:
    """Return the parsed tier table."""
    return json.loads(path.read_text())


def tier_order(table: dict) -> list[str]:
    """Return the tier names from smallest to largest memory."""
    tiers = table["tiers"]
    return sorted(tiers, key=lambda t: tiers[t]["max_ram_gb"] or float("inf"))


def pick_tier(table: dict, ram_gb: float) -> str:
    """Return the smallest tier whose ``max_ram_gb`` covers ``ram_gb``.

    A tier with ``max_ram_gb`` null has no ceiling, so it takes every larger Mac.
    """
    for name in tier_order(table):
        ceiling = table["tiers"][name]["max_ram_gb"]
        if ceiling is None or ram_gb <= ceiling + 0.5:
            return name
    return tier_order(table)[-1]


def smaller_tier(table: dict, name: str) -> str | None:
    """Return the tier below ``name``, or ``None`` at the bottom."""
    order = tier_order(table)
    i = order.index(name)
    return order[i - 1] if i > 0 else None


def ram_gb() -> float:
    """Return this Mac's physical memory in GiB."""
    out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
    return int(out.stdout.strip()) / 2**30


def set_env_keys(text: str, values: dict[str, str]) -> str:
    """Return ``text`` with each ``KEY=value`` set, replacing or appending lines."""
    for key, value in values.items():
        line = f"{key}={value}"
        pattern = rf"(?m)^{re.escape(key)}=.*$"
        if re.search(pattern, text):
            text = re.sub(pattern, lambda _, line=line: line, text)
        else:
            text = text.rstrip("\n") + f"\n{line}\n"
    return text


def backup_path(path: Path) -> Path:
    """Return an unused ``<name>.bak-<UTC timestamp>`` path beside ``path``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017
    candidate = path.with_name(f"{path.name}.bak-{stamp}")
    n = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak-{stamp}-{n}")
        n += 1
    return candidate


def resolve_served_id(served: list[str], wanted: str) -> str | None:
    """Return the id oMLX serves for ``wanted``.

    oMLX names a model after its folder, and some versions prefix the org
    (``Jundot--Qwen3.6-…``), so an id ending in ``wanted`` also matches.
    """
    if wanted in served:
        return wanted
    for sid in served:
        if sid.endswith(f"--{wanted}") or sid.endswith(f"/{wanted}"):
            return sid
    return None


class OMLX:
    """The few oMLX calls this script makes, authenticated from its settings."""

    def __init__(self, settings_path: Path | None = None):
        settings = json.loads((settings_path or OMLX_SETTINGS).read_text())
        server = settings.get("server", {})
        host = server.get("host", "127.0.0.1")
        host = "127.0.0.1" if host in ("0.0.0.0", "") else host
        # 8000 is oMLX's own default; the docs have it moved to 8080.
        self.base = f"http://{host}:{int(server.get('port', 8000))}"
        self._key = (settings.get("auth") or {}).get("api_key") or ""
        self.guard_tier = (settings.get("memory") or {}).get("memory_guard_tier", "?")

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 30):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self._key:
            req.add_header("Authorization", f"Bearer {self._key}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — local oMLX
            return json.loads(resp.read() or b"{}")

    def reachable(self) -> bool:
        try:
            self.models()
            return True
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def reload(self) -> bool:
        """Ask oMLX to rescan its model folders; ``False`` if the route is missing."""
        try:
            self._call("POST", "/admin/api/reload", {}, timeout=120)
            return True
        except urllib.error.HTTPError:
            return False

    def models(self) -> list[str]:
        return [m["id"] for m in self._call("GET", "/v1/models").get("data", [])]

    def smoke_test(self, model: str) -> str | None:
        """Send one tiny chat request; return ``None`` on success, else oMLX's error."""
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with the word ready."}],
            "max_tokens": 8,
        }
        try:
            self._call("POST", "/v1/chat/completions", body, timeout=600)
            return None
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read())["error"]["message"]
            except (ValueError, KeyError, TypeError):
                return f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError) as exc:
            return str(exc)


def find_hf() -> str | None:
    """Return the `hf` CLI: the repo's .venv first, then PATH."""
    local = REPO / ".venv" / "bin" / "hf"
    return str(local) if local.exists() else shutil.which("hf")


def has_weights(dest: Path) -> bool:
    return any(dest.glob("*.safetensors"))


def plist_idle_unload(text: str) -> str | None:
    """Return the launch agent's ``IMAGE_IDLE_UNLOAD_S`` value, or ``None`` if unset."""
    m = re.search(r"<key>IMAGE_IDLE_UNLOAD_S</key>\s*<string>([^<]*)</string>", text)
    return m.group(1) if m else None


def docker_vm_gb() -> float | None:
    """Return the Docker VM's memory in GiB, or ``None`` if Docker is not answering."""
    try:
        out = subprocess.run(
            ["docker", "info", "--format", "{{.MemTotal}}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return int(out.stdout.strip()) / 2**30 if out.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def main(argv: list[str] | None = None) -> int:
    table = load_tiers()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tier", choices=tier_order(table), help="tier to set up (default: from RAM)"
    )
    parser.add_argument("--model", help="a Hugging Face MLX repo to use instead of the tier's")
    parser.add_argument(
        "--images",
        choices=["local", "openai"],
        default="local",
        help="where images are rendered (openai needs OPENAI_API_KEY in docker/.env)",
    )
    parser.add_argument("--dry-run", action="store_true", help="report the plan, change nothing")
    args = parser.parse_args(argv)
    # Line by line, so this script's output stays in order with `hf download`'s.
    sys.stdout.reconfigure(line_buffering=True)

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        print("error: this sets up oMLX models, which need an Apple Silicon Mac.", file=sys.stderr)
        print("  On other hosts use Ollama or OpenAI; see docs/INSTALLATION.md.", file=sys.stderr)
        return 1

    ram = ram_gb()
    name = args.tier or pick_tier(table, ram)
    tier = dict(table["tiers"][name])
    why = "--tier" if args.tier else f"{ram:.0f} GB of memory"
    if args.model:
        tier["llm_repo"] = args.model
        tier["llm_id"] = args.model.rsplit("/", 1)[-1]
        tier["moot_model"] = tier["llm_id"]
        tier["llm_gb"] = None
    print(f"Tier: {name} ({why}); model {tier['llm_repo']} ({tier['status']})")

    if not OMLX_SETTINGS.exists():
        print(
            f"error: {OMLX_SETTINGS} not found. Install and start oMLX first (https://omlx.ai).",
            file=sys.stderr,
        )
        return 1
    hf = find_hf()
    if hf is None:
        print(
            "error: the `hf` CLI is missing. Run `make setup`, or `pip install huggingface_hub`.",
            file=sys.stderr,
        )
        return 1

    org, _, base = tier["llm_repo"].rpartition("/")
    dest = OMLX_MODELS / (org or "local") / base
    env_values = {
        "VLLM_MODEL": tier["llm_id"],
        "MOOT_MODEL": tier["moot_model"] or "",
        "IMAGE_IDLE_UNLOAD_S": str(tier["image_idle_unload_s"]),
    }
    if args.images == "openai":
        env_values["WORKER_IMAGE_BACKEND"] = "openai"

    # oMLX may already serve the model from elsewhere (the Hugging Face cache,
    # under an org-prefixed id); then there is nothing to download.
    omlx = OMLX()
    online = omlx.reachable()
    found = resolve_served_id(omlx.models(), tier["llm_id"]) if online else None

    if args.dry_run:
        if found:
            state = f"already served by oMLX as {found}"
            env_values["VLLM_MODEL"] = found
            if tier["moot_model"] == tier["llm_id"]:
                env_values["MOOT_MODEL"] = found
        elif has_weights(dest):
            state = "present"
        else:
            state = f"to download (~{tier['llm_gb'] or '?'} GB)"
        print(f"  model: {dest} ({state})")
        for k, v in env_values.items():
            print(f"  docker/.env: {k}={v}")
        print("Dry run: nothing changed.")
        return 0

    # 1. Download, unless oMLX already serves the model.
    if found:
        print(f"oMLX already serves {found}; skipping the download.")
    else:
        if not has_weights(dest) and tier["llm_gb"]:
            free_gb = shutil.disk_usage(OMLX_HOME).free / 1e9
            if free_gb < tier["llm_gb"] * 1.1:
                print(
                    f"error: {free_gb:.1f} GB free; {tier['llm_repo']} needs about {tier['llm_gb']} GB.",
                    file=sys.stderr,
                )
                return 1
        print(f"Downloading into {dest} (resumes; quick if already there) ...")
        cmd = [hf, "download", tier["llm_repo"], "--local-dir", str(dest)]
        if subprocess.run(cmd).returncode != 0:
            print(f"error: download of {tier['llm_repo']} failed.", file=sys.stderr)
            return 1

    # 2. Rescan and resolve the served id.
    served_id = tier["llm_id"]
    if online:
        if not found:
            if not omlx.reload():
                print("note: oMLX has no rescan route; if the model is not listed, restart oMLX.")
            found = resolve_served_id(omlx.models(), tier["llm_id"])
        if found is None:
            print(
                f"error: oMLX does not list {tier['llm_id']} after the rescan. Restart oMLX and re-run.",
                file=sys.stderr,
            )
            return 1
        served_id = found
        if tier["moot_model"] == tier["llm_id"]:
            env_values["MOOT_MODEL"] = served_id
        env_values["VLLM_MODEL"] = served_id
    else:
        print(
            f"note: oMLX is not answering at {omlx.base}; start it, then re-run to test the model."
        )

    # 3. Test before writing, so a model oMLX refuses never becomes the default.
    if online:
        print(f"Testing {served_id} on oMLX ...")
        err = omlx.smoke_test(served_id)
        if err:
            print(f"error: oMLX could not run {served_id}:\n  {err}", file=sys.stderr)
            lower = smaller_tier(table, name)
            if lower:
                print(
                    f"  Free memory (see below), or try a smaller tier: make models TIER={lower}",
                    file=sys.stderr,
                )
            print("docker/.env was not changed.", file=sys.stderr)
            report_memory(ram, omlx)
            return 1
        print("  ok")

    # 4. Write docker/.env.
    if not ENV_FILE.exists():
        shutil.copy2(ENV_EXAMPLE, ENV_FILE)
        print(
            f"Created {ENV_FILE} from .env.example; set VLLM_API_KEY in it (scripts/rotate_omlx_key.py)."
        )
    old = ENV_FILE.read_text()
    new = set_env_keys(old, env_values)
    if new != old:
        backup = backup_path(ENV_FILE)
        shutil.copy2(ENV_FILE, backup)
        ENV_FILE.write_text(new)
        print(f"Updated docker/.env (backup: {backup.name}):")
    else:
        print("docker/.env already matches:")
    for k, v in env_values.items():
        print(f"  {k}={v}")

    report_memory(ram, omlx)
    if IMAGE_AGENT_PLIST.exists() and plist_idle_unload(IMAGE_AGENT_PLIST.read_text()) != str(
        tier["image_idle_unload_s"]
    ):
        print(
            "The FLUX launch agent has another idle-unload setting: run `make image-agent-install`."
        )
    print("Next: make down && make up")
    return 0


def report_memory(ram: float, omlx: OMLX) -> None:
    """Print the memory settings this script leaves alone."""
    vm = docker_vm_gb()
    if vm is not None:
        print(f"Docker VM memory: {vm:.1f} GB")
        if ram <= 24.5 and vm > DOCKER_VM_WARN_GB:
            print(
                f"  On a {ram:.0f} GB Mac, lower it to about 4 GB "
                "(Docker Desktop > Settings > Resources): the VM keeps what it has used."
            )
    print(f"oMLX memory guard: {omlx.guard_tier} (unchanged)")


if __name__ == "__main__":
    sys.exit(main())
