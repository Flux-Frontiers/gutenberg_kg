#!/usr/bin/env python3
# © 2026 Eric G. Suchanek, PhD -- Flux-Frontiers . SPDX-License-Identifier: Elastic-2.0
"""
Bootstrap a GutenbergKG checkout: check the requirements, install what is
missing, and stop before any long build.

Run it from a fresh clone, with whatever ``python3`` the machine has (stdlib
only; it imports nothing from ``gutenberg_kg`` and needs no ``.venv``)::

    python3 scripts/bootstrap.py --dry-run     # report only, change nothing
    python3 scripts/bootstrap.py               # ask before each install
    python3 scripts/bootstrap.py --yes         # no questions
    make bootstrap DRY_RUN=1                   # same, through make

Steps, in order:

1. Python 3.12 or 3.13 on PATH. Reported only; never installed. Without one,
   steps 5 and 6 are skipped.
2. Poetry 2.x. Installed with ``pipx`` if present, else with the official
   installer, after you confirm (``--yes`` confirms for you). The official
   installer is downloaded and run as Poetry's own docs do it, with no
   checksum; that is why it needs a confirmation and why pipx is tried first.
3. GNU Make, for the build and run targets. Reported only.
4. A container runtime, Docker or Apple ``container``. Docker is reported only;
   with neither present on Apple Silicon and macOS 26 or later,
   ``make setup RUNTIME=apple`` is offered. ``--cli-only`` skips this step.
5. ``poetry install`` with the recommended extras (``--dev`` adds the
   contributor toolchain). Refused while a virtualenv other than ``.venv`` is
   active, because Poetry would install into that one instead.
6. ``gutenkg init``: the spaCy and embedder models.
7. ``docker/.env`` from ``docker/.env.example``. An existing file is never
   touched.
8. Optional LLM and image backends: oMLX, Ollama, OpenAI keys. Reported only.

It ends by printing the next command and does not run it: ``make build-corpus``
takes 30-45 minutes, and ``make pull-worker-image`` skips it.

With ``--dry-run`` nothing is installed, copied or downloaded; each action is
printed as ``would run``. The one command that does run is the read-only
``gutenkg init --check``, and only when the venv already exists.

Exit status:
    0  every requirement is met, or is one this script installs
    1  a requirement is missing that the script cannot or did not install
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
# datetime.UTC is 3.11+, and this runs under whatever python3 the machine has.
_UTC = timezone.utc  # noqa: UP017

# Matches `requires-python = ">=3.12,<3.14"` in pyproject.toml.
PYTHON_MIN = (3, 12)
PYTHON_MAX_EXCLUSIVE = (3, 14)
POETRY_MIN_MAJOR = 2
POETRY_INSTALLER_URL = "https://install.python-poetry.org"

# The CLI install the docs recommend; --dev adds what CI's test job needs.
EXTRAS = "kgdeps viz viz3d mcp"
DEV_ONLY_EXTRAS = ("image", "pov")

# Apple's `container` CLI needs macOS 26.
APPLE_CONTAINER_MIN_MACOS = 26

ENV_FILE = ROOT / "docker" / ".env"
ENV_EXAMPLE = ROOT / "docker" / ".env.example"

# Local probes must not go through an HTTP proxy from the environment.
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def python_ok(version) -> bool:
    """Whether a ``(major, minor, ...)`` version is inside the supported range.

    :param version: A version tuple such as ``sys.version_info``.
    :returns: True for 3.12 and 3.13.
    """
    return PYTHON_MIN <= tuple(version[:2]) < PYTHON_MAX_EXCLUSIVE


def parse_version(text: str):
    """Pull the first ``X.Y.Z`` out of a ``--version`` line.

    :param text: Output such as ``Poetry (version 2.3.2)``.
    :returns: ``(major, minor, patch)``, or None when there is no version.
    """
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(g) for g in m.groups()) if m else None


def dev_extras(extras: str) -> str:
    """Add the extras the contributor toolchain needs to the chosen ones.

    :param extras: Space-separated Poetry extras.
    :returns: The same extras plus ``image`` and ``pov``, without duplicates.
    """
    merged = extras.split()
    merged += [e for e in DEV_ONLY_EXTRAS if e not in merged]
    return " ".join(merged)


def macos_major() -> int:
    """The running macOS major version.

    :returns: For example 26, or 0 when not on macOS.
    """
    try:
        return int(platform.mac_ver()[0].split(".")[0])
    except ValueError:
        return 0


def read_dotenv(path: Path) -> dict:
    """Read ``NAME=value`` lines from an env file.

    Skips comments, accepts an ``export`` prefix, unquotes quoted values and
    drops a trailing ``# comment`` from an unquoted one.

    :param path: The env file; a missing file reads as empty.
    :returns: Mapping of name to value.
    """
    values: dict = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ("'", '"'):
            end = value.find(value[0], 1)
            value = value[1:end] if end > 0 else value[1:]
        elif value.startswith("#"):
            value = ""
        else:
            value = value.split(" #", 1)[0].strip()
        values[name.strip()] = value
    return values


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """Whether something accepts TCP connections on a local port.

    :param port: Port to probe.
    :param host: Host to probe.
    :param timeout: Seconds to wait for the connection.
    :returns: True if the connection succeeded.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_status(url: str, timeout: float = 1.0):
    """The HTTP status a local URL answers with, bypassing any proxy.

    :param url: URL to GET.
    :param timeout: Seconds to wait.
    :returns: The status code, or None when nothing answered over HTTP.
    """
    try:
        with _LOCAL_OPENER.open(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError, ValueError):
        return None


