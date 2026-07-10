<p align="center">
  <img src="assets/logos/logo_512.png" alt="GutenbergKG — The Knowledge Press" width="400"/>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%20|%203.13-blue.svg" alt="Python"/></a>
  <a href="https://www.elastic.co/licensing/elastic-license"><img src="https://img.shields.io/badge/code-Elastic--2.0-lightgrey.svg" alt="Code License"/></a>
  <a href="https://www.gutenberg.org/"><img src="https://img.shields.io/badge/texts-Public%20Domain-green.svg" alt="Texts License"/></a>
  <img src="https://img.shields.io/badge/version-1.7.1-blue.svg" alt="Version"/>
  <img src="https://img.shields.io/badge/corpus-230%20books-orange.svg" alt="Corpus"/>
  <img src="https://img.shields.io/badge/nodes-1.2M-green.svg" alt="Nodes"/>
  <img src="https://img.shields.io/badge/edges-4.9M-green.svg" alt="Edges"/>
  <a href="https://github.com/Flux-Frontiers/doc_kg"><img src="https://img.shields.io/badge/DocKG-ready-blue.svg" alt="DocKG"/></a>
  <a href="https://github.com/Flux-Frontiers/KGRAG"><img src="https://img.shields.io/badge/KGRAG-integrated-purple.svg" alt="KGRAG"/></a>
  <img src="https://img.shields.io/badge/imagine-FLUX.2--Klein-ff6b35.svg" alt="Corpus image generation"/>
  <a href="https://doi.org/10.5281/zenodo.20045390"><img src="https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20045390-blue.svg" alt="DOI"/></a>
</p>

# GutenbergKG — The Knowledge Press

**GutenbergKG** is a universal ingestion engine for digitized text corpora — named for the press that democratized books, built to do the same for structured knowledge.

It transforms the world's great public-domain literature, philosophy, and sacred texts into **queryable knowledge graphs** — enabling semantic search, thematic analysis, and cross-work discovery at a scale and depth that keyword search cannot touch. Ask *what themes connect Dostoevsky and Dante*, trace the evolution of the social contract from Rousseau to Thoreau, or find every passage in the corpus that grapples with revenge — and get semantically grounded answers drawn from the source texts themselves.

The corpus currently spans **230 public-domain texts across 19 genres** — 1,234,165 nodes, 4,947,554 edges — built and fully indexed on an Apple M5 Max in under 30 minutes.

*Author: Eric G. Suchanek, PhD · Flux-Frontiers, Liberty TWP, OH*

---

## The Knowledge Press — Local App

The primary interface is **The Knowledge Press**: a self-contained Docker app that bundles the full knowledge graph, a query worker, and a Streamlit chat UI. Once running, open `http://localhost:8501` and query 230 books with plain English.

### One-time corpus build (~24 min)

The corpus must be built before the Docker image. This step converts the raw texts into DocKG + DiaryKG indices and bundles them for baking into the image. You only do this once (or after adding new books).

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
cd gutenberg_kg
poetry install         # installs the gutenkg CLI
make init               # fetches local models (spaCy, embedder) — run once

