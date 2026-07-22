<p align="center">
  <img src="assets/logos/logo_512.png" alt="GutenbergKG — The Knowledge Press" width="400"/>
</p>

<p align="center">
  <a href="https://github.com/Flux-Frontiers/gutenberg_kg/actions/workflows/ci.yml"><img src="https://github.com/Flux-Frontiers/gutenberg_kg/actions/workflows/ci.yml/badge.svg" alt="CI"/></a>
  <a href="https://github.com/Flux-Frontiers/gutenberg_kg/actions/workflows/docs.yml"><img src="https://github.com/Flux-Frontiers/gutenberg_kg/actions/workflows/docs.yml/badge.svg" alt="Docs"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%20|%203.13-blue.svg" alt="Python"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/code-Elastic--2.0-lightgrey.svg" alt="Code License"/></a>
  <a href="https://www.gutenberg.org/"><img src="https://img.shields.io/badge/texts-Public%20Domain-green.svg" alt="Texts License"/></a>
  <img src="https://img.shields.io/badge/version-1.10.0-blue.svg" alt="Version"/>
  <img src="https://img.shields.io/badge/corpus-241%20books-orange.svg" alt="Corpus"/>
  <img src="https://img.shields.io/badge/nodes-1.3M-green.svg" alt="Nodes"/>
  <img src="https://img.shields.io/badge/edges-5.1M-green.svg" alt="Edges"/>
  <a href="https://doi.org/10.5281/zenodo.20045390"><img src="https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20045390-blue.svg" alt="DOI"/></a>
</p>

# GutenbergKG — The Knowledge Press

**GutenbergKG** is a universal ingestion engine for digitized text corpora — named for the press that democratized books, built to do the same for structured knowledge.

It transforms the world's great public-domain literature, philosophy, and sacred texts into **queryable knowledge graphs** — enabling semantic search, thematic analysis, and cross-work discovery at a scale and depth that keyword search cannot touch. Ask *what themes connect Dostoevsky and Dante*, trace the evolution of the social contract from Rousseau to Thoreau, or find every passage in the corpus that grapples with revenge — and get semantically grounded answers drawn from the source texts themselves.

The corpus currently spans **241 public-domain texts across 20 genres** — 1,270,591 nodes, 5,094,446 edges — built and fully indexed on an Apple M5 Max in about 30 minutes.

*Author: Eric G. Suchanek, PhD · Flux-Frontiers, Liberty TWP, OH*

