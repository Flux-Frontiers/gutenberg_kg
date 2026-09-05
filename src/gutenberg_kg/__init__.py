# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""GutenbergKG — The Knowledge Press.

A universal ingestion engine for digitized text corpora. Downloads texts
from public-domain sources (Project Gutenberg, the Internet Archive, and
others), ingests and indexes them into a hybrid semantic + structural
knowledge graph via `DocKG`_, and serves them for federated cross-corpus
retrieval through `KGRAG`_.

Modules
-------
cli           — the ``gutenkg`` command group (download, ingest, query,
                snapshots, visualisation, batch workflows).
serve         — the RunPod worker, Streamlit chat UI, and image servers
                (see :mod:`gutenberg_kg.serve` — optional extras required).
build_corpus  — corpus build/bundle pipeline (``gutenkg build-corpus``).
image_gen     — FLUX.2-Klein image generation (local MLX or remote server).
mcp_server    — MCP tools for querying the corpus and generating images.

.. _DocKG: https://github.com/Flux-Frontiers/doc_kg
.. _KGRAG: https://github.com/Flux-Frontiers/KGRAG
"""

__version__ = "1.18.0"
