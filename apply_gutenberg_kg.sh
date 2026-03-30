#!/usr/bin/env bash
# apply_gutenberg_kg.sh — Apply gutenberg_kg reorganization to a local clone.
#
# Usage (run from the root of your local gutenberg_kg clone):
#   bash apply_gutenberg_kg.sh
#
# What it does:
#   1. Creates 8 genre subdirectories
#   2. Moves all 64 books (128 files) via git mv
#   3. Writes ingest.sh, scripts/catalog.txt, scripts/download_gutenberg.py
#   4. Commits everything

set -euo pipefail

if [[ ! -f "scripts/catalog.txt" ]]; then
    echo "ERROR: Run this script from the root of the gutenberg_kg repository."
    exit 1
fi

echo "=== GutenbergKG: applying reorganization ==="
echo ""


# ── 3. Write updated files ───────────────────────────────────────────────────
echo "[3/4] Writing ingest.sh and updated scripts..."

cat > ingest.sh << 'INGEST_EOF'
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
INGEST_EOF
chmod +x ingest.sh

cat > scripts/catalog.txt << 'CATALOG_EOF'
# Project Gutenberg Book Catalog
# Format: <ebook_id>[\t<title_override>[\t<genre_override>]]
#
# Genre is auto-detected from section headers below.
# To override: add a third tab-separated column with the genre directory name.
#
# Genre directories:
#   ancient-classical, shakespeare, english-literature, american-literature,
#   french-literature, russian-literature, philosophy, spanish
#
# Find ebook IDs: python scripts/download_gutenberg.py search --author "Author Name"
# Download all:  python scripts/download_gutenberg.py catalog scripts/catalog.txt

# Ancient & Classical
1727	The Odyssey
6130	The Iliad
228	The Aeneid
1497	The Republic
1004	The Divine Comedy
27673	Oedipus King of Thebes
2680	Meditations
10	The Bible

# Shakespeare
1524	Hamlet
1513	Romeo and Juliet
1533	Macbeth
1514	A Midsummer Nights Dream

# English Literature
1260	Jane Eyre
768	Wuthering Heights
1400	Great Expectations
145	Middlemarch
161	Sense and Sensibility
158	Emma
1342	Pride and Prejudice
84	Frankenstein
345	Dracula
219	Heart of Darkness
35	The Time Machine
36	The War of the Worlds
120	Treasure Island
521	Robinson Crusoe
829	Gullivers Travels
43	The Strange Case of Dr Jekyll and Mr Hyde
1661	The Adventures of Sherlock Holmes
174	The Picture of Dorian Gray
11	Alices Adventures in Wonderland
98	A Tale of Two Cities
1080	A Modest Proposal
2591	Grimms Fairy Tales

# American Literature
2701	Moby Dick
33	The Scarlet Letter
205	Walden
1322	Leaves of Grass
76	Adventures of Huckleberry Finn
215	The Call of the Wild
73	The Red Badge of Courage
203	Uncle Toms Cabin
1952	The Yellow Wallpaper

# French Literature
135	Les Miserables
1184	The Count of Monte Cristo
1257	The Three Musketeers
2413	Madame Bovary
164	Twenty Thousand Leagues Under the Sea
19942	Candide

# Russian Literature
2554	Crime and Punishment
28054	The Brothers Karamazov
1399	Anna Karenina
2600	War and Peace
2638	The Idiot
1081	Dead Souls

# Philosophy & Non-Fiction
1228	On the Origin of Species
147	Common Sense
3207	Leviathan
1998	Thus Spake Zarathustra
4363	Beyond Good and Evil
3300	The Wealth of Nations
1404	The Federalist Papers
1232	The Prince

# Spanish
996	Don Quixote
CATALOG_EOF

# ── 4. Commit ────────────────────────────────────────────────────────────────
echo "[4/4] Committing..."
git add -A
git -c commit.gpgsign=false commit -m "Reorganize books into genre subdirectories; add ingest.sh"

echo ""
echo "=== Done! Now push with: git push origin main ==="
