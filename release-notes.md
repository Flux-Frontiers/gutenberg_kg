# Release Notes -- v1.15.0

> Released: 2026-09-01

The documentation site now runs on mkdocs-material with an API reference
generated from the package docstrings, gated by a strict local build.
The release also adds publication-year dating, an analytic POV-Ray
rendering backend, and a cross-platform local image server.

## What changed

**Documentation moved from pdoc to mkdocs-material.** The `docs/*.md`
guides render as a site with navigation, search, and theming, and
mkdocstrings generates the API reference from the package docstrings.
The site builds on every push to `main` that touches docs or source,
instead of only on version tags. A new `scripts/check_docs_build.py`,
wired into pre-commit, runs `mkdocs build --strict` and fails on any
warning outside two known categories, so a broken internal link or a
missing nav target no longer ships. CI's own build runs without
`--strict` because those two warning categories are permanent.

**Books carry their publication year.** `gutenberg_kg.temporal` reads
the year from a book's Internet Archive metadata and stamps it on every
node in the book's graph, not just the document row, so time-scoped
federated queries can match individual chunks. Years stay years:
`"1876"` is not converted to `1876-01-01`, so it matches a query for any
month of 1876.

**`gutenkg pov` renders the knowledge tree as an analytic POV-Ray
scene.** Limbs are swept tubes and each leaf is an instance of one
declared ellipsoid, so files are one to two orders of magnitude smaller
than the VTK mesh dump and silhouettes stay exact at any zoom. Both
backends grow from the same skeleton, so they produce the same tree. The
new `pov` extra needs no PyVista, Qt, or GL context; a headless machine
with a `povray` binary can write and render scenes.

**Local image generation runs off Apple Silicon.** `make up` previously
assumed the FLUX backend, which only installs on Apple hardware. It now
falls back to SDXL-Lightning, which runs on CUDA, MPS, or CPU.

**Dependency pins are gated.** `scripts/check_pins.py` verifies the four
cross-pinned KG packages (`kgmodule-utils`, `kg-rag`, `doc-kg`,
`diary-kg`) agree across `pyproject.toml`, `poetry.lock`, the Dockerfile
ARGs, and `runpod/requirements.txt`, and gates `make build` and CI.
`kgmodule-utils` moves to 0.18.0.

## Upgrading

Building the docs needs the new optional `docs` group:
`poetry install --with docs --extras "chat image mcp viz viz3d kgdeps"`,
then `make docs` (or `make docs-serve` for live reload). Nothing else
requires action: a plain `poetry install` picks up the relocked
dependencies, and the POV-Ray path is opt-in via
`poetry install --extras pov`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
