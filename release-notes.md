# Release Notes — v1.13.0

> Released: 2026-08-03

Nineteen commits since v1.12.0, gathered here. The theme is things that were
wrong quietly: an image carrying gigabytes it could never use, a chat control
that reverted without saying so, a gateway address that pointed nowhere, and a
dependency file that made `poetry lock` take eight minutes.

## What changed

**The container image lost ~3.8 GB of unusable CUDA runtime.** torch's default
PyPI wheel for linux/aarch64 is a CUDA build, pulled in silently through
sentence-transformers. In this image it was pure weight — the container reports
`torch.cuda.is_available() == False` on Apple Silicon regardless. Installing
CPU-only torch before the KG stack keeps the resolver satisfied and the GPU
runtime out.

**`poetry lock` went from 503 seconds to under ten.** The `full` and `all`
aggregate extras re-listed packages already declared elsewhere, which Poetry
treats as duplicate dependencies under different markers — it discards the
resolution, adds an override, and restarts, with the override set growing each
time. Removing the aggregates removed the restarts.

**The chat model picker keeps your selection.** Choosing a synthesis model and
then refreshing the model list reverted the picker to the provider default. The
selectboxes carried no Streamlit key, so refreshing changed the widget's
identity and reset it. Worse, the reset was invisible: the sidebar went on
showing the default while queries and image-prompt rewrites used it, so answers
came back from a model you had not chosen.

**The Apple runtime's fallback gateway was wrong.** Containers reach host
services over the vmnet gateway, and the cold-start fallback pointed at
`192.168.65.1` — Docker Desktop's subnet — rather than the `192.168.64.0/24`
that macOS's vmnet framework actually allocates. This repo's own documentation
had it right; only the Makefile disagreed.

**Vector store handling is stricter.** A new `resolve_vector_paths()` resolves a
store from a KG root, registration records `vectors_path` for migrated graphs,
and the served dimension is read from the store rather than assumed to be 384.
Several `build-corpus` bugs around leftover LanceDB stores are fixed alongside.

## Upgrading

Rebuild the image to pick up the CPU-only torch change and the chat fix:
`make build`. Nothing else is required.

Dependency floors moved to a co-installable set (`doc-kg>=0.20.0`,
`diary-kg>=0.96.0`, `rich>=14.3.3,<15`), so re-lock if you track this repo as a
dependency. The `full` and `all` extras no longer exist — install the specific
extras you need instead.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
