<p align="center">
  <img src="assets/logos/logo_512.png" alt="GutenbergKG — The Knowledge Press" width="400"/>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%20|%203.13-blue.svg" alt="Python"/></a>
  <a href="https://www.elastic.co/licensing/elastic-license"><img src="https://img.shields.io/badge/code-Elastic--2.0-lightgrey.svg" alt="Code License"/></a>
  <a href="https://www.gutenberg.org/"><img src="https://img.shields.io/badge/texts-Public%20Domain-green.svg" alt="Texts License"/></a>
  <img src="https://img.shields.io/badge/version-1.2.0-blue.svg" alt="Version"/>
  <img src="https://img.shields.io/badge/corpus-181%20books-orange.svg" alt="Corpus"/>
  <img src="https://img.shields.io/badge/nodes-878K-green.svg" alt="Nodes"/>
  <img src="https://img.shields.io/badge/edges-17.6M-green.svg" alt="Edges"/>
  <a href="https://github.com/Flux-Frontiers/doc_kg"><img src="https://img.shields.io/badge/DocKG-ready-blue.svg" alt="DocKG"/></a>
  <a href="https://github.com/Flux-Frontiers/KGRAG"><img src="https://img.shields.io/badge/KGRAG-integrated-purple.svg" alt="KGRAG"/></a>
  <a href="https://doi.org/10.5281/zenodo.20045390"><img src="https://zenodo.org/badge/doi/10.5281/zenodo.20045390.svg" alt="DOI"/></a>
</p>

# GutenbergKG — The Knowledge Press

**GutenbergKG** is a universal ingestion engine for digitized text corpora — named for the press that democratized books, built to do the same for structured knowledge.

It transforms the world's great public-domain literature, philosophy, and sacred texts into **queryable knowledge graphs** — enabling semantic search, thematic analysis, and cross-work discovery at a scale and depth that keyword search cannot touch. Ask *what themes connect Dostoevsky and Dante*, trace the evolution of the social contract from Rousseau to Thoreau, or find every passage in the corpus that grapples with revenge — and get semantically grounded answers drawn from the source texts themselves.

The corpus currently spans **181 public-domain texts across 13 genres** — 878,403 nodes, 17,564,366 edges — built and fully indexed on an Apple M5 Max in under 10 minutes.

*Author: Eric G. Suchanek, PhD · Flux-Frontiers, Liberty TWP, OH*

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

## Corpus at a Glance

| Genre | Books | Nodes | Edges |
|-------|------:|------:|------:|
| English Literature | 37 | 187,049 | 2,062,293 |
| Ancient & Classical | 26 | 138,437 | 2,880,057 |
| Philosophy | 26 | 113,025 | 1,246,016 |
| Russian Literature | 13 | 90,276 | 2,760,956 |
| American Literature | 23 | 90,494 | 859,696 |
| French Literature | 12 | 89,627 | 3,264,872 |
| Science Fiction | 19 | 70,670 | 958,530 |
| World Literature | 5 | 21,257 | 1,666,207 |
| Sacred Texts | 7 | 23,825 | 883,040 |
| German Literature | 5 | 13,124 | 609,413 |
| Spanish Literature | 1 | 11,438 | 121,414 |
| Shakespeare | 4 | 6,259 | 83,127 |
| Technical Reference (IA) | 3 | 22,922 | 168,745 |
| **Total** | **181** | **878,403** | **17,564,366** |

The full book list, organized by genre, is in [`docs/CORPUS.md`](docs/CORPUS.md). Planned additions are tracked in [`docs/CORPUS_WISHLIST.md`](docs/CORPUS_WISHLIST.md).

---

## Quick Start

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
cd gutenberg_kg
poetry install
gutenkg --help
```

After cloning, rebuild the knowledge graph indices from the source Markdown (not committed to git — they're local build artifacts):

```bash
gutenkg ingest --force-build
```

> **Expect 30–45 minutes** for a full rebuild on Apple Silicon (Apple M5 Max: ~30 min, Mac mini M4: ~45 min). Individual genres take 30 seconds to 5 minutes. Grab a coffee — or two.

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

> **Example synthesis output:** See [`STOICS_VS_RUSSIANS.md`](https://github.com/Flux-Frontiers/KGRAG/blob/main/docs/STOICS_VS_RUSSIANS.md) — a live run of the question above against Marcus Aurelius, Dostoevsky, Tolstoy, and Nietzsche, with every passage retrieved deterministically from the graph and quoted verbatim. The retrieval layer cannot hallucinate; the LLM synthesizes from verified facts only. *(Run against an earlier 78-book corpus; the current 181-book corpus adds additional Stoic, philosophical, and literary coverage.)*

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

181 works, 17.6 million edges, production-ready pipeline. The architecture is federated by design — new corpora slot in without touching the existing graph. The ingestion tooling is fast and fully automated. The query layer is proven. This is the inflection point before the graph becomes too large for any single team to steer.

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
  version      = {1.1.0},
  publisher    = {Flux-Frontiers},
  doi          = {10.5281/zenodo.20045390},
  url          = {https://github.com/Flux-Frontiers/gutenberg_kg},
  note         = {Universal ingestion engine for digitized text corpora;
                  181 public-domain texts across 13 genres as queryable
                  knowledge graphs via DocKG and KGRAG}
}
```

**APA:**

> Suchanek, E. G. (2026). *GutenbergKG: The Knowledge Press* (Version 1.1.0) [Software]. Flux-Frontiers. https://doi.org/10.5281/zenodo.20045390

---

## License

The texts in this repository are **public domain**. They were sourced from [Project Gutenberg](https://www.gutenberg.org/) and the [Internet Archive](https://archive.org/); GutenbergKG is an independent project with no affiliation with or endorsement from either organization. The download scripts and tooling are part of the [Flux Frontiers](https://github.com/Flux-Frontiers) project and are released under the [Elastic License 2.0](https://www.elastic.co/licensing/elastic-license).
