#!/usr/bin/env bash
# build_image.sh — build local package wheels then build the Docker image.
#
# Usage:
#   ./build_image.sh [IMAGE_TAG]
#
# Default IMAGE_TAG: gutenkg-worker:latest
#
# Prereqs: pip, docker. kg-rag installs from PyPI (see requirements.txt);
# only the gutenberg-kg wheel is built locally.

set -euo pipefail

IMAGE="${1:-gutenkg-worker:latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEEL_DIR="${SCRIPT_DIR}/wheels"

GUTENBERG_REPO="$(dirname "${SCRIPT_DIR}")"            # this repo

echo "==> Building gutenberg-kg wheel into ${WHEEL_DIR}/"
rm -rf "${WHEEL_DIR}"
mkdir -p "${WHEEL_DIR}"
pip wheel --no-deps -w "${WHEEL_DIR}" "${GUTENBERG_REPO}" -q

echo "==> Wheels built:"
ls -lh "${WHEEL_DIR}"/*.whl

echo "==> Building Docker image: ${IMAGE}"
docker build -t "${IMAGE}" "${SCRIPT_DIR}"

echo ""
echo "Done. Push with:"
echo "  docker tag ${IMAGE} <your-registry>/${IMAGE}"
echo "  docker push <your-registry>/${IMAGE}"
