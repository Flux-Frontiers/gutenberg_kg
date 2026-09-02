# GutenbergKG Cheatsheet

Quick reference for downloading, ingesting, and managing the corpus.

Use the `gutenkg` CLI (after `poetry install`).

> **Planning additions?** See [`CORPUS_WISHLIST.md`](CORPUS_WISHLIST.md) for the curated list of high-priority books organized by genre, with Gutenberg IDs and a checkbox per book. Pre-built catalog files for each genre live in [`scripts/catalogs/`](../scripts/catalogs/).

---

## Installation

```bash
deactivate          # make sure no other venv is active
poetry env use python3.12
poetry install --extras "kgdeps viz viz3d mcp"
gutenkg --help
```

Dev tooling (pytest, ruff, ty, pre-commit) is a Poetry group rather than
an extra, so add `--with dev` if you're working on the repo itself. Full
options: [`INSTALLATION.md`](INSTALLATION.md).

---

## Genres

Genres are stored in `corpus/genres.json`. Add new genres without touching code.

```bash
gutenkg genres init                              # seed corpus/genres.json (first time)
gutenkg genres list                              # show registered genres
gutenkg genres add medieval-lit --source gutenberg   # add a Gutenberg genre
gutenkg genres add my-ia-collection --source ia      # add an Internet Archive genre
```

`genres add` auto-initializes the file if it doesn't exist yet.

---

## Downloading Books

### Search

```bash
gutenkg download search "science fiction"
gutenkg download search --author "Mary Shelley"
gutenkg download search --title "Frankenstein"
gutenkg download search --subject "dystopia" --max-results 10

# Note: Gutenberg's search endpoint is slow — prefer catalogs (see below)
```

### Download a single book

```bash
gutenkg download book 84 --genre science-fiction
gutenkg download book 84 --genre science-fiction --dry-run
gutenkg download book 84 --genre science-fiction --force
```

### Batch download from catalog

Pre-built genre catalogs live in `scripts/catalogs/`. Preferred over search.

```bash
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction --dry-run
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction --force
```

Catalog format: one book per line, `<gutenberg_id>[TAB<optional title>]`. Lines starting with `#` are comments.

### Fetch an entire genre in one step

```bash
# Interactive (Enter=yes, n=skip, q=quit)
gutenkg download fetch-genre science-fiction

# Custom search query
gutenkg download fetch-genre science-fiction --query "dystopia"

# Download all without prompting
gutenkg download fetch-genre science-fiction --yes

# Preview only
gutenkg download fetch-genre science-fiction --dry-run
```

Reports saved to `reports/fetch_genre_<genre>_<timestamp>.md`.

### Survey what's downloaded

```bash
gutenkg download survey
gutenkg download survey --genre science-fiction
```

Output shows `md=✓/✗  ref=✓/✗  kg=✓/✗` per book.

---

## Building Knowledge Graphs (Ingest)

### Build all genres

```bash
gutenkg ingest
```

### Build specific genre(s)

```bash
gutenkg ingest --genre science-fiction
gutenkg ingest --genre shakespeare --genre philosophy
```

### Force rebuild (wipes existing .dockg first)

```bash
gutenkg ingest --force-build
gutenkg ingest --force-build --genre american-literature
```

### Build and push to git (per-genre commits)

```bash
gutenkg ingest --push
gutenkg ingest --force-build --push
gutenkg ingest --genre science-fiction --push
```

### Dry run (preview only)

```bash
gutenkg ingest --dry-run
gutenkg ingest --dry-run --push
```

### Re-register with KGRAG (without rebuilding)

```bash
gutenkg ingest --force-register
gutenkg ingest --force-register --genre philosophy
```

Reports are auto-saved to `reports/ingest_YYYY-MM-DD_HHMMSS.md` after every run.

---

## Author Index

Every `reference.md` carries author provenance (Born / Died / Wikipedia /
Gutenberg agent ID). `corpus/authors/` aggregates those per-book facts into
one page per author.

```bash
# Rebuild corpus/authors/ from existing reference.md files
gutenkg authors

# Also re-fetch RDF and patch reference.md files missing provenance
gutenkg authors --refresh

# Preview
gutenkg authors --dry-run
gutenkg authors --refresh --dry-run
```

