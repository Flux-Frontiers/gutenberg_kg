#!/usr/bin/env bash
# ingest.sh — Build a per-book DocKG for every book in every genre, register
# each as "gutenberg-<genre>-<book-slug>" and add it to two corpora:
#   - gutenberg-<genre>   (genre-level queries)
#   - gutenberg-all       (full library federation)
#
# Usage (from the gutenberg_kg repo root):
#   bash ingest.sh [--wipe]
#
# Prerequisites:
#   pip install kg-rag   OR   poetry run kgrag (from the kgrag repo)
#
# Each book directory gets its own .dockg/ (SQLite + LanceDB).
# Query examples:
#   kgrag query "your question" --kind doc
#   kgrag corpus query gutenberg-shakespeare "to be or not to be"
#   kgrag corpus query gutenberg-all "hubris and fate"

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIPE=""
DRY_RUN=""

for ARG in "$@"; do
    case "$ARG" in
        --wipe)     WIPE="--wipe" ;;
        --dry-run)  DRY_RUN="1" ;;
    esac
done

GENRES=(
    ancient-classical
    shakespeare
    english-literature
    american-literature
    french-literature
    russian-literature
    philosophy
    spanish
    science-fiction
)

echo "=== GutenbergKG Ingest (per-book) ==="
echo "Repo: $REPO_ROOT"
[[ "$WIPE" == "--wipe" ]] && echo "Mode: WIPE + rebuild"
[[ -n "$DRY_RUN" ]] && echo "Mode: DRY RUN (no changes)"
echo ""

if ! command -v kgrag &>/dev/null; then
    echo "ERROR: kgrag not found — install kg-rag first"
    exit 1
fi

# slugify: lowercase, replace spaces/special chars with hyphens
slugify() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/-\+/-/g' | sed 's/^-\|-$//g'
}

# Ensure top-level corpora exist (idempotent)
echo "--- Ensuring corpora exist ---"
for GENRE in "${GENRES[@]}"; do
    if [[ -n "$DRY_RUN" ]]; then
        echo "  [dry] kgrag corpus create gutenberg-$GENRE"
    else
        kgrag corpus create "gutenberg-$GENRE" 2>/dev/null && echo "  [+] corpus: gutenberg-$GENRE" || echo "  [=] exists: gutenberg-$GENRE"
    fi
done
if [[ -n "$DRY_RUN" ]]; then
    echo "  [dry] kgrag corpus create gutenberg-all"
else
    kgrag corpus create "gutenberg-all" 2>/dev/null && echo "  [+] corpus: gutenberg-all" || echo "  [=] exists: gutenberg-all"
fi
echo ""

TOTAL_OK=0
TOTAL_FAIL=0

for GENRE in "${GENRES[@]}"; do
    GENRE_DIR="$REPO_ROOT/$GENRE"
    GENRE_CORPUS="gutenberg-$GENRE"

    echo "=== $GENRE ==="

    if [[ ! -d "$GENRE_DIR" ]]; then
        echo "  [!] Directory not found: $GENRE_DIR — skipping"
        echo ""
        continue
    fi

    while IFS= read -r -d '' BOOK_DIR; do
        BOOK_NAME="$(basename "$BOOK_DIR")"
        BOOK_SLUG="$(slugify "$BOOK_NAME")"
        KG_NAME="gutenberg-${GENRE}-${BOOK_SLUG}"

        echo "  --- $BOOK_NAME ---"

        INIT_ARGS=(kgrag init "$BOOK_DIR" --layer doc --name "$KG_NAME" --corpus "$GENRE_CORPUS")
        [[ "$WIPE" == "--wipe" ]] && INIT_ARGS+=(--wipe)

        if [[ -n "$DRY_RUN" ]]; then
            echo "    [dry] ${INIT_ARGS[*]}"
            echo "    [dry] kgrag corpus add gutenberg-all ${KG_NAME}-doc"
            (( TOTAL_OK++ )) || true
        elif "${INIT_ARGS[@]}"; then
            echo "    [+] Registered: $KG_NAME"
            kgrag corpus add "gutenberg-all" "${KG_NAME}-doc" 2>/dev/null && echo "    [+] Added to gutenberg-all" || true
            (( TOTAL_OK++ )) || true
        else
            echo "    [x] Failed: $KG_NAME"
            (( TOTAL_FAIL++ )) || true
        fi

    done < <(find "$GENRE_DIR" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

    echo ""
done

echo "=== Done ==="
echo "  OK: $TOTAL_OK  Failed: $TOTAL_FAIL"
echo ""
echo "Query your Gutenberg library:"
echo "  kgrag query \"your question\" --kind doc"
echo "  kgrag corpus query gutenberg-shakespeare \"ambition and power\""
echo "  kgrag corpus query gutenberg-all \"the nature of justice\""
echo "  kgrag list"