# ANSI colors, used only on a terminal (main() decides; NO_COLOR turns them off).
_USE_COLOR = False
_TAG_COLORS = {
    "ok": "32",
    "warn": "33",
    "missing": "31;1",
    "fail": "31;1",
    "run": "36",
    "would run": "36",
    "skip": "2",
    "info": "2",
}
HEADER_WIDTH = 72
# Below this much free disk, warn: the corpus bundle, image and SDXL weights
# together take tens of GB.
LOW_DISK_GB = 20


def paint(text: str, code: str) -> str:
    """Wrap text in an ANSI color when color is on.

    :param text: The text.
    :param code: SGR parameters, such as ``32`` or ``1``.
    :returns: The text, colored or unchanged.
    """
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def say(tag: str, msg: str) -> None:
    """Print one status line.

    :param tag: Short status word such as ``ok`` or ``missing``.
    :param msg: The message.
    """
    print(f"  [{paint(tag, _TAG_COLORS.get(tag, '0'))}] {msg}")


def _capture(cmd: list) -> str:
    """Run a quick read-only command and return its stripped output.

    :param cmd: Argument vector.
    :returns: Its stdout, or ``""`` when it is missing, fails or hangs.
    """
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _sysctl(name: str) -> str:
    """Read one macOS sysctl value.

    :param name: The sysctl key, such as ``hw.memsize``.
    :returns: Its value, or ``""``.
    """
    # /usr/sbin is often missing from a trimmed PATH (cron, some IDE shells).
    return _capture([shutil.which("sysctl") or "/usr/sbin/sysctl", "-n", name])


def project_version() -> str:
    """The version in pyproject.toml, read without tomllib (Python 3.11+ only).

    :returns: For example ``1.31.0``, or ``unknown``.
    """
    try:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else "unknown"


def git_provenance() -> str:
    """Branch, short commit and whether the checkout has local changes.

    :returns: For example ``main @ 5724889``, ``... (modified)``, or ``not a git checkout``.
    """
    git = ["git", "-C", str(ROOT)]
    sha = _capture(git + ["rev-parse", "--short", "HEAD"])
    if not sha:
        return "not a git checkout"
    branch = _capture(git + ["rev-parse", "--abbrev-ref", "HEAD"]) or "?"
    dirty = " (modified)" if _capture(git + ["status", "--porcelain"]) else ""
    return f"{branch} @ {sha}{dirty}"