New downloads already land with full provenance in `reference.md` — use
`--refresh` only for books that predate the RDF fetch or had a transient
network failure.

---

## After Cloning (Rebuild Indices)

Knowledge graph indices are not committed to git. After cloning, rebuild them:

```bash
gutenkg rebuild-indices
gutenkg rebuild-indices --genre science-fiction
gutenkg rebuild-indices --genre shakespeare --genre philosophy
```

---

## Querying the Corpus

`gutenkg query` searches the locally ingested corpus through KGRAG — no Docker,
no LLM. Run `gutenkg ingest` first so the per-book indices exist and are
registered.

```bash
gutenkg query "the nature of justice"                        # whole corpus
gutenkg query "revenge" --corpus gutenberg-russian-literature  # one genre corpus
gutenkg query "the Great Fire" --k 20                        # results per KG (default 8)
gutenkg query "plague" --json                                # machine-readable
gutenkg query "plague" --registry /path/to/registry.json     # non-default registry
```

| Option | Default | Meaning |
|---|---|---|
| `--corpus` | `gutenberg-all` | Registered corpus to search |
| `--k` | `8` | Results per knowledge graph |
| `--registry` | KGRAG default | Override the local registry path |
| `--json` | off | Emit KGRAG results as JSON |

---

## On-Device Corpus Packs

Build the SQLite packs the native app searches locally (see
[On-device corpus packs](ON_DEVICE.md)).

```bash
gutenkg export-swift                      # → bundles/gutenberg-all/swift/
gutenkg export-swift --verify             # report int8 recall while building
gutenkg export-swift --dtype float        # exact vectors, ~3x larger
gutenkg export-swift --no-vectors --no-golden   # fast schema-only pass
```

Produces `core.pack`, `gutenberg.pack`, `diaries.pack`, a `manifest.json`, and
a `golden.json` parity file. Only chunk and section nodes are carried over —
the query path reads nothing else — so a 5.7 GB bundle lands around 1.3 GB.

## Visualisation and Light-Field Rendering

`viz3d` and `quilt` need the 3-D extra: `poetry install --extras viz3d`. The
2-D growth timeline at the end of this section needs `--extras viz` instead.

### The interactive forest — `gutenkg viz3d`

```bash
gutenkg viz3d                                    # whole ingested corpus
gutenkg viz3d --corpus corpus --width 1920 --height 1200
```

Every ingested book (one with a `.dockg/graph.sqlite`) becomes a tree: trunk =
document, branches = sections, leaves = chunks, grouped into genre groves.
Right-click a node to read its text. Two controls in the panel matter most:

- **Organic tree (one book)** — filter to a single book, then tick this to grow
  it by space colonization instead of drawing the schematic spiral. The limbs
  reach the book's own chunks, so the canopy's shape is the book's structure;
  branch radii follow the pipe model. Picking is disabled in this mode — the
  scene is swept wood and batched leaf glyphs, not per-node actors.