**Contents:**
[What It Does](#what-it-does) ·
[The Knowledge Press — Local App](#the-knowledge-press--local-app) ·
[Corpus at a Glance](#corpus-at-a-glance) ·
[Requirements](#requirements) ·
[CLI Quick Start](#cli-quick-start--developer--power-user-path) ·
[Querying the Corpus](#querying-the-corpus) ·
[Image Generation](#corpus-grounded-image-generation) ·
[Partnerships](#partnerships) ·
[Citation](#citation) ·
[License](#license)

---

## What It Does

GutenbergKG ingests text from three sources:

- **[Project Gutenberg](https://www.gutenberg.org/)** — the canonical source for public-domain literature. Full OPDS + RDF metadata enrichment: author birth/death, Wikipedia links, subjects, rights.
- **[Internet Archive](https://archive.org/)** — for works not on Gutenberg, including technical reference volumes (Audel Guides, early science texts). OCR plain-text with configurable curation preprocessing.
- **Local corpora** — any directory of `.md` or `.txt` files can be ingested as a genre.

Each text is:

1. **Stripped** of boilerplate (Project Gutenberg headers/footers, OCR artifacts)
2. **Structured** — chapters, parts, acts, scenes, letters, verses detected and converted to Markdown heading hierarchy
3. **Indexed** by [DocKG](https://github.com/Flux-Frontiers/doc_kg) into a hybrid SQLite knowledge graph (FTS5 lexical + `sqlite-vec` dense vectors)
4. **Registered** with [KGRAG](https://github.com/Flux-Frontiers/KGRAG) for federated cross-corpus query

The result: every work is independently queryable as its own knowledge graph, grouped into genre corpora for thematic search, and unified into `gutenberg-all` for corpus-wide discovery. No LLM is required to query — see [Requirements](#requirements).

---

## The Knowledge Press — Local App

The primary interface is **The Knowledge Press**: a self-contained container app that bundles the full knowledge graph, a query worker, and a Streamlit chat UI. Once running, open `http://localhost:8501` and query all books with plain English.

### One-time corpus build (~30 min)

The corpus must be built before the container image. This step converts the raw texts into DocKG + DiaryKG indices and bundles them for baking into the image. You only do this once (or after adding new books).

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
cd gutenberg_kg
poetry install         # installs the gutenkg CLI
make init               # fetches local models (spaCy, embedder) — run once

make build-corpus      # builds .dockg/ indices + bundles/gutenberg-all/
```

> **Expect ~24 minutes** on Apple Silicon. Individual genres take 30 seconds to 5 minutes. The resulting `bundles/gutenberg-all/` directory (~3–5 GB) is what gets baked into the image.

### Build and run

```bash
make build             # bakes the corpus bundle into a self-contained Docker image
make up                # starts everything: worker + chat UI + FLUX image server
```

`make up` brings up three services:

| Service | URL | Purpose |
|---------|-----|---------|
| Query worker | `http://localhost:8000` | Handles all retrieval and synthesis |
| **Chat UI** | **`http://localhost:8501`** | **The Knowledge Press — primary interface** |
| FLUX image server | `http://localhost:8090` | Corpus-grounded image generation |

Open `http://localhost:8501` to start querying.

```bash
make stop              # shuts everything down
make query Q="What is justice according to Plato?"   # one-shot query against the worker
```

**Lighter setups:** `make run` starts just the worker; `make chat` starts worker + chat UI without the image server.

**Runtime choice:** all of the above runs on Docker by default. On Apple Silicon with macOS 26 you can skip Docker Desktop entirely and use Apple's native [`container`](https://github.com/apple/container) CLI instead — same targets, one extra variable:

```bash
container system start  # once per boot
make build RUNTIME=apple
make up RUNTIME=apple
```

Setup, caveats, and how the two runtimes differ are covered in [`docs/APPLE_CONTAINERS.md`](docs/APPLE_CONTAINERS.md).

**About the image size:** the image is large (~4–6 GB) because the full corpus — 1.3M nodes, 5.1M edges, and their 384-dim vector embeddings — is baked in. This is by design: the image is entirely self-contained and needs no external data at runtime. You build it once locally; it never needs to be pushed anywhere.

---

## Corpus at a Glance

<details>
<summary><b>Full genre breakdown</b> — every genre with book, node, and edge counts, sorted by book count</summary>

<!-- BEGIN corpus-table (generated by scripts/sync_corpus_docs.py — do not edit by hand) -->
| Genre | Books | Nodes | Edges |
|-------|------:|------:|------:|
| Philosophy | 39 | 206,960 | 721,341 |
| English Literature | 37 | 185,188 | 834,173 |
| Ancient & Classical | 23 | 118,737 | 461,010 |
| American Literature | 21 | 86,452 | 320,974 |
| Horror | 16 | 43,546 | 165,056 |
| Science Fiction | 13 | 40,280 | 144,023 |
| Russian Literature | 12 | 89,271 | 422,384 |
| French Literature | 12 | 89,473 | 415,362 |
| Biography | 11 | 71,607 | 290,544 |
| Drama | 10 | 14,992 | 57,192 |
| Natural History | 7 | 44,747 | 157,202 |
| Sacred Texts | 7 | 31,773 | 155,939 |
| Travel | 6 | 57,279 | 197,361 |
| Letters | 6 | 37,562 | 120,173 |
| German Literature | 5 | 15,073 | 48,065 |
| World Literature | 4 | 18,305 | 65,559 |
| Diaries | 4 | 78,744 | 382,451 |
| Shakespeare | 4 | 6,260 | 20,966 |
| Technical Reference (IA) | 3 | 22,920 | 61,837 |
| Spanish Literature | 1 | 11,422 | 52,834 |
| **Total** | **241** | **1,270,591** | **5,094,446** |
<!-- END corpus-table -->

</details>

The full book list, organized by genre, is in [`docs/CORPUS.md`](docs/CORPUS.md). Planned additions are tracked in [`docs/CORPUS_WISHLIST.md`](docs/CORPUS_WISHLIST.md).

---

## Requirements

**Python 3.12+, [Poetry](https://python-poetry.org/), GNU Make, and Docker** — or Apple's native [`container`](https://github.com/apple/container) CLI on macOS 26 via `RUNTIME=apple` ([details](docs/APPLE_CONTAINERS.md)). The full requirements table, platform notes, and troubleshooting are in [`docs/INSTALLATION.md`](docs/INSTALLATION.md).

**No LLM is required to query the corpus** — the graph and vector index answer semantic queries on their own. An LLM is only needed for the optional *synthesis* and *image generation* layers. On Apple Silicon, **[oMLX](https://omlx.ai)** is recommended; **[Ollama](https://ollama.com)** works everywhere; and the **OpenAI** provider path works end-to-end (synthesis *and* `gpt-image-1` image generation) with nothing but `OPENAI_API_KEY` set — see [`docs/INSTALLATION.md`](docs/INSTALLATION.md#environment-variables--full-reference).

For RunPod serverless deployment see [`docs/RUNPOD.md`](docs/RUNPOD.md).

---

## CLI Quick Start — Developer / Power-User Path

The CLI operates directly against the local `.dockg/` indices — no Docker required. Use it to download and ingest books, manage the corpus, and query the graph from the terminal.

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
cd gutenberg_kg
poetry install
gutenkg init            # fetches local models (spaCy, embedder) — run once
gutenkg --help
```

After cloning, rebuild the knowledge graph indices from the source Markdown:

```bash
gutenkg ingest --force-build
```

> **Expect 30–45 minutes** for a full rebuild on Apple Silicon (Apple M5 Max: ~30 min, Mac mini M4: ~45 min). Individual genres take 30 seconds to 5 minutes.

For the full command reference — downloading, ingesting, genre management, batch workflows — see [`docs/CHEATSHEET.md`](docs/CHEATSHEET.md). For the technical pipeline internals, see [`docs/DOWNLOAD_PIPELINE.md`](docs/DOWNLOAD_PIPELINE.md).

---

## Querying the Corpus

The query tooling ships **baked in** — no separate installs. `poetry install` puts the [DocKG](https://github.com/Flux-Frontiers/doc_kg) CLI (`dockg`) on your PATH as a core dependency, and the [KGRAG](https://github.com/Flux-Frontiers/KGRAG) CLI (`kgrag`) comes with the `kgdeps` extra (`poetry install --extras kgdeps`). The linked repos are for documentation and development, not something you need to clone.

Three layers, from highest to lowest level — pick the one that fits:

| Tool | Level | Use it for |
|---|---|---|
| **Chat UI / `make query`** | app | conversational querying and one-shot questions against the running worker |
| **`kgrag`** | federated | cross-corpus thematic search and LLM synthesis across genre corpora |
| **`dockg`** | single corpus | direct semantic search within one index |

(`gutenkg` itself is the *corpus management* layer — downloading, ingesting, genre bookkeeping, status — not a query tool.)

```bash
# Semantic search within a genre (dockg — direct index query)
dockg query "characters who seek revenge" --corpus gutenberg-russian-literature

# Cross-work thematic analysis (kgrag — federated)
kgrag corpus query gutenberg-philosophy "free will and moral responsibility"

# Full corpus discovery
kgrag corpus query gutenberg-all "the nature of justice"

# LLM synthesis — retrieve deterministic passages, synthesize with a local model
kgrag synthesize "How do the Stoics and Russian novelists differ on suffering and redemption?" \
  --corpus gutenberg-ancient-classical,gutenberg-russian-literature,gutenberg-philosophy \
  --model qwen3:4b
```

> **Example synthesis output:** See [`STOICS_VS_RUSSIANS.md`](https://github.com/Flux-Frontiers/KGRAG/blob/main/docs/STOICS_VS_RUSSIANS.md) — a live run of the question above against Marcus Aurelius, Dostoevsky, Tolstoy, and Nietzsche, with every passage retrieved deterministically from the graph and quoted verbatim. The retrieval layer cannot hallucinate; the LLM synthesizes from verified facts only. *(Run against an earlier 78-book corpus; the current 241-book corpus adds substantial additional Stoic, philosophical, and literary coverage.)*

---

## Corpus-Grounded Image Generation

`gutenkg imagine` generates illustrations grounded in the corpus text — no cloud API, no separate server. It runs a three-stage pipeline entirely on Apple Silicon:

1. **DiaryKG / DocKG retrieval** — the most semantically relevant passages are pulled from the knowledge graph.
2. **VLM rewrite** — a local Qwen3 model (via [oMLX](http://localhost:8080)) rewrites the prose into a visual scene description.
3. **FLUX.2-Klein generation** — a 4-bit quantised FLUX.2-Klein model renders the image in ~15–22 seconds.

```bash
# 1. Install the project (CLI-first workflow)
pip install -e ".[imagine]"

# Optional: MCP server support
pip install -e ".[mcp]"

# 2. Start oMLX on port 8080 with a Qwen3 model (for VLM rewrite)
omlx serve mlx-community/Qwen3-30B-A3B-Instruct-2507-MLX-4bit --port 8080

# 3. Generate — FLUX model auto-downloads on first run (~4 GB, no license gate)
gutenkg imagine --query "great fire" --book pepys --ratio 16:9 --steps 8

# Direct prompt (no corpus lookup, no oMLX required)
gutenkg imagine "the Great Fire of London at night, oil painting"

# Inspect what the corpus retrieves before generating
gutenkg imagine --query "plague in London" --book pepys --corpus-only
```

The same pipeline is available as an MCP tool (`corpus_imagine`) for use directly in Claude Code chat when installed with `.[mcp]` — ask *"Create an image of the Great Fire based on Pepys' description"* and the tool handles retrieval, rewriting, and generation automatically.

For the full options reference see [`docs/CHEATSHEET.md § Corpus-Grounded Image Generation`](docs/CHEATSHEET.md).

---

## Partnerships

GutenbergKG is one node in the **Tree of Knowledge** — a federated network of domain knowledge graphs unified by [KGRAG](https://github.com/Flux-Frontiers/KGRAG), aimed at a persistent, publicly queryable graph of humanity's written heritage. With 241 works, 5.1 million edges, and a production-ready pipeline, we are seeking hosting sponsors, licensing partners, and research collaborators — see [`docs/PARTNERS.md`](docs/PARTNERS.md) for what we're looking for and what partners get.

**To discuss a partnership:** [suchanek@flux-frontiers.com](mailto:suchanek@flux-frontiers.com)

---

## Related Projects

Both DocKG and KGRAG install with this project as dependencies (see [Querying the Corpus](#querying-the-corpus)) — these repos are where they are developed and documented:

- **[KGRAG](https://github.com/Flux-Frontiers/KGRAG)** — Federated knowledge graph orchestration and query layer
- **[DocKG](https://github.com/Flux-Frontiers/doc_kg)** — Semantic document knowledge graph (powers this corpus)
- **[PyCodeKG](https://github.com/Flux-Frontiers/pycode_kg)** — Structural knowledge graph for Python codebases

---

## Citation

If you use GutenbergKG in your research, please cite it. GitHub's **Cite this repository** button (top-right of the repo page) will generate APA or BibTeX automatically from [`CITATION.cff`](CITATION.cff).

**BibTeX:**

```bibtex
@software{suchanek2026gutenbergkg,
  author       = {Suchanek, Eric G.},
  title        = {{GutenbergKG}: The Knowledge Press},
  year         = {2026},
  version      = {1.10.0},
  publisher    = {Flux-Frontiers},
  doi          = {10.5281/zenodo.20045390},
  url          = {https://github.com/Flux-Frontiers/gutenberg_kg},
  note         = {Universal ingestion engine for digitized text corpora;
                  241 public-domain texts across 20 genres as queryable
                  knowledge graphs via DocKG and KGRAG}
}
```

**APA:**

> Suchanek, E. G. (2026). *GutenbergKG: The Knowledge Press* (Version 1.10.0) [Software]. Flux-Frontiers. https://doi.org/10.5281/zenodo.20045390

---

## License

The texts in this repository are **public domain**. They were sourced from [Project Gutenberg](https://www.gutenberg.org/) and the [Internet Archive](https://archive.org/); GutenbergKG is an independent project with no affiliation with or endorsement from either organization. The download scripts and tooling are part of the [Flux Frontiers](https://github.com/Flux-Frontiers) project and are released under the [Elastic License 2.0](LICENSE).