make build-corpus      # builds .dockg/ indices + bundles/gutenberg-all/
```

> **Expect ~24 minutes** on Apple Silicon. Individual genres take 30 seconds to 5 minutes. The resulting `bundles/gutenberg-all/` directory (~3–5 GB) is what gets baked into the Docker image.

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

### About the image size

The Docker image is large (~4–6 GB) because the full corpus — 1.2M nodes, 4.9M edges, and their 384-dim vector embeddings — is baked in. This is by design: the image is entirely self-contained and needs no external data at runtime. You build it once locally; it never needs to be pushed anywhere.

---

## Corpus at a Glance

| Genre | Books | Nodes | Edges |
|-------|------:|------:|------:|
| Philosophy | 39 | 206,960 | 721,341 |
| English Literature | 37 | 185,188 | 834,173 |
| Ancient & Classical | 23 | 118,737 | 461,010 |
| American Literature | 21 | 86,452 | 320,974 |
| Russian Literature | 12 | 89,271 | 422,384 |
| French Literature | 12 | 89,473 | 415,362 |
| Biography | 11 | 71,607 | 290,544 |
| Drama | 10 | 14,992 | 57,192 |
| Science Fiction | 18 | 47,400 | 162,187 |
| Travel | 6 | 57,279 | 197,361 |
| Natural History | 7 | 44,747 | 157,202 |
| Sacred Texts | 7 | 31,773 | 155,939 |
| Letters | 6 | 37,562 | 120,173 |
| World Literature | 4 | 18,305 | 65,559 |
| German Literature | 5 | 15,073 | 48,065 |
| Diaries | 4 | 78,744 | 382,451 |
| Technical Reference (IA) | 3 | 22,920 | 61,837 |
| Spanish Literature | 1 | 11,422 | 52,834 |
| Shakespeare | 4 | 6,260 | 20,966 |
| **Total** | **230** | **1,234,165** | **4,947,554** |

The full book list, organized by genre, is in [`docs/CORPUS.md`](docs/CORPUS.md). Planned additions are tracked in [`docs/CORPUS_WISHLIST.md`](docs/CORPUS_WISHLIST.md).

---

## What It Does

GutenbergKG ingests text from three sources:

- **[Project Gutenberg](https://www.gutenberg.org/)** — the canonical source for public-domain literature. Full OPDS + RDF metadata enrichment: author birth/death, Wikipedia links, subjects, rights.
- **[Internet Archive](https://archive.org/)** — for works not on Gutenberg, including technical reference volumes (Audel Guides, early science texts). OCR plain-text with configurable curation preprocessing.
- **Local corpora** — any directory of `.md` or `.txt` files can be ingested as a genre.

Each text is:

1. **Stripped** of boilerplate (Project Gutenberg headers/footers, OCR artifacts)
2. **Structured** — chapters, parts, acts, scenes, letters, verses detected and converted to Markdown heading hierarchy
3. **Indexed** by [DocKG](https://github.com/Flux-Frontiers/doc_kg) into a hybrid SQLite + LanceDB knowledge graph
4. **Registered** with [KGRAG](https://github.com/Flux-Frontiers/KGRAG) for federated cross-corpus query

The result: every work is independently queryable as its own knowledge graph, grouped into genre corpora for thematic search, and unified into `gutenberg-all` for corpus-wide discovery.

**No LLM is required to query the corpus.** The graph and vector index answer semantic queries on their own. A small local LLM (Ollama, llama.cpp, MLX) can optionally be connected for synthesis — summarizing results, comparing passages, or generating thematic essays — but the retrieval layer stands alone.

---

## Requirements

| | Required | Notes |
|---|---|---|
| **Python** | 3.12 or 3.13 | `>=3.12,<3.14` |
| **[Poetry](https://python-poetry.org/)** | for the CLI workflow | dependency management + virtual env |
| **[GNU Make](https://www.gnu.org/software/make/)** | for build/run targets | drives `build-corpus`, `build`, `run`, `chat` |
| **[Docker](https://docs.docker.com/get-docker/)** | for the container workflow | Docker Engine 24+ with Compose v2 |
| **LLM (optional)** | for synthesis & image generation | [oMLX](https://omlx.ai) (Apple Silicon) or [Ollama](https://ollama.com) (cross-platform), or **OpenAI** cloud (`OPENAI_API_KEY`) |

**No LLM is required to query the corpus** — the graph and vector index answer semantic queries on their own. An LLM is only needed for the optional *synthesis* and *image generation* layers. On Apple Silicon, **oMLX** is recommended; **Ollama** works everywhere; and the **OpenAI** provider path works end-to-end (synthesis *and* `gpt-image-1` image generation) with nothing but `OPENAI_API_KEY` set — see [`docs/INSTALLATION.md`](docs/INSTALLATION.md#environment-variables--full-reference).

Full prerequisites, platform notes, and troubleshooting are in [`docs/INSTALLATION.md`](docs/INSTALLATION.md). For RunPod serverless deployment see [`docs/RUNPOD.md`](docs/RUNPOD.md).

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

Once indexed, the full corpus is queryable via [DocKG](https://github.com/Flux-Frontiers/doc_kg) and [KGRAG](https://github.com/Flux-Frontiers/KGRAG):

```bash
# Semantic search within a genre
dockg query "characters who seek revenge" --corpus gutenberg-russian-literature

