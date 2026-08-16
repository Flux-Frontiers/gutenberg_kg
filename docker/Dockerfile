# corpus-gutenberg — standalone KGRAG image for the full GutenbergKG corpus
#
# Self-contained build from python:3.12-slim (no kgrag-worker base — everything
# the worker imports comes from PyPI pins + this checkout):
#   - the pre-built bundle (DocKG + DiaryKG indices) baked in at /workspace/gutenberg/
#   - a Gutenberg-specific handler that registers all KG kinds on startup
#
# Build workflow:
#   1. make build-diaries  — rebuild DiaryKG indices in corpus/diaries/*/
#   2. make build-corpus   — bundle DocKG + diary indices -> bundles/gutenberg-all/
#   3. make build          — docker build (COPYs bundle into image)
#   4. make run            — docker compose up
#
# Steps 1-2 must complete before step 3.  build-corpus depends on build-diaries
# in the Makefile, so `make build-corpus` runs both automatically.
# The bundle must exist at bundles/gutenberg-all/ before building.
# Layout baked into the image at /workspace/gutenberg/:
#   .dockg/
#     graph.sqlite    (696K nodes · 6.2M edges)
#     vectors.sqlite  (696K × 384-dim vectors, sqlite-vec — exact, ~10x smaller
#                      than the LanceDB store it replaced)
#     catalog.json    (241 books · author/title/Gutenberg ID)
#   diaries/
#     The Diary of Samuel Pepys — Complete/.diarykg/
#     The Diary of John Evelyn — Volume 1/.diarykg/
#     The Diary of John Evelyn — Volume 2/.diarykg/
#     The Journal of a Tour to the Hebrides with Samuel Johnson/.diarykg/

FROM python:3.12-slim

WORKDIR /app

# System libs needed by the sentence-transformers / pyarrow wheels.
# libgomp1: OpenMP runtime for torch. libglib2.0-0: pulled in by the pyarrow
# side of the doc-kg stack.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgomp1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch, installed BEFORE the KG stack that pulls it transitively.
#
# torch's default PyPI wheel for linux/aarch64 is now a CUDA build (2.13.0+cu130
# at the time of writing — the aarch64 CUDA wheels exist for ARM servers like
# Grace Hopper). Nothing here asks for it; it arrives silently through
# sentence-transformers. In this image it is pure dead weight: 2.9 GB of
# nvidia-* runtime plus 652 MB of triton, in a container that reports
# torch.cuda.is_available() == False whether it runs under Docker Desktop or
# Apple's `container` — both are arm64 VMs on Apple Silicon with no NVIDIA GPU.
#
# Its own RUN on purpose: --index-url REPLACES PyPI for the whole command, and
# the PyTorch CPU index does not host kg-rag/doc-kg/diary-kg. Installing torch
# first means the resolver below finds the requirement already satisfied and
# leaves the CPU build in place. Keep this layer above the KG install so a pin
# bump doesn't re-download torch.
#
# NOTE: this is the LOCAL/Apple image only. runpod/Dockerfile is deliberately
# left on the default CUDA wheels — RunPod serverless is amd64 on real GPUs,
# where that build is the correct one.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

