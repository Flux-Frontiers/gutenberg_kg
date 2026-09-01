# Release Notes — v1.15.0

> Released: 2026-09-01

Three weeks of work land here. The most visible change is the documentation
site: it now runs on mkdocs-material with a real API reference generated
from the package's own docstrings, gated by a strict local build so a broken
link can no longer ship unnoticed. Alongside it, books now carry their
publication year, a second backend renders knowledge trees as analytic
POV-Ray scenes instead of a VTK mesh, and the local image server runs on any
machine, not just Apple Silicon.

## What changed

**The docs site moved from pdoc to mkdocs-material.** pdoc rendered a flat
module dump with no search or theming; mkdocs-material now renders the
`docs/*.md` guides as a real site with navigation, search, and theming, and
mkdocstrings generates the API reference straight from the package's own
docstrings, so the reference can't drift from the code the way a hand-written
one would. It also builds on every push to `main` that touches the docs or
the source tree, rather than only on a version tag, so the published site can
now go stale for at most one push instead of a whole release cycle. A new
`scripts/check_docs_build.py`, wired into pre-commit, runs `mkdocs build
--strict` and fails on any warning outside two known, permanent categories —
closing a gap where a genuinely broken internal link or a missing nav target
would previously build clean and ship silently, since CI's own build runs
without `--strict`.

**A book now carries its publication year.** `gutenberg_kg.temporal` reads
the year a book was published from its Internet Archive metadata and stamps
it onto every node in that book's graph, not just the top-level document —
because a federated query hits chunks directly, and a chunk with no year
attached drops out of any time-scoped search. The year is kept deliberately
imprecise: `"1876"` is stored as a year, not silently promoted to
`1876-01-01`, so it still overlaps a query for any month in that year.

**`gutenkg pov` renders the knowledge tree as an analytic POV-Ray scene.**
Where the existing `gutenkg quilt` path tessellates the tree into a VTK mesh,
this one sweeps tubes and instances a single declared ellipsoid per leaf —
one to two orders of magnitude smaller on disk, with silhouettes that stay
exact at any zoom. Both backends grow from the same skeleton, so they can't
drift into two different-looking trees. It's headless: the new `pov` extra
needs no PyVista, Qt, or GL context, so a machine with just a `povray` binary
can write scenes.

**Local image generation no longer requires Apple Silicon.** `make up`
previously assumed the FLUX backend, which fails outright to install on any
non-Apple host. It now falls back to SDXL-Lightning, which runs on
CUDA, MPS, or plain CPU, so the stack comes up everywhere — slowly on CPU,
but it comes up.

**Dependency pin hygiene.** The four KG packages this project cross-pins
(`kgmodule-utils`, `kg-rag`, `doc-kg`, `diary-kg`) had drifted across
`pyproject.toml`, `poetry.lock`, the Dockerfile ARGs, and
`runpod/requirements.txt` — `scripts/check_pins.py`, added this cycle, now
gates `make build` and CI on all four agreeing. `kgmodule-utils` moves to
0.18.0 as part of that.

## Upgrading

Building the docs locally needs the new optional `docs` group:
`poetry install --with docs --extras "chat image mcp viz viz3d kgdeps"`, then
`make docs` (or `make docs-serve` for live reload). Nothing else requires
action — a plain `poetry install` picks up the relocked dependencies, and the
POV-Ray path is opt-in via `poetry install --extras pov`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
