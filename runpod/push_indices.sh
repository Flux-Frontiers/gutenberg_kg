#!/usr/bin/env bash
# push_indices.sh
#
# Push the pre-built GutenbergKG corpus bundle from your local machine to a
# RunPod Network Volume via SSH.
#
# The bundle lives at bundles/gutenberg-all/ after running `make build-corpus`.
# It contains the consolidated DocKG index (.dockg/) and DiaryKG indices
# (diaries/) for the full 249-book corpus.  Total upload is several GB.
#
# The remote layout after this script (sqlite-vec — LanceDB dirs are excluded):
#   /workspace/
#   └── gutenberg_kg/
#       ├── .dockg/          (DocKG index — SQLite graph + sqlite-vec vectors)
#       │   ├── graph.sqlite
#       │   ├── vectors.sqlite
#       │   └── catalog.json
#       └── diaries/         (DiaryKG temporal indices, each with vectors.sqlite)
#
# Prerequisites
# -------------
#   1. make build-corpus has completed (bundles/gutenberg-all/ exists locally).
#   2. A RunPod Network Volume exists (≥ 20 GB recommended).
#   3. A temporary RunPod pod has the volume attached at /workspace.
#   4. SSH key added to your RunPod account (Settings → SSH Public Keys).
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
GUTENBERG_REPO="$(dirname "${SCRIPT_DIR}")"

BUNDLE_DIR="${GUTENBERG_REPO}/bundles/gutenberg-all"
BUNDLE_CHECK="${BUNDLE_DIR}/.dockg/graph.sqlite"

echo ""
echo "==> Target: ${SSH_TARGET} -p ${POD_PORT} : ${DEST_BASE}/gutenberg_kg/"
echo ""

# ---------------------------------------------------------------------------
# Verify local bundle exists
# ---------------------------------------------------------------------------

if [[ ! -f "${BUNDLE_CHECK}" ]]; then
    echo "ERROR: corpus bundle not found at ${BUNDLE_CHECK}"
    echo "       Run 'make build-corpus' first to generate bundles/gutenberg-all/."
    exit 1
fi

echo "==> Source bundle: ${BUNDLE_DIR}"
du -sh "${BUNDLE_DIR}" || true
echo ""

# ---------------------------------------------------------------------------
# Create remote directory structure
# ---------------------------------------------------------------------------

ssh ${SSH_OPTS} "${SSH_TARGET}" \
    "mkdir -p ${DEST_BASE}/gutenberg_kg"

# ---------------------------------------------------------------------------
# Push bundle
# ---------------------------------------------------------------------------

echo "--- Pushing corpus bundle → ${DEST_BASE}/gutenberg_kg/ ---"
# --exclude 'lancedb': the served worker reads sqlite-vec (vectors.sqlite); the
# LanceDB dirs are the ~2.3 GB legacy store and are not shipped. Drop the flag
# to fall back to a LanceDB deploy.
rsync -avz --progress --exclude 'lancedb' -e "${RSYNC_SSH}" \
    "${BUNDLE_DIR}/" \
    "${SSH_TARGET}:${DEST_BASE}/gutenberg_kg/"

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

echo ""
echo "==> Remote volume contents:"
ssh "${SSH_TARGET}" -p "${POD_PORT}" \
    "du -sh ${DEST_BASE}/gutenberg_kg 2>/dev/null && \
     ls ${DEST_BASE}/gutenberg_kg/.dockg/ 2>/dev/null || echo '  (no .dockg yet)'"

echo ""
echo "Done. Detach or terminate the temporary pod."
echo "The Network Volume is ready — attach it to the gutenkg serverless endpoint."