def os_label() -> str:
    """The operating system and architecture.

    :returns: For example ``macOS 26.1 (arm64)``.
    """
    system = platform.system()
    if system == "Darwin":
        name = f"macOS {platform.mac_ver()[0]}"
    elif system == "Linux":
        name = "Linux"
        try:
            for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
                if line.startswith("PRETTY_NAME="):
                    name = line.partition("=")[2].strip('"')
        except OSError:
            pass
    else:
        name = platform.platform()
    return f"{name} ({platform.machine()})"


def cpu_label() -> str:
    """The CPU model and core count.

    :returns: For example ``Apple M5 Max, 18 cores``.
    """
    model = ""
    if platform.system() == "Darwin":
        model = _sysctl("machdep.cpu.brand_string")
    elif platform.system() == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("model name"):
                    model = line.partition(":")[2].strip()
                    break
        except OSError:
            pass
    model = model or platform.processor() or "unknown CPU"
    return f"{model}, {os.cpu_count() or '?'} cores"


def memory_gb():
    """Installed memory in GB.

    :returns: GB as an int, or None when it cannot be read.
    """
    if platform.system() == "Darwin":
        raw = _sysctl("hw.memsize")
        return int(raw) // 2**30 if raw.isdigit() else None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 2**20
    except (OSError, ValueError, IndexError):
        pass
    return None


