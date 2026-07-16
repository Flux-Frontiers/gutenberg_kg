# Release Notes — v1.9.0

> Released: 2026-07-16

GutenbergKG 1.9.0 takes the Knowledge Press beyond the browser: a native
macOS app (Phase 1 thin client) now talks to the same worker the Streamlit UI
uses, and the vector store underneath everything has migrated from LanceDB to
sqlite-vec — exact retrieval, ~10× smaller on disk.

## What changed

**KnowledgePress macOS app.** The new `app/GutenbergKGKit/` SwiftPM package
ships a SwiftUI thin client for the corpus: a chat view that renders
retrieved passages per turn, a Browse view for reading books chapter by
chapter, and a settings sidebar for the worker endpoint and API key. Under it
sits `GutenbergKGKit`, an async `WorkerClient` covering the worker's search,
stats, and browse ops, with unit tests against a stubbed `URLProtocol`.
Phase 2 (on-device Core ML retrieval) is the next step.

**sqlite-vec replaces LanceDB.** Benchmarks showed the production LanceDB
IvfFlat index averaging 0.825 recall@10 (as low as 0.4 on exact-phrase
queries like "pillar of salt"), while sqlite-vec brute force is exact at
comparable latency and shrinks the store from ~2.5 GB to ~1.1 GB. Both
workers now prefer `vectors.sqlite` and keep LanceDB only as a transition
fallback — with an `nprobes(128)` stopgap that lifts fallback recall to
0.992. `build-corpus` emits sqlite-vec bundles natively, and a new
`docker/Dockerfile.sqlite` builds a worker image that never ships the
LanceDB directory at all.

**Serving layer moved into the package.** The RunPod handler, Streamlit chat
UI, and FLUX image server now live in `gutenberg_kg.serve` with proper entry
points (`gutenkg chat`, `gutenkg-handler`, `gutenkg-image-server`) and
optional extras (`[chat]`, `[image]`), instead of loose scripts under
`docker/`. The chat UI header and corpus-scope dropdown are now fed live from
the worker's new `stats` op rather than hardcoded counts.

**Accuracy fixes.** Diary books are no longer dropped from ingest reports
(20 genres reported, not 19); the missing `sqlite-vec` extra that crash-looped
the worker and broke non-Docker installs is fixed; the horror genre is no
longer silently omitted from generated corpus docs; and every public corpus
count (badges, tables, citations) is regenerated from live data — 241 books,
1,270,591 nodes, 5,094,446 edges across 20 genres.

## Upgrading

Run `poetry install` to pick up the raised floors (`doc-kg>=0.18.0`,
`kgmodule-utils[synthesis,sqlite-vec]>=0.5.0`), then rebuild bundles with
`make build-corpus` to emit the new `vectors.sqlite` store and rebuild the
Docker image with `make build`. Existing LanceDB bundles keep working through
the fallback path. Image generation now takes `--size WIDTHxHEIGHT` instead
of `--ratio`. The macOS app builds with `swift build` inside
`app/GutenbergKGKit/` — see `app/README.md`.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
