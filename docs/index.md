# GutenbergKG

**The Knowledge Press -- a local, source-grounded way to ask better questions of great books.**

*Eric G. Suchanek, PhD -- Flux-Frontiers*

GutenbergKG turns public-domain texts into a queryable library of knowledge
graphs. Instead of searching for a word in one book at a time, you can
explore an idea across works -- then read the passages that support what you
find. Retrieval is local and works without an LLM; an optional local or
cloud model can turn the retrieved passages into a cited synthesis, but the
evidence remains visible and inspectable.

The included corpus contains **241 texts in 20 genres**: literature,
philosophy, drama, diaries, sacred texts, travel, natural history, and
technical reference.

## Where to start

| | |
|---|---|
| [Installation](INSTALLATION.md) | CLI, Docker, and Apple container setup |
| [Cheatsheet](CHEATSHEET.md) | Every `gutenkg` command, quick reference |
| [Chat UI](CHAT_UI.md) | The Streamlit reading-room interface |

## Corpus

| | |
|---|---|
| [Books in the corpus](CORPUS.md) | The full title-level catalog |
| [Corpus wishlist](CORPUS_WISHLIST.md) | Planned additions, organized by genre |
| [Download pipeline](DOWNLOAD_PIPELINE.md) | How texts are fetched and catalogued |
| [Ingestion pipeline](ingestion-pipeline.md) | Retrieval and build architecture |

## Visualization

| | |
|---|---|
| [Ray-tracing the knowledge tree](POVRAY.md) | Growing a book into a 3-D tree, cast to Looking Glass or rendered analytically |

See also [RunPod deployment](RUNPOD.md) and [Partners](PARTNERS.md).

The [API reference](api/corpus.md) is generated from the package's own
docstrings.

## Source

GutenbergKG is Elastic-2.0 and lives at
[github.com/Flux-Frontiers/gutenberg_kg](https://github.com/Flux-Frontiers/gutenberg_kg).