def header_lines(*, dry_run: bool, started) -> list:
    """The banner: what is being bootstrapped, where, when and on what.

    :param dry_run: Whether this is a dry run.
    :param started: Start time, an aware ``datetime``.
    :returns: Lines to print.
    """
    title = f"GutenbergKG bootstrap  v{project_version()}"
    badge = "DRY RUN" if dry_run else "INSTALL"
    pad = HEADER_WIDTH - 4 - len(title) - len(badge)
    rule = "+" + "-" * (HEADER_WIDTH - 2) + "+"
    banner = f"| {paint(title, '1')}{' ' * pad}{paint(badge, '33;1' if dry_run else '32;1')} |"

    utc = started.astimezone(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    local = started.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    mem = memory_gb()
    free_gb = shutil.disk_usage(ROOT).free // 2**30
    disk = f"{free_gb} GB free on the repo's volume"
    if free_gb < LOW_DISK_GB:
        disk += paint(f"  (low: the full stack wants {LOW_DISK_GB}+ GB)", "33")
    v = sys.version_info
    rows = [
        ("started", f"{utc}  (local {local})"),
        ("repo", f"{ROOT}"),
        ("git", git_provenance()),
        (
            "host",
            f"{socket.gethostname()}  (user {os.environ.get('USER') or os.environ.get('USERNAME') or '?'})",
        ),
        ("os", os_label()),
        ("cpu", cpu_label()),
        ("memory", f"{mem} GB" if mem is not None else "unknown"),
        ("disk", disk),
        ("python", f"{v[0]}.{v[1]}.{v[2]}  {sys.executable}"),
        ("command", shlex.join(["python3", "scripts/bootstrap.py", *sys.argv[1:]])),
    ]
    return [rule, banner, rule] + [f"  {paint(f'{k:<8}', '2')} {val}" for k, val in rows] + [""]


class Bootstrap:
    """One bootstrap run; records the requirements it could not satisfy."""

    def __init__(self, *, dry_run: bool, assume_yes: bool, dev: bool, cli_only: bool, extras: str):
        """Set the run mode.

        :param dry_run: Report only; run no install and write no file.
        :param assume_yes: Answer yes to every install question.
        :param dev: Install the contributor toolchain as well.
        :param cli_only: Skip the container runtime check.
        :param extras: Space-separated Poetry extras for ``poetry install``.
        """
        self.dry_run = dry_run
        self.assume_yes = assume_yes
        self.dev = dev
        self.cli_only = cli_only
        self.extras = extras
        self.blocked: list = []
        self.python_ready = False
        self.poetry_ready = False

    def confirm(self, question: str) -> bool:
        """Ask before an install; ``--yes`` answers yes, a non-terminal answers no.

        :param question: What is about to happen.
        :returns: True to go ahead.
        """
        if self.assume_yes or self.dry_run:
            return True
        if not sys.stdin.isatty():
            say("skip", f"{question} -- not a terminal; re-run with --yes to allow it")
            return False
        return input(f"  ? {question} [y/N] ").strip().lower() in ("y", "yes")

    def act(self, cmd: list) -> bool:
        """Run a command in the repo root, or print it under ``--dry-run``.

        :param cmd: Argument vector.
        :returns: True if it ran and exited 0, or if this is a dry run.
        """
        text = shlex.join(cmd)
        if self.dry_run:
            say("would run", text)
            return True
        say("run", text)
        try:
            return subprocess.run(cmd, cwd=ROOT, check=False).returncode == 0
        except OSError as exc:
            say("fail", f"{cmd[0]}: {exc.strerror or exc}")
            return False

    def block(self, what: str, hint: str) -> None:
        """Record an unmet hard requirement and say how to fix it.

        :param what: The requirement.
        :param hint: The fix, as one line.
        """
        self.blocked.append(what)
        say("missing", f"{what}. {hint}")

    # -- steps --------------------------------------------------------

    def check_python(self) -> None:
        """Step 1: a supported interpreter must be on PATH."""
        v = sys.version_info
        if python_ok(v):
            say("ok", f"Python {v[0]}.{v[1]}.{v[2]} ({sys.executable})")
            self.python_ready = True
            return
        for name in ("python3.13", "python3.12"):
            found = shutil.which(name)
            if found:
                say("ok", f"{name} at {found} (this python3 is {v[0]}.{v[1]}; Poetry will use it)")
                self.python_ready = True
                return
        # uv's standalone CPython lands python3.12 in ~/.local/bin, where the
        # search above finds it, and does not depend on Homebrew.
        hint = "Install 3.12 or 3.13: uv python install 3.12"
        if not shutil.which("uv"):
            hint += " (uv: https://docs.astral.sh/uv/)"
            if platform.system() == "Darwin":
                hint += ", or brew install python@3.12"
        self.block(f"Python {v[0]}.{v[1]} is outside >=3.12,<3.14", hint)

    def check_poetry(self) -> None:
        """Step 2: Poetry 2.x, installed if missing and allowed."""
        exe = shutil.which("poetry")
        if exe:
            try:
                out = subprocess.run(
                    [exe, "--version"], capture_output=True, text=True, check=False, timeout=60
                ).stdout
            except (subprocess.TimeoutExpired, OSError):
                out = ""
            ver = parse_version(out)
            if ver is None:
                self.block(f"Poetry at {exe} did not report its version", "Check: poetry --version")
            elif ver[0] < POETRY_MIN_MAJOR:
                self.block(
                    f"Poetry {'.'.join(map(str, ver))} is older than {POETRY_MIN_MAJOR}.x",
                    "Upgrade it: pipx upgrade poetry, or poetry self update",
                )
            else:
                say("ok", f"Poetry {'.'.join(map(str, ver))} ({exe})")
                self.poetry_ready = True
            return
        say("missing", "Poetry is not installed")
        if not self.confirm("Install Poetry now?"):
            self.block("Poetry", f"Install it from {POETRY_INSTALLER_URL}")
            return
        if shutil.which("pipx"):
            ok = self.act(["pipx", "install", "poetry"])
        elif self.dry_run:
            say("would run", f"curl -sSL {POETRY_INSTALLER_URL} | {sys.executable} -")
            ok = True
        else:
            ok = self._run_poetry_installer()
        if not ok:
            self.block("Poetry", f"The install failed; see {POETRY_INSTALLER_URL}")
            return
        # Both installers put the binary in ~/.local/bin, which may not be on PATH yet.
        local_bin = str(Path.home() / ".local" / "bin")
        if not self.dry_run and local_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")
            say("warn", f"add {local_bin} to your PATH so new shells find poetry")
        self.poetry_ready = self.dry_run or bool(shutil.which("poetry"))
        if not self.poetry_ready:
            self.block("Poetry", "Installed, but it is not on PATH")

    def _run_poetry_installer(self) -> bool:
        """Download Poetry's official installer and run it with this interpreter.

        :returns: True if the installer ran and exited 0.
        """
        say("run", f"download {POETRY_INSTALLER_URL} and run it with {sys.executable}")
        try:
            with urllib.request.urlopen(POETRY_INSTALLER_URL, timeout=30) as resp:  # noqa: S310
                script = resp.read()
        except (urllib.error.URLError, OSError) as exc:
            say("fail", f"could not download the installer: {exc}")
            if "CERTIFICATE" in str(exc).upper() and platform.system() == "Darwin":
                say(
                    "info",
                    "a python.org Python needs its certificates: run 'Install Certificates.command'"
                    " in its /Applications/Python 3.x folder",
                )
            return False
        try:
            return subprocess.run([sys.executable, "-"], input=script, check=False).returncode == 0
        except OSError as exc:
            say("fail", f"could not run the installer: {exc}")
            return False

    def check_make(self) -> None:
        """Step 3: GNU Make, needed only for the build and run targets."""
        found = shutil.which("make")
        if found:
            say("ok", f"make ({found})")
        else:
            hint = "xcode-select --install" if platform.system() == "Darwin" else "install make"
            say("warn", f"make not found; the build/run targets need it ({hint})")

    def check_containers(self) -> None:
        """Step 4: Docker or Apple ``container``, for the container workflow."""
        docker, apple = shutil.which("docker"), shutil.which("container")
        if docker:
            try:
                up = subprocess.run(
                    [docker, "info"], capture_output=True, check=False, timeout=20
                ).returncode
            except subprocess.TimeoutExpired:
                say(
                    "warn",
                    "docker info gave no answer in 20 s; Docker Desktop may be wedged"
                    " (quit it, pkill -x com.docker.backend, reopen it)",
                )
            except OSError as exc:
                say("warn", f"could not run docker: {exc}")
            else:
                if up == 0:
                    say("ok", f"Docker ({docker}), daemon running")
                else:
                    say(
                        "warn",
                        "Docker is installed but its daemon is not running; start Docker Desktop",
                    )
        if apple:
            say("ok", f"Apple container CLI ({apple})")
        if docker or apple:
            return
        say("warn", "no container runtime; only the container workflow needs one")
        if (
            platform.system() == "Darwin"
            and platform.machine() == "arm64"
            and macos_major() >= APPLE_CONTAINER_MIN_MACOS
        ):
            if self.confirm("Install Apple's container CLI (make setup RUNTIME=apple)?"):
                self.act(["make", "setup", "RUNTIME=apple"])
        else:
            say(
                "warn",
                "install Docker Engine or Docker Desktop: https://docs.docker.com/get-docker/"
                f" (Apple's container CLI needs Apple Silicon and macOS {APPLE_CONTAINER_MIN_MACOS})",
            )

    def foreign_venv(self):
        """The active virtualenv, when it is not this repo's ``.venv``.

        :returns: Its path, or None when none is active or it is ``.venv``.
        """
        active = os.environ.get("VIRTUAL_ENV")
        if not active or Path(active).resolve() == VENV.resolve():
            return None
        return active

    def install_deps(self) -> None:
        """Step 5: ``poetry install``; idempotent, so it always runs."""
        if not self.python_ready:
            say("skip", "poetry install -- no supported Python")
            return
        if not self.poetry_ready:
            say("skip", "poetry install -- Poetry is not available")
            return
        active = self.foreign_venv()
        if active:
            self.block(
                f"another virtualenv is active ({active})",
                "Poetry would install into it instead of .venv; run 'deactivate' and re-run",
            )
            return
        if self.dev:
            cmd = ["poetry", "install", "--with", "dev", "--extras", dev_extras(self.extras)]
        else:
            cmd = ["poetry", "install", "--extras", self.extras]
        if not self.act(cmd):
            self.block("poetry install", "It failed; fix the error above and re-run")

    def fetch_models(self) -> None:
        """Step 6: ``gutenkg init`` for the spaCy and embedder models."""
        gutenkg = VENV / ("Scripts" if os.name == "nt" else "bin") / "gutenkg"
        if self.dry_run and gutenkg.exists():
            # Read-only: reports each model's status and downloads nothing.
            say("run", ".venv/bin/gutenkg init --check")
            subprocess.run([str(gutenkg), "init", "--check"], cwd=ROOT, check=False)
            return
        if not self.python_ready:
            say("skip", "gutenkg init -- no supported Python")
            return
        if not self.poetry_ready:
            say("skip", "gutenkg init -- Poetry is not available")
            return
        if "poetry install" in self.blocked or self.foreign_venv():
            say("skip", "gutenkg init -- the Python dependencies are not installed")
            return
        if not self.act(["poetry", "run", "gutenkg", "init"]):
            self.block("gutenkg init", "A model download failed; re-run, or run gutenkg init")

    def make_env_file(self) -> None:
        """Step 7: seed ``docker/.env`` from the example, never overwriting."""
        if ENV_FILE.exists():
            say("ok", "docker/.env exists (left unchanged)")
        elif self.dry_run:
            say("would run", "cp docker/.env.example docker/.env")
        else:
            shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
            say("run", "cp docker/.env.example docker/.env")

    def _probe_llm(self, name: str, port: int, path: str, key_hint: str) -> bool:
        """Report one local OpenAI-compatible server.

        :param name: Server name for the message.
        :param port: Local port it listens on by default.
        :param path: A GET path the server answers.
        :param key_hint: What to do when it answers 401.
        :returns: True when the server is there (answering, or asking for a key).
        """
        if not port_open(port):
            say("info", f"no {name} on :{port}")
            return False
        code = http_status(f"http://127.0.0.1:{port}{path}")
        if code == 200:
            say("ok", f"{name} answering on :{port}")
            return True
        if code == 401:
            say("warn", f"{name} on :{port} wants an API key; {key_hint}")
            return True
        say("warn", f"something on :{port} does not answer like {name} (GET {path} -> {code})")
        return False

    def probe_backends(self) -> None:
        """Step 8: report which synthesis and image backends are usable."""
        dotenv = read_dotenv(ENV_FILE)

        def setting(name: str) -> str:
            return os.environ.get(name) or dotenv.get(name, "")

        omlx = self._probe_llm(
            "oMLX", 8080, "/v1/models", "set VLLM_API_KEY in docker/.env to its key"
        )
        placeholder = read_dotenv(ENV_EXAMPLE).get("VLLM_API_KEY", "")
        if placeholder and setting("VLLM_API_KEY") == placeholder:
            say(
                "warn",
                "VLLM_API_KEY is still the example placeholder; set your oMLX key"
                " (~/.omlx/settings.json, auth.api_key) or clear it",
            )
        ollama = self._probe_llm("Ollama", 11434, "/api/tags", "check its configuration")

        synth_key = bool(setting("OPENAI_API_KEY") or setting("SYNTH_API_KEY"))
        image_key = bool(setting("OPENAI_API_KEY") or setting("IMAGE_API_KEY"))
        if synth_key and image_key:
            say("ok", "OpenAI key set: worker and chat UI get synthesis and gpt-image-1 images")
        elif synth_key:
            say(
                "ok", "OpenAI synthesis key set (no image key: set OPENAI_API_KEY or IMAGE_API_KEY)"
            )
        elif image_key:
            say("ok", "IMAGE_API_KEY set: gpt-image-1 images only; synthesis needs OPENAI_API_KEY")
        else:
            say("info", "no OPENAI_API_KEY: set it in docker/.env for cloud synthesis and images")
        if image_key:
            say("info", "`gutenkg imagine` (CLI) still needs a local image server")
        if not (omlx or ollama or synth_key):
            say("info", "no synthesis backend; querying the corpus works without one")
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            say("info", "local images: make image-server (FLUX) or make sdxl-server")
        elif os.name == "nt":
            # `make sdxl-server` assumes a POSIX venv layout and a POSIX shell.
            say(
                "info", "local images: the SDXL server; see docs/INSTALLATION.md, 'SDXL on Windows'"
            )
        else:
            say("info", "local images: make sdxl-server (FLUX needs Apple Silicon or CUDA 13)")

    def run(self) -> int:
        """Run every step and print the summary.

        :returns: The process exit status.
        """
        started = datetime.now(_UTC)
        clock = time.monotonic()
        print("\n".join(header_lines(dry_run=self.dry_run, started=started)))
        if self.dry_run:
            print(paint("Dry run: nothing will be installed, copied or downloaded.\n", "33"))
        steps = [
            ("1/8 Python", self.check_python),
            ("2/8 Poetry", self.check_poetry),
            ("3/8 Make", self.check_make),
            ("4/8 Container runtime", None if self.cli_only else self.check_containers),
            ("5/8 Python dependencies", self.install_deps),
            ("6/8 Local models", self.fetch_models),
            ("7/8 docker/.env", self.make_env_file),
            ("8/8 Optional backends", self.probe_backends),
        ]
        for title, step in steps:
            print(paint(title, "1"))
            if step is None:
                say("skip", "--cli-only")
            else:
                step()
        print()
        finished = datetime.now(_UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        took = f"finished {finished}, took {time.monotonic() - clock:.1f} s"
        if self.blocked:
            print(paint("Blocked: " + "; ".join(self.blocked), "31;1"))
            print(paint(took, "2"))
            return 1
        done = "Requirements are met." if not self.dry_run else "Nothing blocks a real run."
        print(paint(done, "32;1"))
        print(paint(took, "2"))
        print(
            "\nNext (not run for you):\n"
            "  make pull-worker-image && make up      fastest: the published image\n"
            "  make build-corpus && make build        build locally, 30-45 min\n"
            "  gutenkg ingest --force-build           CLI only, no container"
        )
        return 0


def main(argv=None) -> int:
    """Parse arguments and run the bootstrap.

    :param argv: Argument list; defaults to ``sys.argv[1:]``.
    :returns: The process exit status.
    """
    p = argparse.ArgumentParser(description="Check and install what GutenbergKG needs.")
    p.add_argument("--dry-run", action="store_true", help="report only; change nothing")
    p.add_argument("-y", "--yes", action="store_true", help="answer yes to every install question")
    p.add_argument(
        "--dev",
        action="store_true",
        help="also install the contributor toolchain (adds the image and pov extras)",
    )
    p.add_argument("--cli-only", action="store_true", help="skip the container runtime check")
    p.add_argument("--extras", default=EXTRAS, help=f"Poetry extras (default: {EXTRAS!r})")
    args = p.parse_args(argv)
    # Keep our lines in order with the output of the commands we run.
    sys.stdout.reconfigure(line_buffering=True)
    global _USE_COLOR
    _USE_COLOR = (
        sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    )
    return Bootstrap(
        dry_run=args.dry_run,
        assume_yes=args.yes,
        dev=args.dev,
        cli_only=args.cli_only,
        extras=args.extras,
    ).run()


if __name__ == "__main__":
    sys.exit(main())
