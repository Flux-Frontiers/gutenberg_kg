# Release Notes — v1.10.0

> Released: 2026-07-16

GutenbergKG 1.10.0 is an operational release: the API documentation site is
now live and rebuilt automatically on every change, and a handful of small
gaps left over from the 1.9.0 push are closed.

## What changed

**GitHub Pages goes live.** The API reference at
https://flux-frontiers.github.io/gutenberg_kg/ is now built and deployed by
`.github/workflows/docs.yml` on every push to `main`, rather than committing
generated HTML to the repo. `docs/` reverts to hand-written markdown only,
and `make docs` writes its pdoc output to a gitignored `site/`. Getting there
took a full audit of what `pdoc` actually needs at import time — it exercises
every documented module, including `gutenberg_kg.serve.handler`'s full
startup sequence (KG registry, embedder warm-up) — so the CI job now installs
the complete set of extras that requires (`dev chat image mcp viz viz3d
kgdeps`), pip-installs `runpod` alongside them, and sets
`PDOC_ALLOW_EXEC=1` to work around a Linux-only crash in `runpod`'s
import-time CPU probe. The docs logo, which pointed at a file never
committed to the repo, now resolves correctly too.

**The docs landing page had nothing on it.** `gutenberg_kg/__init__.py`
carried no module docstring, so pdoc's generated `index.html` — which
redirects straight to the package's top-level page — rendered essentially
empty. It now describes the project in general terms: an ingestion engine
for public-domain text corpora, not affiliated with or limited to Project
Gutenberg specifically.

**`/release` gets a safety net.** The release workflow now runs `poetry run
make docs` as a gate before tagging, so an environment or import regression
in the docs build is caught locally instead of silently failing the Pages
deploy after the tag is already pushed.

## Upgrading

No dependency, schema, or API changes — this release only affects
documentation tooling. Nothing to do beyond the usual `git pull`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
