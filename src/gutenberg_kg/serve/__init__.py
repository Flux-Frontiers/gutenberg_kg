# © 2026 Eric G. Suchanek, PhD — Flux-Frontiers · SPDX-License-Identifier: Elastic-2.0
"""Serving layer for the GutenbergKG corpus.

Modules
-------
handler       — RunPod serverless worker (semantic search + synthesis).
                Importing it runs the full startup sequence (registry,
                embedder, vector tables), so import it only to serve.
chat          — Streamlit chat UI (launch via ``gutenkg chat``).
pages/        — extra Streamlit pages auto-discovered next to chat.py.
image_server  — FastAPI wrapper around :mod:`gutenberg_kg.image_gen`
                (launch via ``gutenkg-image-server``).

Optional dependencies: install ``gutenberg-kg[worker]``, ``[chat]``, or
``[image]`` for the respective module's requirements.
"""