# Cross-work thematic analysis
kgrag corpus query gutenberg-philosophy "free will and moral responsibility"

# Full corpus discovery
kgrag corpus query gutenberg-all "the nature of justice"

# Genre-specific
kgrag corpus query gutenberg-sacred-texts "forgiveness and redemption"

# LLM synthesis — retrieve deterministic passages, synthesize with a local model
kgrag synthesize "How do the Stoics and Russian novelists differ on suffering and redemption?" \
  --corpus gutenberg-ancient-classical,gutenberg-russian-literature,gutenberg-philosophy \
  --model qwen3:4b
```

> **Example synthesis output:** See [`STOICS_VS_RUSSIANS.md`](https://github.com/Flux-Frontiers/KGRAG/blob/main/docs/STOICS_VS_RUSSIANS.md) — a live run of the question above against Marcus Aurelius, Dostoevsky, Tolstoy, and Nietzsche, with every passage retrieved deterministically from the graph and quoted verbatim. The retrieval layer cannot hallucinate; the LLM synthesizes from verified facts only. *(Run against an earlier 78-book corpus; the current 230-book corpus adds substantial additional Stoic, philosophical, and literary coverage.)*

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

## Seeking Strategic Partners & Sponsors

GutenbergKG is one node in a larger initiative — the **Tree of Knowledge** — a federated network of domain knowledge graphs unified by [KGRAG](https://github.com/Flux-Frontiers/KGRAG). The goal: a persistent, publicly queryable graph of humanity's written heritage, queryable without an LLM, composable with one.

We are seeking **targeted partners** who bring infrastructure, institutional reach, or commercial interest to the table.

### Hosting & Infrastructure Sponsors

The corpus knowledge graph indices need persistent, reliable hosting to serve researchers and developers at scale. We are looking for sponsors willing to provide compute and storage in exchange for prominent attribution, early access to new corpora, and co-branding on the public instance.

### Licensing Partners

[KGRAG](https://github.com/Flux-Frontiers/KGRAG) and [DocKG](https://github.com/Flux-Frontiers/doc_kg) are the infrastructure that powers this corpus — and every other knowledge graph in the Tree of Knowledge ecosystem. Organizations building AI-assisted research tools, enterprise knowledge management, or domain-specific retrieval systems can license the stack for internal or commercial deployment.

### Research Collaborators

Digital humanities centers, computational linguistics labs, library science programs, and AI research groups with aligned missions. We are particularly interested in partners who can extend the corpus into non-English languages, underrepresented traditions, or specialized technical domains.

### Why now

230 works, 4.9 million edges, production-ready pipeline. The architecture is federated by design — new corpora slot in without touching the existing graph. The ingestion tooling is fast and fully automated. The query layer is proven. This is the inflection point before the graph becomes too large for any single team to steer.

**To discuss a partnership:** [suchanek@flux-frontiers.com](mailto:suchanek@flux-frontiers.com)

---

## Related Projects

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
  version      = {1.7.1},
  publisher    = {Flux-Frontiers},
  doi          = {10.5281/zenodo.20045390},
  url          = {https://github.com/Flux-Frontiers/gutenberg_kg},
  note         = {Universal ingestion engine for digitized text corpora;
                  230 public-domain texts across 19 genres as queryable
                  knowledge graphs via DocKG and KGRAG}
}
```

**APA:**

> Suchanek, E. G. (2026). *GutenbergKG: The Knowledge Press* (Version 1.7.1) [Software]. Flux-Frontiers. https://doi.org/10.5281/zenodo.20045390

---

## License

The texts in this repository are **public domain**. They were sourced from [Project Gutenberg](https://www.gutenberg.org/) and the [Internet Archive](https://archive.org/); GutenbergKG is an independent project with no affiliation with or endorsement from either organization. The download scripts and tooling are part of the [Flux Frontiers](https://github.com/Flux-Frontiers) project and are released under the [Elastic License 2.0](https://www.elastic.co/licensing/elastic-license).
