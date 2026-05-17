#!/usr/bin/env python3
"""
build_kg.py — GutenbergKG Volume Builder

Builds GutenbergKG DocKG indices inside a RunPod pod and syncs
them to the Network Volume.

Usage
-----
  # Full build from scratch (first run)
  python build_kg.py

  # Rebuild indices only (repos + venv already present)
  python build_kg.py --rebuild-only

  # Skip corpus download; ingest from existing files
  python build_kg.py --skip-download

  # Custom destination and genres
  python build_kg.py --dest /data --genres philosophy science

  # Custom git branch
  python build_kg.py --branch main
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_RED = "\033[31m"


def _c(color: str, text: str) -> str:
    return f"{color}{text}{_RESET}" if sys.stdout.isatty() else text


def info(msg: str) -> None:
    print(_c(_CYAN, f"==> {msg}"), flush=True)


def step(msg: str) -> None:
    print(_c(_GREEN, f"    {msg}"), flush=True)


def warn(msg: str) -> None:
    print(_c(_YELLOW, f"    WARNING: {msg}"), flush=True)


def error(msg: str) -> None:
    print(_c(_RED, f"ERROR: {msg}"), file=sys.stderr, flush=True)


def blank() -> None:
    print(flush=True)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def run(
    cmd: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict | None = None,
    prefix: str = "    ",
    check: bool = True,
) -> int:
    """Run a command, streaming output line-by-line."""
    proc = subprocess.Popen(
        [str(c) for c in cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=env or os.environ.copy(),
        text=True,
        errors="replace",
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\r\n")
        if line:
            print(f"{prefix}{line}", flush=True)
    rc = proc.wait()
    if check and rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)
    return rc


def _du(path: Path) -> str:
    try:
        out = subprocess.run(
            ["du", "-sh", str(path)], capture_output=True, text=True, check=False
        ).stdout
        return out.split()[0] if out else "?"
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--dest",
        type=Path,
        default=Path(os.environ.get("DEST", "/workspace")),
        help="Network Volume mount path (default: /workspace)",
    )
    p.add_argument(
        "--genres",
        nargs="+",
        default=None,
        metavar="GENRE",
        help=(
            "Gutenberg genres to download/ingest. "
            "In --rebuild-only mode, defaults to all genres present in the corpus dir. "
            "In full mode, defaults to: philosophy english-literature russian-literature"
        ),
    )
    p.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip Gutenberg book downloads; ingest from existing corpus",
    )
    p.add_argument(
        "--rebuild-only",
        action="store_true",
        help="Skip system deps, venv creation, and repo cloning; just rebuild indices",
    )
    p.add_argument(
        "--branch",
        default=os.environ.get("GUTENBERG_BRANCH", "main"),
        metavar="BRANCH",
        help="gutenberg_kg git branch to clone (default: main)",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def setup_env(dest: Path) -> None:
    """Redirect all temp/cache I/O to the volume (root fs is only ~5 GB)."""
    cache_dirs: dict[str, Path] = {
        "TMPDIR": dest / ".tmp",
        "PIP_CACHE_DIR": dest / ".pip_cache",
        "PIP_TMPDIR": dest / ".tmp",
        "PIP_BUILD": dest / ".tmp" / "pip_build",
        "HF_HOME": dest / ".hf_cache",
    }
    for var, path in cache_dirs.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[var] = str(path)

    os.environ.update(
        {
            "HF_HUB_OFFLINE": "0",
            "TRANSFORMERS_OFFLINE": "0",
            "HF_DATASETS_OFFLINE": "0",
            "HF_HUB_ENABLE_HF_TRANSFER": "0",
        }
    )


# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------

_SYSTEM_PACKAGES = [
    "python3.12",
    "python3.12-venv",
    "python3-pip",
    "git",
    "rsync",
    "libgomp1",
    "libglib2.0-0",
    "curl",
    "tmux",
]


def install_system_deps() -> None:
    info("Installing system dependencies …")
    run(["apt-get", "update", "-qq"])
    run(["apt-get", "install", "-y", "--no-install-recommends", *_SYSTEM_PACKAGES])
    run(["apt-get", "clean"])
    subprocess.run(["rm", "-rf", "/var/lib/apt/lists/"], check=False)
    step("system deps ready")


# ---------------------------------------------------------------------------
# Python venv
# ---------------------------------------------------------------------------


def ensure_venv(work_dir: Path) -> Path:
    venv = work_dir / "venv"
    pip = venv / "bin" / "pip"
    if pip.exists():
        step(f"reusing venv at {venv}")
        return venv
    info(f"Creating venv at {venv} …")
    shutil.rmtree(venv, ignore_errors=True)
    venv.parent.mkdir(parents=True, exist_ok=True)
    run(["python3.12", "-m", "venv", str(venv)])
    run([pip, "install", "--quiet", "--upgrade", "pip"])
    return venv


# ---------------------------------------------------------------------------
# Repo cloning
# ---------------------------------------------------------------------------


def _clone_or_pull(url: str, dest: Path, branch: str = "main") -> None:
    if (dest / ".git").exists():
        step(f"{dest.name}: pulling latest")
        run(["git", "-C", str(dest), "pull", "--quiet"])
    else:
        step(f"cloning {url} (branch: {branch})")
        run(["git", "clone", "--quiet", "--branch", branch, url, str(dest)])


def clone_repos(work_dir: Path, branch: str) -> None:
    info("Cloning repos …")
    os.environ["GIT_TERMINAL_PROMPT"] = "0"
    subprocess.run(["git", "config", "--global", "credential.helper", ""], check=False)
    _clone_or_pull(
        "https://github.com/Flux-Frontiers/gutenberg_kg.git",
        work_dir / "gutenberg_kg",
        branch,
    )
    _clone_or_pull("https://github.com/Flux-Frontiers/KGRAG.git", work_dir / "kgrag")


def install_packages(venv: Path, work_dir: Path) -> None:
    pip = venv / "bin" / "pip"
    info("Installing Python packages …")
    run([pip, "install", "--quiet", "-e", f"{work_dir / 'kgrag'}[kg]"])
    run([pip, "install", "--quiet", "-e", str(work_dir / "gutenberg_kg")])
    step("packages installed")


# ---------------------------------------------------------------------------
# GutenbergKG index build
# ---------------------------------------------------------------------------


_DEFAULT_GENRES = ["philosophy", "english-literature", "russian-literature"]


def resolve_genres(args: argparse.Namespace, work_dir: Path) -> list[str]:
    if args.genres is not None:
        return args.genres

    if args.rebuild_only:
        corpus_dir = work_dir / "gutenberg_kg" / "corpus"
        if corpus_dir.is_dir():
            detected = sorted(
                p.name for p in corpus_dir.iterdir() if p.is_dir() and p.name != "authors"
            )
            if detected:
                step(f"Auto-detected {len(detected)} genres from {corpus_dir}")
                return detected
        warn(f"Corpus dir not found at {corpus_dir}; falling back to defaults")

    return _DEFAULT_GENRES


def build_gutenbergkg(
    venv: Path,
    work_dir: Path,
    dest: Path,
    genres: list[str],
    skip_download: bool,
) -> None:
    info("Building GutenbergKG DocKG indices …")
    gutenkg = venv / "bin" / "gutenkg"
    gutenberg_src = work_dir / "gutenberg_kg"

    for genre in genres:
        blank()
        step(f"Genre: {genre}")

        if not skip_download:
            catalog = gutenberg_src / "scripts" / "catalogs" / f"{genre}.txt"
            if catalog.exists():
                step(f"Downloading from catalog ({catalog.name}) …")
                run(
                    [gutenkg, "download", "catalog", str(catalog), "--genre", genre],
                    cwd=gutenberg_src,
                )
            else:
                step("Downloading via fetch-genre (no catalog found) …")
                run(
                    [gutenkg, "download", "fetch-genre", genre, "--max-results", "200", "--yes"],
                    cwd=gutenberg_src,
                )

        step("Ingesting (building DocKG) …")
        run(
            [gutenkg, "ingest", "--genre", genre, "--force-build"],
            cwd=gutenberg_src,
        )

    blank()
    step("Syncing to volume …")
    gutenberg_dest = dest / "gutenberg_kg"
    gutenberg_dest.mkdir(parents=True, exist_ok=True)
    src_dockg = gutenberg_src / ".dockg"
    dest_dockg = gutenberg_dest / ".dockg"
    dest_dockg.mkdir(parents=True, exist_ok=True)
    run(["rsync", "-a", f"{src_dockg}/", f"{dest_dockg}/"])
    step(f"Done: {_du(dest_dockg)}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def print_summary(dest: Path) -> None:
    blank()
    print("=" * 60)
    print("  Volume contents:")
    dockg_dir = dest / "gutenberg_kg" / ".dockg"
    if dockg_dir.exists():
        print(f"    {_du(dockg_dir):>6}  {dockg_dir}")
    blank()
    print("  All done. Terminate this pod — the Network Volume is ready.")
    print(f"  Attach volume to the gutenkg worker with: KG_VOLUME={dest}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    dest: Path = args.dest
    work_dir = dest / "gutenkg_build"

    setup_env(dest)

    genres = resolve_genres(args, work_dir)

    print("=" * 60)
    print("  GutenbergKG Volume Builder")
    print(f"  Destination : {dest}")
    print(f"  Genres      : {' '.join(genres)}")
    if args.rebuild_only:
        print("  Mode        : rebuild indices only")
    print("=" * 60)
    blank()

    if not args.rebuild_only:
        install_system_deps()
        venv = ensure_venv(work_dir)
        clone_repos(work_dir, args.branch)
        install_packages(venv, work_dir)
    else:
        venv = work_dir / "venv"
        if not (venv / "bin" / "pip").exists():
            error(f"venv not found at {venv} — run without --rebuild-only first.")
            sys.exit(1)
        step(f"using existing venv at {venv}")

    build_gutenbergkg(venv, work_dir, dest, genres, args.skip_download)
    print_summary(dest)


if __name__ == "__main__":
    main()
