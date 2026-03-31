#!/usr/bin/env bash
# push.sh — Commit and push DocKG changes in per-genre batches.
#
# Usage:
#   bash scripts/push.sh [GENRE ...]
#
# Examples:
#   bash scripts/push.sh                          # all genres
#   bash scripts/push.sh american-literature      # one genre
#   bash scripts/push.sh shakespeare philosophy   # several genres
#
# Each genre that has staged changes gets its own commit and push.
# Genres with no changes are skipped silently.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ALL_GENRES=(
    ancient-classical
    shakespeare
    english-literature
    american-literature
    french-literature
    russian-literature
    philosophy
    spanish
)

GENRES=("${@:-${ALL_GENRES[@]}}")

# Validate genre names
for genre in "${GENRES[@]}"; do
    valid=0
    for g in "${ALL_GENRES[@]}"; do
        [[ "$g" == "$genre" ]] && valid=1 && break
    done
    if [[ $valid -eq 0 ]]; then
        echo "ERROR: unknown genre '$genre'" >&2
        echo "Valid genres: ${ALL_GENRES[*]}" >&2
        exit 1
    fi
done

echo "=== Gutenberg KG — genre batch push ==="
echo "Genres: ${GENRES[*]}"
echo

pushed=0
skipped=0

for genre in "${GENRES[@]}"; do
    genre_dir="$REPO_ROOT/$genre"

    if [[ ! -d "$genre_dir" ]]; then
        echo "[$genre] directory not found — skipping"
        continue
    fi

    # Stage everything under this genre
    git add "$genre_dir/"

    # Check if there's anything to commit
    if git diff --cached --quiet; then
        echo "[$genre] nothing to commit — skipping"
        ((skipped++)) || true
        continue
    fi

    # Count changed files for the commit message
    n_files=$(git diff --cached --name-only | wc -l | tr -d ' ')

    echo "[$genre] committing $n_files file(s)..."
    git commit -m "$(cat <<EOF
chore(dockg): rebuild $genre DocKG indices ($n_files files)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"

    echo "[$genre] pushing..."
    git push

    echo "[$genre] done"
    echo
    ((pushed++)) || true
done

echo "=== Summary: $pushed genre(s) pushed, $skipped skipped ==="
