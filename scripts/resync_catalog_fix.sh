#!/usr/bin/env bash
# resync_catalog_fix.sh — pull the fix/catalog corpus corrections onto this
# machine and rebuild the DocKG indices that changed.
#
# Background: fix/catalog fixed several mislabeled books (wrong Gutenberg ID
# silently pulling in the wrong text). Most fixes are folder renames (old
# folder deleted, new one added), which git handles cleanly since .dockg/ is
# gitignored everywhere. Two books were corrected *in place* (same folder
# name, corrected content) — for those, a plain `ingest` would skip the
# rebuild and keep serving the old wrong embeddings, so they need
# --force-build explicitly.
#
# Usage: scripts/resync_catalog_fix.sh [branch]
#   branch  Branch to pull (default: fix/catalog). Use "main" once merged.

set -euo pipefail

BRANCH="${1:-fix/catalog}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Genres with an in-place content fix (same folder name) — need --force-build
# so ingest doesn't skip the stale .dockg it finds already sitting there.
FORCE_GENRES=(science-fiction)

# Genres with renamed/replaced book folders — old .dockg went away with the
# old folder, so a plain ingest builds the new one fine.
PLAIN_GENRES=(
  ancient-classical biography drama english-literature german-literature
  letters russian-literature travel
)

echo "== 1/4: sync code =="
git fetch origin
git checkout "$BRANCH"
git pull

echo
echo "== 2/4: resolve gutenkg =="
if [[ -x "$REPO_ROOT/.venv/bin/gutenkg" ]]; then
  GUTENKG="$REPO_ROOT/.venv/bin/gutenkg"
else
  echo "!! $REPO_ROOT/.venv/bin/gutenkg not found — run 'poetry install' (or"
  echo "   'pip install -e .') in this repo first." >&2
  exit 1
fi
if command -v gutenkg >/dev/null && [[ "$(command -v gutenkg)" != "$GUTENKG" ]]; then
  echo "!! NOTE: bare 'gutenkg' on PATH resolves to $(command -v gutenkg),"
  echo "   not this repo's venv. Using the explicit path below to avoid a"
  echo "   stale/unrelated install."
fi
echo "using: $GUTENKG ($("$GUTENKG" --version))"

echo
echo "== 3/4: rebuild per-book DocKG indices =="
echo "-- force-rebuild (in-place content fixes): ${FORCE_GENRES[*]}"
force_args=()
for g in "${FORCE_GENRES[@]}"; do force_args+=(--genre "$g"); done
"$GUTENKG" ingest "${force_args[@]}" --force-build

echo "-- plain ingest (renamed folders, no stale index to bust): ${PLAIN_GENRES[*]}"
plain_args=()
for g in "${PLAIN_GENRES[@]}"; do plain_args+=(--genre "$g"); done
"$GUTENKG" ingest "${plain_args[@]}"

echo
echo "== 4/4: refresh the consolidated bundle =="
"$GUTENKG" build-corpus --update

echo
echo "== orphaned .dockg dirs (old renamed-away book folders left behind) =="
found=0
while IFS= read -r -d '' dockg_dir; do
  book_dir="$(dirname "$dockg_dir")"
  # Flag it only if .dockg is the *only* thing left in the book folder.
  if [[ "$(ls -A "$book_dir")" == ".dockg" ]]; then
    echo "  $book_dir"
    found=1
  fi
done < <(find corpus -mindepth 3 -maxdepth 3 -type d -name .dockg -print0)
if [[ "$found" -eq 0 ]]; then
  echo "  (none)"
else
  echo "  ^ safe to 'rm -rf' — their tracked markdown is gone, only the old index remains."
fi

echo
echo "done."
