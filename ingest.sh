#!/usr/bin/env bash
# ingest.sh — Build a DocKG for each genre directory and register them all
# under a "gutenberg" corpus in KGRAG.
#
# Usage (from the gutenberg_kg repo root):
#   bash ingest.sh [--wipe]
#
# Prerequisites:
#   pip install kg-rag   OR   use the KGRAG repo with poetry run kgrag
#   kgrag corpus create gutenberg --desc "Project Gutenberg library"
#
# Each genre directory gets its own .dockg/ (SQLite + LanceDB), registered as
# "gutenberg-<genre>" and added to the "gutenberg" corpus.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIPE="${1:-}"
CORPUS="gutenberg"

GENRES=(
    ancient-classical
    shakespeare
    english-literature
    american-literature
    french-literature
    russian-literature
    philosophy
    spanish
)

echo "=== GutenbergKG Ingest ==="
echo "Repo: $REPO_ROOT"
[[ "$WIPE" == "--wipe" ]] && echo "Mode: WIPE + rebuild"
echo ""

# Ensure corpus exists
if ! kgrag corpus info "$CORPUS" &>/dev/null 2>&1; then
    echo "Creating corpus '$CORPUS'..."
    kgrag corpus create "$CORPUS" --desc "Project Gutenberg library"
fi

for GENRE in "${GENRES[@]}"; do
    GENRE_DIR="$REPO_ROOT/$GENRE"
    KG_NAME="gutenberg-$GENRE"

    echo "--- $GENRE ---"

    if [[ ! -d "$GENRE_DIR" ]]; then
        echo "  [!] Directory not found: $GENRE_DIR - skipping"
        echo ""
        continue
    fi

    MD_COUNT=$(find "$GENRE_DIR" -name "*.md" ! -name "README.md" | wc -l)
    if [[ "$MD_COUNT" -eq 0 ]]; then
        echo "  [!] No .md files found - skipping"
        echo ""
        continue
    fi

    echo "  [.] $MD_COUNT .md files"

    # Wipe existing .dockg if requested
    if [[ "$WIPE" == "--wipe" ]] && [[ -d "$GENRE_DIR/.dockg" ]]; then
        rm -rf "$GENRE_DIR/.dockg"
        echo "  [.] Wiped existing .dockg"
    fi

    # Build DocKG
    if ! command -v dockg &>/dev/null; then
        echo "  [!] dockg not found - skipping build (install doc-kg first)"
        echo ""
        continue
    fi

    echo "  [.] Building DocKG..."
    if dockg build --repo "$GENRE_DIR"; then
        echo "  [+] DocKG built"
    else
        echo "  [x] dockg build failed"
        echo ""
        continue
    fi

    # Register with kgrag
    SQLITE="$GENRE_DIR/.dockg/graph.sqlite"
    LANCEDB="$GENRE_DIR/.dockg/lancedb"
    ARGS=(kgrag register "$KG_NAME" doc "$GENRE_DIR")
    [[ -f "$SQLITE" ]]  && ARGS+=(--sqlite  "$SQLITE")
    [[ -d "$LANCEDB" ]] && ARGS+=(--lancedb "$LANCEDB")

    if "${ARGS[@]}" 2>&1; then
        echo "  [+] Registered: $KG_NAME"
    else
        echo "  [!] Already registered (continuing)"
    fi

    # Add to corpus
    kgrag corpus add "$CORPUS" "$KG_NAME" 2>&1 && echo "  [+] Added to corpus: $CORPUS" || true

    echo ""
done

echo "=== Done ==="
echo ""
echo "Query your library:"
echo "  kgrag corpus query gutenberg \"your question\""
echo "  kgrag synthesize \"your question\" --corpus gutenberg"
echo "  kgrag viz"