# runpod: serverless worker harness (rp_serve_api) used by the handler
# kg-rag: KGRegistry/CorpusRegistry + embedder wrapper — imported lazily by
#         the handler's _bootstrap_registry, so a missing install only fails
#         at container startup, not at build time
# kgmodule-utils: synthesis + shared KG runtime; the [sqlite-vec] extra supplies
#         the sqlite_vec module the served vectors.sqlite store needs
# doc-kg: DocKG index + query API (pulls the heavy torch/sentence-transformers
#         stack transitively)
# diary-kg: DiaryKG temporal index + query API
# streamlit + httpx: chat UI dependencies
# watchdog: faster Streamlit file-watching via native OS events (vs. polling)
# All three KG packages ship on PyPI, so they install by version like any other
# dep. Pre-installing them here (before the src COPY below) keeps them in a cached
# layer, so source-only changes don't re-resolve the heavy KG/torch stack.
# KEEP THESE >= THE FLOORS IN pyproject.toml [project].dependencies. The
# `pip install .` below re-resolves the same packages, so a pin below the floor
# is silently upgraded there — the pinned layer is wasted work and the numbers
# here become fiction. These are the versions the build is verified against.
#
# They also move as a SET, not individually — these four are cross-pinned. What
# each one actually requires, read off the lock rather than from memory:
#   kg-rag 0.11.0         transformers>=5.5.0,<6 · kgmodule-utils>=0.8.0
#                         (also the floor for KGEntry.vectors_path, which
#                         handler.py passes at startup)
#   doc-kg 0.21.1         kgmodule-utils[semantic]>=0.10.0
#   diary-kg 0.97.0       doc-kg>=0.21.2 · kgmodule-utils>=0.13.2
#   kgmodule-utils 0.11.0 transformers>=5.5.0,<6 via its [semantic] extra
# Because these are `==` pins, a stale one is a hard resolution failure at build
# time, not a silent upgrade: doc-kg 0.21.1 with kgmodule-utils==0.9.0 cannot
# resolve. Bump them together and rerun `poetry lock`.
#
# KGMODULE_UTILS_VERSION tracks pyproject's >=0.12.1 floor and the lock. It sat
# at 0.10.0 — below both — which made the ARG fiction rather than a pin: the
# `pip install .` below re-resolved it and upgraded anyway, exactly as the
# paragraph above warns, so the image never ran the version named here and the
# pre-install layer fetched that package twice per cold build. 0.12.1 is the
# release that actually carries the organic tree engine scene.py imports: 0.12.0
# was published without it, from a tree the v0.12.0 tag did not contain, and
# cannot be corrected in place because PyPI reserves an uploaded filename.
ARG KG_RAG_VERSION=0.12.0
ARG KGMODULE_UTILS_VERSION=0.14.0
ARG DOC_KG_VERSION=0.21.2
ARG DIARY_KG_VERSION=0.97.0
RUN pip install --no-cache-dir \
    "runpod>=1.7.0" \
    "kg-rag==${KG_RAG_VERSION}" \
    "kgmodule-utils[synthesis,sqlite-vec]==${KGMODULE_UTILS_VERSION}" \
    "doc-kg==${DOC_KG_VERSION}" \
    "diary-kg==${DIARY_KG_VERSION}" \
    streamlit httpx watchdog openai

# Install the local repo package so runtime imports always match this checkout.
# The serving layer (handler, chat UI, pages) ships inside the package at
# gutenberg_kg/serve/ — no loose script COPYs needed.
COPY pyproject.toml README.md /app/
COPY src/gutenberg_kg /app/src/gutenberg_kg
RUN pip install --no-cache-dir .

# Pre-download the embedding model during build so the container never reaches
# HuggingFace at runtime (network may be unavailable or restricted on RunPod).
# The token arrives as a BuildKit secret (see HF_SECRET in the Makefile), so the
# Hub request is authenticated — higher rate limits, no "unauthenticated
# requests" warning — without the token landing in the image or its build
# history the way a --build-arg would. The secret is optional: with none
# mounted, the download proceeds anonymously, which still works for this
# public model.
ARG EMBED_MODEL=BAAI/bge-small-en-v1.5
RUN --mount=type=secret,id=hf_token \
    if [ -s /run/secrets/hf_token ]; then export HF_TOKEN="$(cat /run/secrets/hf_token)"; fi; \
    python - <<'EOF'
import os
from sentence_transformers import SentenceTransformer
model = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
print(f"Pre-downloading {model} ...")
SentenceTransformer(model)
print("Done.")
EOF

# Force offline mode — no HuggingFace network calls at runtime.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# Bake the full bundle into the image.
# Generated by:  gutenkg build-corpus
# Lives at:      bundles/gutenberg-all/   (gitignored — build locally first)
COPY bundles/gutenberg-all/ /workspace/gutenberg/

ENV GUTENBERG_ROOT=/workspace/gutenberg
ENV EMBED_MODEL=BAAI/bge-small-en-v1.5
# In-container marker for runtimes that don't create /.dockerenv (Apple's
# `container` CLI) — read by the chat UI to pick host.docker.internal.
ENV GUTENKG_IN_CONTAINER=1

CMD ["python", "-u", "-m", "gutenberg_kg.serve.handler"]
