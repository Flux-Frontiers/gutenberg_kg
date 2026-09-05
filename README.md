<p align="center">
  <img src="assets/logos/logo_512.png" alt="GutenbergKG — The Knowledge Press" width="320"/>
</p>

<p align="center">
  <a href="https://github.com/Flux-Frontiers/gutenberg_kg/actions/workflows/ci.yml"><img src="https://github.com/Flux-Frontiers/gutenberg_kg/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="https://github.com/Flux-Frontiers/gutenberg_kg/actions/workflows/docs.yml"><img src="https://github.com/Flux-Frontiers/gutenberg_kg/actions/workflows/docs.yml/badge.svg" alt="Docs"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%20%7C%203.13-blue.svg" alt="Python"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/code-Elastic--2.0-lightgrey.svg" alt="Code License"/></a>
  <a href="https://www.gutenberg.org/"><img src="https://img.shields.io/badge/texts-Public%20Domain-green.svg" alt="Texts License"/></a>
  <img src="https://img.shields.io/badge/version-1.18.0-blue.svg" alt="Version"/>
  <img src="https://img.shields.io/badge/corpus-252%20books-orange.svg" alt="Corpus"/>
  <img src="https://img.shields.io/badge/nodes-1.3M-green.svg" alt="Nodes"/>
  <img src="https://img.shields.io/badge/edges-5.3M-green.svg" alt="Edges"/>
  <a href="https://doi.org/10.5281/zenodo.20045389"><img src="https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20045389-blue.svg" alt="DOI"/></a>
</p>

# GutenbergKG — The Knowledge Press

**A local, source-grounded way to ask better questions of great books.**

GutenbergKG turns public-domain texts into a queryable library of knowledge graphs. Instead of searching for a word in one book at a time, you can explore an idea across works—then read the passages that support what you find.

Ask how Stoics, novelists, and sacred texts treat suffering; find accounts of the Great Fire in Pepys; compare what Rousseau and Thoreau mean by freedom. Retrieval is local and works without an LLM. An optional local or cloud model can turn the retrieved passages into a cited synthesis, but the evidence remains visible and inspectable.

The included corpus contains **241 texts in 20 genres**: literature, philosophy, drama, diaries, sacred texts, travel, natural history, and technical reference. It is a working library, not a benchmark-sized black box.

> **GutenbergKG is for readers, researchers, and builders** who want semantic discovery with a path back to the original text.

## 🌳 New: a book grows into a tree, and the tree can leave the screen

Two things are new here, and the second depends on hardware most people do not have yet.

### Books grow into natural-looking trees

A knowledge graph does not have to be drawn as a hairball. Each book now grows into a tree, and the growth is structural rather than decorative. The book's text chunks become attraction points and the branches are produced by space colonization (Runions, Lane & Prusinkiewicz, 2007), so every limb is a real path through the graph—document → section → chunk cluster—and the canopy's shape is the book's shape. Branch radii follow the pipe model, so a limb carrying half the text is visibly thicker.

Two books of different structure therefore grow different silhouettes, and a given book grows the same tree every time: the seed comes from its slug, not from Python's per-process `hash()`. Hamlet is 420 chunks carried on 305 limbs.

```bash
gutenkg viz3d                                     # tick "Organic tree", pick a book
gutenkg quilt --book Hamlet --season autumn       # spring, summer, autumn, winter
```

There are four seasons. `--season winter` drops ninety percent of the leaves, which is the point—bare wood is where the pipe model shows.

### If you own a Looking Glass display, cast to it

