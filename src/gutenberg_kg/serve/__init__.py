# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Serving layer for the GutenbergKG corpus.

Modules
-------
handler       — the worker (semantic search + synthesis), served by worker_api.
                Importing it runs the full startup sequence (registry,
                embedder, vector tables), so import it only to serve.
Chat          — Streamlit chat UI (launch via ``gutenkg chat``).
pages/        — extra Streamlit pages auto-discovered next to Chat.py.
image_server  — ``gutenkg-image-server``, an alias of ``imagewright serve``
                kept for one release (and ``sdxl_server``, its SDXL twin).

Optional dependencies: install ``gutenberg-kg[chat]`` for the chat UI. The
worker's FastAPI comes with its container image (docker/Dockerfile).
"""
