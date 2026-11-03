# Release Notes -- v1.32.0

> Released: 2026-11-03

### Added

- **`scripts/rotate_omlx_key.py`: one oMLX API key in both places.** Writes a
  random key (or `--key`) to `auth.api_key` in `~/.omlx/settings.json` and to
  `VLLM_API_KEY` in `docker/.env`, backing up the settings to a timestamped
  `settings.json.bak-*` on each run and never printing the key. It refuses while oMLX is running (port open, or an `omlx` process),
  since the app can write its settings back on exit. A mismatch is what makes
  oMLX answer 401 and the chat UI's model list come up empty.

- **`make bootstrap`: one-command install for a fresh clone.**
  `scripts/bootstrap.py` (stdlib only, so it runs before Poetry or the venv
  exist) checks Python 3.12/3.13, Poetry 2.x, Make and a container runtime,
  installs Poetry when missing (with confirmation), runs `poetry install`,
  `gutenkg init` and seeds `docker/.env` without overwriting it, then reports
  which oMLX, Ollama and OpenAI backends are usable. `DRY_RUN=1` prints every
  action and changes nothing; it ends by printing the next command rather than
  starting the 30-45 minute corpus build. A header records the version,
  git commit, UTC timestamp, host, OS, CPU, memory, free disk and Python.

- **Ten books from the wishlist** (265 after ingest): Gogol's *The Mantle,
  and Other Stories*, the *Letters of the Right Honourable Lady Mary Wortley
  Montagu* (Gutenberg #17520, whose own title initials her name as "Lady
  M—y W—y M—e"), *The Best Letters of Charles Lamb*, Chekhov's *Plays, Second
  Series*, Synge's *The Playboy of the Western World*, the Raven Edition of
  Poe, volumes 2-5 (#2148-2151, beside volume 1 in american-literature), and
  Cicero's *De Officiis*. Gutenberg's only *De Officiis* is the bilingual
  Loeb; the corpus keeps Miller's English and drops the Latin and its
  manuscript-variant notes, which the English embedder turned into search
  noise. Montagu's 58 letters each get a heading (the download had fused
  them into two sections), and stray headings in Synge and Gogol are fixed.
- **`add-book` skill: a structure gate before any build.** Every new book's
  heading outline, section count and language are checked first, with the
  four problems this batch hit and their fixes.

### Changed

- **A uv-managed Python is the suggested interpreter.** `make bootstrap`'s
  hint for an unsupported Python is now `uv python install 3.12` (Homebrew
  only as the fallback when uv is absent), and INSTALLATION.md gains "Using a
  uv-managed Python": how to point Poetry's in-project `.venv` at uv's
  standalone CPython, why `uv python find` needs `--system`, and why
  `poetry env use` fails while `VIRTUAL_ENV` names the removed venv.
  INSTALLATION.md and `docker/.env.example` also say where the oMLX app keeps
  its port (`~/.omlx/settings.json`, default 8000, the worker's) and that
  `VLLM_MODEL` must be a model oMLX serves; three troubleshooting rows cover
  the port clash, the empty model list, and "Network is unreachable" from a
  closed image-server port.

- **INSTALLATION.md no longer says image generation needs a local LLM.** With
  `OPENAI_API_KEY` set, the worker and chat UI generate images with
  `gpt-image-1` and need no local model or image server. `gutenkg imagine`
  still calls an image server, and the page now says so. A new "SDXL on
  Windows" section gives the PowerShell steps, since `make sdxl-server`
  assumes a POSIX shell.

### Fixed

- **`make up` no longer leaves the image server silently down.**
  `image-server`, `sdxl-server` and `sdxl-fetch` built `.venv-image` and
  `.venv-sdxl` with a bare `python3 -m venv`, so a Homebrew 3.14 first on PATH
  gave a venv outside `requires-python`, and a Homebrew whose bundled pip wheel
  the user could not read gave one with no pip. Every later step failed, `make
  up` printed its warning, and the worker reported "Network is unreachable"
  for :8090. A shared `make-venv` recipe now uses `uv venv --seed
  --managed-python` (uv's standalone CPython, independent of Homebrew) when uv
  is on PATH, else python3.13 or python3.12; it rebuilds a venv on the wrong
  Python or without pip, and fails the target if the build does not work.
  `VENV_PYTHON` and `VENV_UV_FLAGS` override the choice.

- **`make bootstrap DEV=1` no longer asks for the retired `kg` group.** The
  group went in #152 (pycode-kg is a global tool), but bootstrap still ran
  `poetry install --with dev,kg`, which stops with "Group(s) not found: kg";
  INSTALLATION.md gave the same command in three places. Both now say
  `--with dev`, and a test checks every group bootstrap names against
  pyproject.

- **A book held in one genre is no longer downloaded again from another
  genre's catalog.** The already-downloaded check (`gutenkg download` and
  `gutenkg ia download`) searched only the target genre, so the
  american-literature catalog re-downloaded Douglass (#23) and Washington
  (#2376), both held in biography. It now searches the whole corpus, and the
  skip records the book in the catalog of the genre that holds it. Without
  `--genre` the check had never matched at all: it looked one level below
  `corpus/`, where there are only genre directories. Those two catalog lines
  are removed.

### Security

- **kgmodule-utils 0.29.2 and quiltwright 0.17.0 are the floors.** Both
  floor Pillow at 13.0.0, so the core install (through
  `kgmodule-utils[synthesis]`) and the `viz3d` and `pov` extras (through
  quiltwright) can no longer resolve Pillow 12.3.0 and its 41 advisories.
  `scripts/check_pins.py --bump` moved the kgmodule-utils floor in
  `pyproject.toml`, the Dockerfile ARG and `runpod/requirements.txt`
  together; the lock follows both. At release, `check_pins.py --bump` also
  moved kg-rag to 0.18.1 in the same three places.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