This is the part that is genuinely new context rather than a nicer picture. A [Looking Glass](https://lookingglassfactory.com/) panel shows a *light field*: dozens of views at once, so the tree has real depth and holds still in space while you move your head around it. No glasses, no headset. Two people can lean over the same tree at the same time and see it from their own angles.

Rendering to one is handled by [quiltwright](https://github.com/suchanek/quiltwright), a separate library for turning ordered sweeps of views into light-field quilts.

```bash
gutenkg quilt --book Hamlet                       # 48 views, one 7680x4320 quilt
gutenkg quilt --book Pepys --orbit 180 --cast     # turntable video, straight to the display
```

Hamlet's 8x6 quilt for the 16" Gen3 Landscape takes about two seconds on an M5 Max. The stereo depth budget is printed before every render, so an over-wide disparity shows up at no cost rather than after all 48 views. The viewer has a **Cast to LG** button that does the same thing for whatever is on screen.

No panel? Nothing is lost. A quilt is an ordinary PNG and the trees above render without any display hardware at all.

Both features need the `viz3d` extra; see the [cheatsheet](docs/CHEATSHEET.md#visualisation-and-light-field-rendering) for every option of `viz3d` and `quilt`.

## What makes it useful

- **Ask across books, not just within them.** Search semantically by theme, scene, question, or concept.
- **Keep the source in view.** Results are ranked passages with their work, author, genre, and path—not an answer detached from its evidence.
- **Run locally.** The query layer is a SQLite graph plus vector index, so retrieval needs no LLM or remote service.
- **Grow the library reproducibly.** The `gutenkg` CLI downloads, cleans, structures, indexes, and registers new texts from Project Gutenberg, Internet Archive, or local Markdown/text files.

Under the hood, each work becomes a [DocKG](https://github.com/Flux-Frontiers/doc_kg) knowledge graph; diary material uses [DiaryKG](https://github.com/Flux-Frontiers/diary_kg). [KGRAG](https://github.com/Flux-Frontiers/KGRAG) federates those graphs into genre and corpus-wide search.

## Choose a path

| If you want to… | Start here |
|---|---|
| Explore the library in a browser | Build the local app below, then open the chat UI. |
| Work from the terminal or add texts | Follow the [CLI installation guide](docs/INSTALLATION.md#cli-workflow). |
| Understand a command or corpus-maintenance workflow | See the [cheatsheet](docs/CHEATSHEET.md). |
| See every title in the corpus | Browse [the corpus catalog](docs/CORPUS.md). |
| Understand the retrieval and build architecture | Read the [ingestion pipeline](docs/ingestion-pipeline.md). |

## Run the local reading room

The Knowledge Press is a self-contained Docker app: a query worker, a Streamlit chat interface, and an optional image service. The first build prepares local indices from the tracked source texts; later starts reuse the image.

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
cd gutenberg_kg
poetry install --extras "kgdeps viz viz3d mcp"
make init                 # download local models once
make build-corpus         # build DocKG + DiaryKG indices (~30 min on Apple Silicon)
make build                # bake the corpus into the Docker image
make chat                 # start the worker and reading room
```

Open **http://localhost:8501** and ask a question. Use `make up` instead of `make chat` to also start the local image service; use `make stop` to shut down services.

The bundle and Docker image are large because the corpus and its vector indices travel with the app. That is deliberate: once built, the reading room has no runtime dependency on a hosted corpus.

For prerequisites, non-Apple-Silicon notes, smaller setups, and cloud/OpenAI synthesis, see [Installation](docs/INSTALLATION.md). For what the interface shows and how it handles sources, see [The Knowledge Press chat UI](docs/CHAT_UI.md).

### Runtime: Docker or Apple `container`

By default the local app runs on Docker. On Apple Silicon with macOS 26 you can skip Docker Desktop entirely and use Apple's native [`container`](https://github.com/apple/container) CLI instead — same `make` targets, one extra variable:

```bash
container system start  # once per boot
make build RUNTIME=apple
make up RUNTIME=apple
```

Setup, caveats, and how the two runtimes differ are covered in [`docs/APPLE_CONTAINERS.md`](docs/APPLE_CONTAINERS.md).

## Manage the library from the terminal

Use `gutenkg` to search the locally ingested corpus—Docker is not required:

```bash
# Search the full corpus
gutenkg query "the nature of justice"

# Search a genre-specific local corpus
gutenkg query "characters who seek revenge" --corpus gutenberg-russian-literature
```

Run `gutenkg ingest` first to build the per-book indices and register them locally.

## Build a library of your own

The project is also an ingestion tool. Add a book, a catalog, an Internet Archive work, or a directory of local Markdown/text; then index it into the same discovery layer.

```bash
# Download and index a known Project Gutenberg work
gutenkg download book 2701 --genre american-literature
gutenkg ingest --genre american-literature

# Inspect what is present and indexed
gutenkg status
```

The complete workflows—including catalogs, genre management, provenance, and rebuilding after a clone—are in the [CLI cheatsheet](docs/CHEATSHEET.md) and [download pipeline](docs/DOWNLOAD_PIPELINE.md).

## Corpus at a glance

<details>
<summary><b>Full genre breakdown</b> — every genre with book, node, and edge counts, sorted by book count</summary>

<!-- BEGIN corpus-table (generated by scripts/sync_corpus_docs.py — do not edit by hand) -->
| Genre | Books | Nodes | Edges |
|-------|------:|------:|------:|
| Philosophy | 39 | 207,468 | 720,945 |
| English Literature | 37 | 185,337 | 834,810 |
| Ancient & Classical | 23 | 118,771 | 461,065 |
| American Literature | 23 | 90,376 | 329,426 |
| Science Fiction | 16 | 51,959 | 179,985 |
| Horror | 16 | 43,556 | 165,071 |
| Russian Literature | 12 | 89,915 | 423,246 |
| French Literature | 12 | 89,527 | 415,390 |
| Biography | 11 | 71,696 | 286,701 |
| Drama | 10 | 14,999 | 57,231 |
| Technical Reference (IA) | 8 | 72,842 | 193,063 |
| Natural History | 7 | 44,826 | 157,484 |
| Sacred Texts | 7 | 31,996 | 156,858 |
| Travel | 6 | 57,790 | 198,489 |
| Letters | 6 | 37,551 | 120,198 |
| German Literature | 5 | 15,072 | 48,043 |
| World Literature | 4 | 18,701 | 66,381 |
| Diaries | 4 | 78,744 | 382,451 |
| Shakespeare | 4 | 6,260 | 20,966 |
| Spanish Literature | 1 | 11,422 | 52,834 |
| **Total** | **252** | **1,342,156** | **5,278,365** |
<!-- END corpus-table -->

</details>

Browse the complete, title-level [corpus catalog](docs/CORPUS.md); prospective additions live in the [corpus wishlist](docs/CORPUS_WISHLIST.md).

## Corpus-grounded images

On Apple Silicon, `gutenkg imagine` can retrieve passages, turn them into a visual brief, and render an illustration locally. This is an optional creative layer—not a substitute for the source text.

```bash
gutenkg imagine --query "the Great Fire of London" --book pepys --ratio 16:9
gutenkg imagine --query "plague in London" --book pepys --corpus-only
```

The second command is a useful way to inspect retrieval without generating anything. Setup and full options are in the [image-generation cheatsheet](docs/CHEATSHEET.md#corpus-grounded-image-generation).

## Project ecosystem

GutenbergKG is one corpus in the broader **Tree of Knowledge**: interoperable, domain-specific knowledge graphs that can be queried independently or together. The underlying projects are [DocKG](https://github.com/Flux-Frontiers/doc_kg) for document graphs and [KGRAG](https://github.com/Flux-Frontiers/KGRAG) for federated retrieval.

We welcome research collaborators, library and digital-humanities partners, and infrastructure sponsors interested in extending access to public-domain knowledge — see [`docs/PARTNERS.md`](docs/PARTNERS.md) for what we're looking for and what partners get. Contact [suchanek@flux-frontiers.com](mailto:suchanek@flux-frontiers.com).

## Citation

If you use GutenbergKG in research, use GitHub’s **Cite this repository** button or [`CITATION.cff`](CITATION.cff).

```bibtex
@software{suchanek2026gutenbergkg,
  author       = {Suchanek, Eric G.},
  title        = {{GutenbergKG}: The Knowledge Press},
  year         = {2026},
  version      = {1.18.0},
  publisher    = {Flux-Frontiers},
  doi          = {10.5281/zenodo.20045389},
  url          = {https://github.com/Flux-Frontiers/gutenberg_kg}
}
```

## License

The texts in this repository are **public domain**. They were sourced from [Project Gutenberg](https://www.gutenberg.org/) and the [Internet Archive](https://archive.org/); GutenbergKG is an independent project with no affiliation with or endorsement from either organization. The download scripts and tooling are part of the [Flux Frontiers](https://github.com/Flux-Frontiers) project and are released under the [Elastic License 2.0](LICENSE).