- **Cast to LG** — render whatever is on screen as a quilt and send it to
  Looking Glass Bridge (16" Gen3 Landscape, at half resolution for speed).

The season selector applies to the organic tree; `summer` is the default.

### Light-field quilts — `gutenkg quilt`

```bash
gutenkg quilt --book Hamlet                       # 48 views, one 7680x4320 quilt
gutenkg quilt --book Hamlet --season autumn       # spring, summer, autumn, winter
gutenkg quilt --book Hamlet --entities --zoom 1.2 # add the gold entity spores
gutenkg quilt --book Hamlet --spec portrait       # another device preset
gutenkg quilt --book Pepys --orbit 180 --cast     # 180-frame turntable, to the display
gutenkg quilt --book Hamlet --schematic           # the spiral layout instead
```

The stereo depth budget is printed **before** every render, so an over-wide
disparity shows up at no cost rather than after all 48 views. A quilt is an
ordinary PNG; nothing here needs a Looking Glass panel except `--cast`.

| Option | Default | Meaning |
|---|---|---|
| `--book` | *(required)* | Title, or a unique fragment of one |
| `--genre` | all | Restrict the book search to one genre |
| `--spec` | `16-landscape` | Quilt preset (`16-landscape`, `16-portrait`, `portrait`, `go`, `27-*`, `32-*`, `65`) |
| `--out` | `renders/quilts` | Output directory |
| `--season` | `summer` | Foliage palette; `winter` drops 90% of leaves, baring the wood |
| `--schematic` | off | Original spiral layout instead of the grown tree |
| `--entities` / `--topics` | off | Gold entity spores / blue topic pollen |
| `--leaf-size` | `0.32` before density scaling | Leaves shrink by the cube root of chunk count; raise for a dense book |
| `--zoom` | `1.0` | Camera dolly after framing — this is what drives depth |
| `--fov` | `14.0` | Per-view vertical FOV; Looking Glass recommends ~14 |
| `--orbit` | `0` | Render a turntable quilt **video** of this many frames |
| `--fps` | `24` | Frame rate for `--orbit` |
| `--cast` | off | Send the finished quilt to Looking Glass Bridge |

Rendering is deterministic: the growth seed comes from the book's slug, so a
book grows the same tree in every session and every render.

### The growth timeline — `gutenkg viz-timeline`

Plots books, authors, nodes, and edges over time from the saved snapshots, so
run `gutenkg snapshot save` at least twice first.

```bash
gutenkg viz-timeline                             # 2x2 Plotly subplot grid
gutenkg viz-timeline --type 3d                   # normalized multi-metric scatter
gutenkg viz-timeline --snapshots path/to/.snapshots
```

---

## Git / Pushing

Pushes are handled automatically by `gutenkg ingest --push` (one commit per genre).
For manual pushes:

```bash
git add corpus/science-fiction/
git commit -m "chore: add science-fiction books"
git push
```

Only source Markdown and `reference.md` files are tracked. Knowledge-graph
artifacts (`.dockg/graph.sqlite` and `.dockg/vectors.sqlite`) are gitignored —
they are regenerable from the source text via `gutenkg ingest --force-build`.

---

## Corpus-Grounded Image Generation

`gutenkg imagine` generates illustrations grounded in the corpus — no cloud
API. It runs a three-stage local pipeline, with the last stage served by a
local image server (`make image-server` on Apple Silicon, `make sdxl-server`
elsewhere):

1. **DiaryKG / DocKG retrieval** — the most relevant passages are pulled from
   the knowledge graph for your query.
2. **VLM rewrite (oMLX)** — a local Qwen3 model rewrites the prose into a
   clean visual scene description (prevents garbled text in the image).
3. **FLUX.2-Klein generation (mflux)** — the scene description is rendered by
   a 4-bit quantised FLUX.2-Klein model (~15–22 s on Apple Silicon).

### Installation

#### 1. Python install

```bash
# The image service (fastapi/uvicorn) — Poetry or pip
poetry install --extras image
pip install -e ".[image]"

# Optional: MCP server support (Claude Code / Cursor)
poetry install --extras mcp
```

There is no `imagine` extra. The generation backend itself is **not** a
dependency of this package: mflux pins a `transformers` version that conflicts
with pycode-kg, so `make image-server` builds an isolated `.venv-image` from
`docker/requirements-image.txt` instead. Run that once, then use `gutenkg
imagine` normally.

#### 2. oMLX — local VLM server

oMLX is an OpenAI-compatible local inference server for MLX models. The VLM
rewrite step calls it on `http://localhost:8080/v1`.

Install and start oMLX with any Qwen3 model (30B recommended, 4B works too):

```bash
# Install oMLX (requires Python 3.11+)
pip install omlx          # or: pip install git+https://github.com/omlx/omlx

# Start with the model used by gutenkg imagine (adjust path to your MLX model)
omlx serve mlx-community/Qwen3-30B-A3B-Instruct-2507-MLX-4bit --port 8080

# Verify it's up
curl http://localhost:8080/v1/models
```

> **Tip:** If oMLX is down when you run `gutenkg imagine --query ...`, the VLM
> rewrite step is skipped gracefully and the raw corpus text is passed to FLUX
> instead (use `--no-vlm` to make this explicit).

#### 3. FLUX.2-Klein model

The image model downloads automatically from HuggingFace on first use
(~4 GB, cached to `~/.cache/huggingface/hub/`):

```
mlx-community/flux2-klein-4b-4bit
```

To pre-download manually:

```bash
huggingface-cli download mlx-community/flux2-klein-4b-4bit
```

No HuggingFace account or license acceptance is required for this model.

#### 4. MCP server (optional — Claude Code / Cursor)

To expose `generate_image` and `corpus_imagine` as MCP tools, first install
the MCP extra, then add the
`gutenkg` server to your `.mcp.json` in the repo root:

```bash
pip install -e ".[mcp]"
```

```json
{
  "mcpServers": {
    "gutenkg": {
      "command": "/path/to/repo/.venv/bin/gutenkg-mcp",
      "env": {
        "GUTENKG_IMAGE_MODEL": "mlx-community/flux2-klein-4b-4bit",
        "GUTENKG_IMAGE_STEPS": "4"
      }
    }
  }
}
```

Replace `/path/to/repo` with the absolute path to your `gutenberg_kg` checkout.
After saving, reload the MCP server in your editor. The tools appear as
`gutenkg / generate_image` and `gutenkg / corpus_imagine`.

### Basic usage

```bash
# Direct prompt — no corpus lookup
gutenkg imagine "the Great Fire of London at night, oil painting"

# Corpus-grounded — retrieve Pepys diary passages, rewrite via VLM, generate
gutenkg imagine --query "great fire" --book pepys

# Choose aspect ratio and quality
gutenkg imagine --query "great fire" --book pepys --ratio 16:9 --steps 8

# Save to a specific path instead of a temp file
gutenkg imagine --query "plague in London" --book pepys -o plague.png

# Reproducible output (fixed seed)
gutenkg imagine --query "great fire" --book pepys --seed 42

# Skip VLM rewrite (faster, but raw corpus prose fed to FLUX)
gutenkg imagine --query "great fire" --book pepys --no-vlm

# Inspect the retrieved corpus text without generating
gutenkg imagine --query "great fire" --book pepys --corpus-only
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--query`/`-q` | — | Semantic query into the corpus (DiaryKG or prose DocKG) |
| `--book`/`-b` | — | Restrict corpus search to books matching this substring (e.g. `pepys`, `evelyn`) |
| `--ratio`/`-r` | `3:2` | Aspect ratio: `1:1`, `3:2`, `2:3`, `16:9`, `9:16`, `4:3`, `3:4` |
| `--steps` | `4` | Inference steps — 4 (fast, ~15 s) · 8 (balanced, ~22 s) · 25 (quality) |
| `--seed`/`-s` | random | Integer seed for reproducible outputs |
| `--output`/`-o` | temp file | Save PNG to this path |
| `--no-vlm` | off | Skip the VLM rewrite step (pass corpus text directly to FLUX) |
| `--corpus-only` | off | Print retrieved corpus text and exit — no image generated |
| `--no-open` | off | Do not open the image after saving |

### MCP tool (Claude Code / Cursor)

The same pipeline is exposed as two MCP tools via the `gutenkg-mcp` server,
configured in `.mcp.json`:

```
generate_image(prompt, aspect_ratio, seed, steps)
    → Direct text-to-image, no corpus lookup.

corpus_imagine(query, book, extra_prompt, aspect_ratio, seed, steps)
    → Retrieve corpus passages → VLM rewrite → FLUX generation.
      extra_prompt appends style/scene notes to the VLM input.
```

In Claude Code chat you can say: *"Create an image of the Great Fire based on
Pepys' description"* and the `corpus_imagine` tool handles the full pipeline.

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GUTENKG_IMAGE_MODEL` | `mlx-community/flux2-klein-4b-4bit` | HuggingFace model repo for FLUX |
| `GUTENKG_IMAGE_STEPS` | `4` | Default inference steps |

---

## Typical Workflows

### Expand the corpus (standard batch cycle)

This is the day-to-day workflow for adding books from the wishlist.

```bash
# 1. Pick books to add — check CORPUS_WISHLIST.md for the curated list
#    Each genre has a pre-built catalog in scripts/catalogs/

# 2. If adding a brand-new genre, register it first (one-time)
gutenkg genres add german-literature --source gutenberg   # Gutenberg source
gutenkg genres add my-ia-collection --source ia           # Internet Archive source

# 3. Download the catalog (run from repo root)
gutenkg download catalog scripts/catalogs/philosophy.txt --genre philosophy

# 4. Ingest — builds DocKG indices + registers with KGRAG
gutenkg ingest --genre philosophy

# 5. Check off completed items in CORPUS_WISHLIST.md

# 6. Refresh the author index
gutenkg authors

# 7. Commit and push
git add corpus/philosophy/
git commit -m "feat: add philosophy wishlist batch"
git push
```

Multi-genre batch (download all, then ingest all at once):

```bash
gutenkg download catalog scripts/catalogs/ancient-classical.txt --genre ancient-classical
gutenkg download catalog scripts/catalogs/french-literature.txt --genre french-literature
gutenkg download catalog scripts/catalogs/russian-literature.txt --genre russian-literature
gutenkg ingest   # rebuilds only what's new; skips already-built books
```

### Add a new genre from scratch

```bash
# 1. Register the genre (no code changes needed)
gutenkg genres add medieval-literature --source gutenberg

# 2. Create a catalog file
#    scripts/catalogs/medieval-literature.txt
#    Format: <gutenberg_id>[TAB<title>]  — see existing files for examples

# 3. Download via catalog
gutenkg download catalog scripts/catalogs/medieval-literature.txt --genre medieval-literature

# 4. Survey what you have
gutenkg download survey --genre medieval-literature

# 5. Build DocKGs and register with KGRAG
gutenkg ingest --genre medieval-literature

# 6. Refresh the author index
gutenkg authors
```

### Rebuild a broken genre

```bash
gutenkg ingest --force-build --genre philosophy
```

### Full corpus rebuild

```bash
gutenkg ingest --force-build
```

### Check ingest status across corpus

```bash
gutenkg download survey
```

---

## File Layout

```
gutenberg_kg/
├── corpus/
│   ├── genres.json                         # Genre registry — edit here to add genres
│   ├── <genre>/                            # ancient-classical, philosophy, …
│   │   └── <Book Title>/
│   │       ├── <slug>.md                   # Full text (Markdown)
│   │       ├── reference.md                # Author provenance + Gutenberg metadata
│   │       └── .dockg/                     # Built by ingest (gitignored)
│   │           ├── graph.sqlite            # Graph database
│   │           └── vectors.sqlite          # Vector index (sqlite-vec)
│   ├── diaries/                            # Diary corpora (Pepys, Evelyn, …)
│   │   └── <Diary Title>/
│   │       ├── .diary/                     # Timestamped chunks (built by build-diaries)
│   │       └── .diarykg/                   # DiaryKG indices (gitignored)
│   │           ├── corpus -> ../.diary     # Symlink to chunk directory
│   │           ├── graph.sqlite
│   │           └── vectors.sqlite
│   └── authors/                            # Built by `gutenkg authors`
│       ├── index.md                        # Master alphabetical author table
│       └── <author_slug>/author.md         # Born, died, Wikipedia, works
├── src/gutenberg_kg/
│   ├── __init__.py
│   ├── audit.py                            # Corpus audit checks (gutenkg audit)
│   ├── authors.py                          # Author-index logic
│   ├── build_corpus.py                     # Consolidated bundle build orchestration
│   ├── build_diaries.py                    # Diary ingest + DiaryKG build
│   ├── corpus.py                           # Corpus model
│   ├── genres.py                           # Loads genres.json; exposes ALL_GENRES
│   ├── gutenberg.py                        # Project Gutenberg download + RDF
│   ├── ia.py                               # Internet Archive download
│   ├── image_gen.py                        # FLUX.2-Klein wrapper (gutenkg imagine)
│   ├── ingest.py                           # DocKG ingest + KGRAG registration
│   ├── layout_organic.py                   # Space colonization, pipe radii, tube sweep
│   ├── mcp_server.py                       # MCP server (gutenkg-mcp entry point)
│   ├── model_setup.py                      # Local model download (gutenkg init)
│   ├── scene.py                            # Qt-free scene builder + seasons
│   ├── vector_store.py                     # sqlite-vec / LanceDB store resolution
│   ├── viz3d.py                            # 3-D KG visualisation (Qt viewer)
│   ├── viz_timeline.py                     # 2-D timeline visualisation
│   ├── diary/                              # Diary parsing + chunking
│   │   ├── chunk.py
│   │   └── parser.py
│   ├── serve/
│   │   ├── Chat.py                         # Streamlit reading room
│   │   ├── handler.py                      # Query worker (retrieval + synthesis)
│   │   ├── image_server.py                 # FLUX image service
│   │   ├── sdxl_server.py                  # SDXL-Lightning image service
│   │   └── pages/1_Browse.py               # Corpus browser page
│   └── cli/
│       ├── main.py                         # gutenkg CLI root group
│       ├── options.py                      # Shared options: REPO_ROOT, CORPUS_ROOT
│       ├── cmd_audit.py                    # gutenkg audit
│       ├── cmd_authors.py                  # gutenkg authors
│       ├── cmd_build_corpus.py             # gutenkg build-corpus
│       ├── cmd_build_diaries.py            # gutenkg build-diaries
│       ├── cmd_chat.py                     # gutenkg chat
│       ├── cmd_chunk_diaries.py            # gutenkg chunk-diaries
│       ├── cmd_download.py                 # gutenkg download *
│       ├── cmd_genres.py                   # gutenkg genres init/list/add
│       ├── cmd_ia.py                       # gutenkg ia *
│       ├── cmd_imagine.py                  # gutenkg imagine (corpus image generation)
│       ├── cmd_ingest.py                   # gutenkg ingest
│       ├── cmd_init.py                     # gutenkg init (local models)
│       ├── cmd_query.py                    # gutenkg query
│       ├── cmd_quilt.py                    # gutenkg quilt (light-field render)
│       ├── cmd_rebuild.py                  # gutenkg rebuild-indices
│       ├── cmd_reregister.py               # gutenkg reregister
│       ├── cmd_snapshot.py                 # gutenkg snapshot
│       ├── cmd_status.py                   # gutenkg status
│       ├── cmd_viz3d.py                    # gutenkg viz3d
│       └── cmd_viz_timeline.py             # gutenkg viz-timeline
├── docker/
│   ├── Dockerfile                          # Worker + chat image
│   ├── docker-compose.yml
│   ├── requirements-image.txt              # FLUX image-server deps
│   └── requirements-sdxl.txt               # SDXL image-server deps
├── runpod/                                 # RunPod serverless build pipeline
├── scripts/
│   ├── process_logo.py                     # Logo transparency + variant generator
│   ├── benchmark_embedders.py              # Embedder benchmarking
│   ├── assess_front_matter.py              # Corpus front-matter analysis
│   ├── provenance_verifier.py              # Reference.md provenance checker
│   ├── regenerate_corpus_doc.py            # Regenerates docs/CORPUS.md
│   ├── sync_corpus_docs.py                 # Syncs the README corpus table
│   └── catalogs/                           # Per-genre batch download catalogs
│       ├── science-fiction.txt
│       ├── philosophy.txt
│       ├── ancient-classical.txt
│       ├── english-literature.txt
│       ├── american-literature.txt
│       ├── french-literature.txt
│       ├── russian-literature.txt
│       ├── german-literature.txt
│       ├── sacred-texts.txt
│       └── world-literature.txt            # …and one per remaining genre
├── docs/
│   ├── APPLE_CONTAINERS.md                 # Apple `container` runtime notes
│   ├── APP_ARCHITECTURE.md                 # Worker/chat/query architecture
│   ├── CHAT_UI.md                          # The reading-room chat interface
│   ├── CHEATSHEET.md                       # Command quick-reference (this file)
│   ├── CORPUS.md                           # Full corpus book list by genre
│   ├── CORPUS_WISHLIST.md                  # Curated additions checklist
│   ├── DOWNLOAD_PIPELINE.md                # End-to-end download pipeline reference
│   ├── INSTALLATION.md                     # CLI + Docker installation
│   ├── ON_DEVICE.md                        # On-device corpus packs for the app
│   ├── PARTNERS.md                         # Collaboration and sponsorship
│   ├── RUNPOD.md                           # RunPod deployment
│   ├── SIMILAR_TO_CAP_*.md                 # SIMILAR_TO evaluation record
│   └── ingestion-pipeline.md               # Ingestion pipeline internals
├── reports/
│   └── ingest_YYYY-MM-DD_HHMMSS.md         # Auto-saved ingest reports
├── .mcp.json                               # MCP server config (gutenkg-mcp)
├── pyproject.toml                          # Package config + script entry points
└── .gitignore
```
