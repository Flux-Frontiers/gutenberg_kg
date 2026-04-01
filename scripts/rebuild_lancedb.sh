#!/usr/bin/env bash
# rebuild_lancedb.sh — Rebuild LanceDB vector indices from graph.sqlite after cloning.
#
# LanceDB is not committed to git (too large). Run this once after cloning to
# reconstruct the vector indices from the committed graph.sqlite files.
#
# Usage:
#   bash scripts/rebuild_lancedb.sh [GENRE ...]
#
# Examples:
#   bash scripts/rebuild_lancedb.sh                    # all genres
#   bash scripts/rebuild_lancedb.sh american-literature
#   bash scripts/rebuild_lancedb.sh shakespeare philosophy

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

echo "=== Gutenberg KG — LanceDB rebuild ==="
echo "Genres: ${GENRES[*]}"
echo

total=0
failed=0

for genre in "${GENRES[@]}"; do
    genre_dir="$REPO_ROOT/$genre"
    [[ -d "$genre_dir" ]] || { echo "[!] $genre: directory not found — skipping"; continue; }

    echo "--- $genre ---"
    for book_dir in "$genre_dir"/*/; do
        [[ -d "$book_dir" ]] || continue
        book_name="$(basename "$book_dir")"
        sqlite="$book_dir/.dockg/graph.sqlite"
        lancedb="$book_dir/.dockg/lancedb"

        # Skip if no sqlite (book not yet ingested)
        if [[ ! -f "$sqlite" ]]; then
            echo "  [$book_name] no graph.sqlite — skipping"
            continue
        fi

        # Skip if lancedb already exists
        if [[ -d "$lancedb" ]]; then
            echo "  [$book_name] lancedb already exists — skipping"
            continue
        fi

        echo "  [$book_name] rebuilding..."
        if dockg build --repo "$book_dir" 2>&1; then
            echo "  [$book_name] done"
            ((total++)) || true
        else
            echo "  [$book_name] FAILED"
            ((failed++)) || true
        fi
    done
    echo
done

echo "=== Done: $total rebuilt, $failed failed ==="
[[ $failed -eq 0 ]] || echo "[!] Re-run to retry failed books."
exit $failed
