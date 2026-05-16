#!/usr/bin/env bash
# push_indices.sh
#
# Push pre-built GutenbergKG DocKG indices from your local machine to a
# RunPod Network Volume via SSH.  Total upload is ~130 MB (just the indices,
# not the raw text corpus).
#
# This is the fastest way to populate the volume: build locally once,
# push the resulting .dockg/ directory.  The raw Gutenberg corpus stays
# on your machine.
#
# Prerequisites
# -------------
#   1. A RunPod Network Volume exists (≥ 10 GB).
#   2. A temporary RunPod pod has the volume attached and is running.
#      ("Mount path" in RunPod UI should be /workspace)
#   3. SSH key added to RunPod account (Settings → SSH Public Keys).
#   4. Local .dockg/ indices already built:
#        gutenkg ingest --genre philosophy --force-build
#
# Usage
# -----
#   # Basic (prompts for connection details)
#   ./push_indices.sh
#
#   # Non-interactive
#   POD_HOST=ssh.runpod.io POD_PORT=12345 ./push_indices.sh
#
# The pod SSH address is shown in the RunPod dashboard:
#   Pods → <your pod> → Connect → "SSH over exposed TCP"
#   It looks like:  ssh root@ssh.runpod.io -p 12345

set -euo pipefail

# ---------------------------------------------------------------------------
# Config — override via env vars or interactive prompts
# ---------------------------------------------------------------------------

POD_HOST="${POD_HOST:-}"
POD_PORT="${POD_PORT:-}"
DEST_BASE="${DEST_BASE:-/workspace}"
SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"

if [[ -z "${POD_HOST}" ]]; then
    read -rp "Pod SSH host (e.g. ssh.runpod.io): " POD_HOST
fi
if [[ -z "${POD_PORT}" ]]; then
    read -rp "Pod SSH port (e.g. 12345): " POD_PORT
fi

SSH_TARGET="root@${POD_HOST}"
SSH_OPTS="-p ${POD_PORT} -i ${SSH_KEY} -o StrictHostKeyChecking=no"
RSYNC_SSH="ssh ${SSH_OPTS}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUTENBERG_REPO="$(dirname "${SCRIPT_DIR}")"   # this repo

echo ""
echo "==> Target: ${SSH_TARGET} -p ${POD_PORT} : ${DEST_BASE}"
echo ""

# ---------------------------------------------------------------------------
# Verify local indices exist
# ---------------------------------------------------------------------------

DOCKG_LOCAL="${GUTENBERG_REPO}/.dockg/graph.sqlite"

if [[ ! -f "${DOCKG_LOCAL}" ]]; then
    echo "ERROR: missing local index: ${DOCKG_LOCAL}"
    echo "       Run 'gutenkg ingest --genre <genre> --force-build' first."
    exit 1
fi

# ---------------------------------------------------------------------------
# Create remote directory structure
# ---------------------------------------------------------------------------

ssh ${SSH_OPTS} "${SSH_TARGET}" \
    "mkdir -p ${DEST_BASE}/gutenberg_kg/.dockg"

# ---------------------------------------------------------------------------
# Push indices
# ---------------------------------------------------------------------------

echo "--- GutenbergKG .dockg/ ---"
rsync -avz --progress -e "${RSYNC_SSH}" \
    "${GUTENBERG_REPO}/.dockg/" \
    "${SSH_TARGET}:${DEST_BASE}/gutenberg_kg/.dockg/"

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

echo ""
echo "==> Remote volume contents:"
ssh "${SSH_TARGET}" -p "${POD_PORT}" \
    "du -sh ${DEST_BASE}/gutenberg_kg/.dockg 2>/dev/null"

echo ""
echo "Done. Detach or terminate the temporary pod."
echo "The Network Volume now has all indices — attach it to the gutenkg endpoint."
