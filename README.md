<p align="center">
  <img src="assets/gutenberg_logo.png" alt="GutenbergKG — The Knowledge Press" width="220"/>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%20|%203.13-blue.svg" alt="Python"/></a>
  <a href="https://www.elastic.co/licensing/elastic-license"><img src="https://img.shields.io/badge/code-Elastic--2.0-lightgrey.svg" alt="Code License"/></a>
  <a href="https://www.gutenberg.org/"><img src="https://img.shields.io/badge/texts-Public%20Domain-green.svg" alt="Texts License"/></a>
  <img src="https://img.shields.io/badge/version-1.0.1-blue.svg" alt="Version"/>
  <img src="https://img.shields.io/badge/corpus-79%20books-orange.svg" alt="Corpus"/>
  <img src="https://img.shields.io/badge/nodes-448K-green.svg" alt="Nodes"/>
  <img src="https://img.shields.io/badge/edges-4.8M-green.svg" alt="Edges"/>
  <a href="https://github.com/Flux-Frontiers/doc_kg"><img src="https://img.shields.io/badge/DocKG-ready-blue.svg" alt="DocKG"/></a>
  <a href="https://github.com/Flux-Frontiers/KGRAG"><img src="https://img.shields.io/badge/KGRAG-integrated-purple.svg" alt="KGRAG"/></a>
</p>

# GutenbergKG — The Knowledge Press

**GutenbergKG** is a universal ingestion engine for digitized text corpora — named for the press that democratized books, built to do the same for structured knowledge. It ingests from [Project Gutenberg](https://www.gutenberg.org/), the [Internet Archive](https://archive.org/), and local file corpora, and produces queryable knowledge graphs via [DocKG](https://github.com/Flux-Frontiers/doc_kg) and [KGRAG](https://github.com/Flux-Frontiers/KGRAG).

The current corpus spans 79 public-domain masterworks across 9 genres — 448,139 nodes, 4,836,993 edges — queryable as independent genre corpora or as a unified `gutenberg-all` knowledge graph.

*Author: Eric G. Suchanek, PhD*
*Flux-Frontiers, Liberty TWP, OH*

---

## Overview

GutenbergKG transforms the raw texts of great literature, philosophy, and science into **queryable knowledge graphs** — enabling semantic search, thematic analysis, and cross-work discovery powered by [DocKG](https://github.com/Flux-Frontiers/doc_kg) and [KGRAG](https://github.com/Flux-Frontiers/KGRAG).

Each book is:

- **Downloaded** from Project Gutenberg and stripped of boilerplate
- **Converted to structured Markdown** with heading hierarchy (`##` chapters, `###` scenes/sub-sections)
- **Organized by genre** into thematic subcorpora for targeted or broad querying
- **DocKG-indexed** into SQLite + LanceDB for hybrid semantic + structural retrieval

The result: 79 of history's most important works, instantly searchable as a unified knowledge graph — or as independently queryable genre corpora.

---

## Corpus at a Glance

| Genre | Books | Nodes | Edges |
|-------|------:|------:|------:|
| English Literature | 22 | 93,263 | 966,163 |
| Russian Literature | 6 | 66,343 | 761,002 |
| French Literature | 6 | 58,009 | 704,701 |
| Ancient & Classical | 9 | 51,895 | 646,165 |
| Science Fiction | 14 | 59,079 | 620,127 |
| Philosophy | 8 | 58,341 | 536,916 |
| American Literature | 9 | 43,512 | 397,378 |
| Spanish Literature | 1 | 11,438 | 121,414 |
| Shakespeare | 4 | 6,259 | 83,127 |
| **Total** | **79** | **448,139** | **4,836,993** |

---

## Repository Structure

```
gutenberg_kg/
├── corpus/                              # all books + author index live here
│   ├── english-literature/              # 22 English novels, novellas & stories
│   │   ├── <Book Title>/
│   │   │   ├── <slug>.md                # Full text with Markdown heading hierarchy
│   │   │   └── reference.md             # Author provenance + Gutenberg metadata
│   │   └── ...
│   ├── philosophy/                      # 8 philosophical works
│   ├── ancient-classical/               # 8 works from antiquity
│   ├── american-literature/             # 9 American classics
│   ├── russian-literature/              # 6 Russian masterworks
│   ├── french-literature/               # 6 French classics
│   ├── shakespeare/                     # 4 Shakespeare plays
│   ├── spanish/                         # Don Quixote
│   ├── science-fiction/                 # 14 works of early SF and weird fiction
│   └── authors/                         # Per-author pages (built from reference.md)
│       ├── index.md                     # Master alphabetical table
│       └── <author_slug>/author.md      # Born, died, Wikipedia, works in corpus
├── src/gutenberg_kg/
│   ├── authors.py                       # Author-index logic (invoked by `gutenkg authors`)
│   └── cli/                             # Click command modules
└── scripts/
    ├── process_logo.py                  # Logo transparency + variant generator
    ├── benchmark_embedders.py           # Embedder benchmarking utility
    └── catalogs/                        # Per-genre batch download catalogs
```

See [`DOWNLOAD_PIPELINE.md`](DOWNLOAD_PIPELINE.md) for the full technical
reference on how raw Gutenberg texts become structured Markdown.

---

## Quick Start

### Install the CLI

```bash
git clone https://github.com/Flux-Frontiers/gutenberg_kg
cd gutenberg_kg
poetry install
gutenkg --help
```

### After cloning — rebuild knowledge graph indices

Knowledge graph indices (`graph.sqlite` + LanceDB vectors) are regenerable build artifacts and are not committed to git. Rebuild everything from the source Markdown files:

```bash
gutenkg ingest --force-build              # all genres
gutenkg ingest --force-build --genre shakespeare  # one genre
```

> See [CHEATSHEET.md](CHEATSHEET.md) for the full command reference.

---

No dependencies beyond Python 3.12+ standard library for downloading.

### Search for books

```bash
gutenkg download search --author "Jane Austen"
gutenkg download search --title "Republic"
gutenkg download search "science fiction"
gutenkg download search --subject "dystopia" --language en
```

### Download a book

```bash
gutenkg download book 1342 --genre english-literature
```

This fetches *Pride and Prejudice* from Gutenberg, strips boilerplate, converts chapter structure to Markdown headings, and saves:

```
corpus/english-literature/Pride and Prejudice/
├── pride_and_prejudice.md
└── reference.md
```

### Batch download from catalog

```bash
gutenkg download catalog scripts/catalogs/science-fiction.txt --genre science-fiction
```

Catalog format: one book per line, `<gutenberg_id>[TAB<optional title>[TAB<optional genre>]]`. Lines starting with `#` are comments. Per-genre catalogs live in [`scripts/catalogs/`](scripts/catalogs/).

---

## Building Knowledge Graphs

`gutenkg ingest` builds DocKG indices, registers each book with KGRAG,
and optionally commits + pushes changes to git — all in per-genre batches
to avoid large monolithic commits.

### Manage genres

Genres are stored in [`corpus/genres.json`](corpus/genres.json) — the single
source of truth. Seed it once, then add new genres without touching any code.

```bash
gutenkg genres init                              # create corpus/genres.json from defaults
gutenkg genres list                              # show all registered genres
gutenkg genres add medieval-literature --source gutenberg   # add a new genre
gutenkg genres add my-ia-collection --source ia             # Internet Archive genre
```

### Ingest all genres

```bash
gutenkg ingest
```

### Ingest one or more specific genres

```bash
gutenkg ingest --genre american-literature
gutenkg ingest --genre shakespeare --genre philosophy
```

### Ingest and push each genre as it finishes

```bash
gutenkg ingest --push
gutenkg ingest --genre russian-literature --push
```

Each genre gets its own `git commit` + `git push` immediately after its books
are processed, keeping individual pushes small regardless of corpus size. Commits
contain only the source Markdown and metadata files — knowledge graph indices are
local-only build artifacts and are not committed.

### Force a full rebuild

```bash
gutenkg ingest --force-build
gutenkg ingest --force-build --genre english-literature
```

### Preview without making changes

```bash
gutenkg ingest --dry-run
gutenkg ingest --dry-run --push
```

### Full option reference

| Flag | Description |
|------|-------------|
| `--genre GENRE` | Process only this genre (repeatable) |
| `--force-build` | Rebuild even if `.dockg` already exists |
| `--force-register` | Re-register even if already in KGRAG registry |
| `--push` | `git add` + `git commit` + `git push` after each genre |
| `--dry-run` | Print actions without executing anything |
| `--registry PATH` | Override the KGRAG registry path |

### What ingest does, per book

1. Runs `dockg build` to build a SQLite + LanceDB knowledge graph under `<book>/.dockg/`
2. Registers the resulting KG with KGRAG under the name `gutenberg-<genre>-<slug>-doc`
3. Adds it to the genre corpus (`gutenberg-<genre>`) and the top-level corpus (`gutenberg-all`)
4. With `--push`: stages `<genre>/` (text + metadata only), commits, and pushes once all books in the genre are done

### Query the corpus

```bash
# Thematic search
dockg query "What themes appear in Meditations?"

# Cross-work discovery
dockg query "characters who seek revenge"

# Philosophical analysis
dockg query "social contract and natural law"
```

### Federated query with KGRAG

```bash
kgrag query "stoic philosophy and virtue"
kgrag corpus query gutenberg-all "the nature of justice"
kgrag corpus query gutenberg-philosophy "free will and determinism"
```

---

## What the Download Script Does

1. **Fetches OPDS metadata** — title, author name, subjects, summary, language, rights
2. **Enriches with RDF provenance** — author birth year, death year, Wikipedia URL, Gutenberg agent ID (pulled from `pg<id>.rdf`)
3. **Downloads** the plain-text UTF-8 version
4. **Strips** Project Gutenberg header/footer boilerplate
5. **Detects structure** — chapters, books, parts, volumes, acts, scenes, letters, and section breaks from common Gutenberg formatting patterns
6. **Converts to Markdown** with proper heading hierarchy (`#` title, `##` chapters, `###` sub-sections)
7. **Writes** a structured `.md` file and a `reference.md` with full author provenance and Gutenberg metadata

After a batch of downloads, run `gutenkg authors` to (re)generate
`corpus/authors/` with per-author pages aggregated across every book in the
corpus. Use `gutenkg authors --refresh` to also backfill provenance for any
`reference.md` files that predate the RDF enrichment.

Full technical reference: [`DOWNLOAD_PIPELINE.md`](DOWNLOAD_PIPELINE.md).

### Supported heading patterns

| Pattern | Example | Heading level |
|---|---|---|
| Chapter | `CHAPTER XIV.`, `Chapter 3` | `##` |
| Book / Volume / Part | `BOOK THE FIRST`, `VOLUME II`, `PART III` | `##` |
| Letter | `Letter 4` | `##` |
| Act / Scene | `ACT III`, `SCENE II` | `##` / `###` |
| Titled section | `I. A SCANDAL IN BOHEMIA` | `##` |
| Sub-section break | `III.` | `###` |
| Multi-line title | `CHAPTER I.` + title on next line | merged into `##` |

---

## Books in the Corpus

### English Literature (22)

| Title | Author | Gutenberg ID |
|---|---|---|
| A Modest Proposal | Jonathan Swift | 1080 |
| A Tale of Two Cities | Charles Dickens | 98 |
| Alice's Adventures in Wonderland | Lewis Carroll | 11 |
| Dracula | Bram Stoker | 345 |
| Emma | Jane Austen | 158 |
| Frankenstein | Mary Shelley | 84 |
| Great Expectations | Charles Dickens | 1400 |
| Grimms' Fairy Tales | Brothers Grimm | 2591 |
| Gulliver's Travels | Jonathan Swift | 829 |
| Heart of Darkness | Joseph Conrad | 219 |
| Jane Eyre | Charlotte Brontë | 1260 |
| Middlemarch | George Eliot | 145 |
| Pride and Prejudice | Jane Austen | 1342 |
| Robinson Crusoe | Daniel Defoe | 521 |
| Sense and Sensibility | Jane Austen | 161 |
| The Adventures of Sherlock Holmes | Arthur Conan Doyle | 1661 |
| The Picture of Dorian Gray | Oscar Wilde | 174 |
| The Strange Case of Dr Jekyll and Mr Hyde | Robert Louis Stevenson | 43 |
| The Time Machine | H.G. Wells | 35 |
| The War of the Worlds | H.G. Wells | 36 |
| Treasure Island | Robert Louis Stevenson | 120 |
| Wuthering Heights | Emily Brontë | 768 |

### Philosophy (8)

| Title | Author | Gutenberg ID |
|---|---|---|
| Beyond Good and Evil | Friedrich Nietzsche | 4363 |
| Common Sense | Thomas Paine | 147 |
| Leviathan | Thomas Hobbes | 3207 |
| On the Origin of Species | Charles Darwin | 1228 |
| The Federalist Papers | Hamilton, Madison, Jay | 1404 |
| The Prince | Niccolò Machiavelli | 1232 |
| The Wealth of Nations | Adam Smith | 3300 |
| Thus Spake Zarathustra | Friedrich Nietzsche | 1998 |

### Ancient & Classical (9)

| Title | Author | Gutenberg ID |
|---|---|---|
| A Selection from the Discourses of Epictetus with the Encheiridion | Epictetus | 10661 |
| Meditations | Marcus Aurelius | 2680 |
| Oedipus King of Thebes | Sophocles | 27673 |
| The Aeneid | Virgil | 228 |
| The Bible (King James) | — | 10 |
| The Divine Comedy | Dante Alighieri | 1004 |
| The Iliad | Homer | 6130 |
| The Odyssey | Homer | 1727 |
| The Republic | Plato | 1497 |

### American Literature (9)

| Title | Author | Gutenberg ID |
|---|---|---|
| Adventures of Huckleberry Finn | Mark Twain | 76 |
| Leaves of Grass | Walt Whitman | 1322 |
| Moby Dick | Herman Melville | 2701 |
| The Call of the Wild | Jack London | 215 |
| The Red Badge of Courage | Stephen Crane | 73 |
| The Scarlet Letter | Nathaniel Hawthorne | 33 |
| The Yellow Wallpaper | Charlotte Perkins Gilman | 1952 |
| Uncle Tom's Cabin | Harriet Beecher Stowe | 203 |
| Walden | Henry David Thoreau | 205 |

### Russian Literature (6)

| Title | Author | Gutenberg ID |
|---|---|---|
| Anna Karenina | Leo Tolstoy | 1399 |
| Crime and Punishment | Fyodor Dostoevsky | 2554 |
| Dead Souls | Nikolai Gogol | 1081 |
| The Brothers Karamazov | Fyodor Dostoevsky | 28054 |
| The Idiot | Fyodor Dostoevsky | 2638 |
| War and Peace | Leo Tolstoy | 2600 |

### French Literature (6)

| Title | Author | Gutenberg ID |
|---|---|---|
| Candide | Voltaire | 19942 |
| Les Misérables | Victor Hugo | 135 |
| Madame Bovary | Gustave Flaubert | 2413 |
| The Count of Monte Cristo | Alexandre Dumas | 1184 |
| The Three Musketeers | Alexandre Dumas | 1257 |
| Twenty Thousand Leagues Under the Sea | Jules Verne | 164 |

### Shakespeare (4)

| Title | Author | Gutenberg ID |
|---|---|---|
| A Midsummer Night's Dream | William Shakespeare | 1514 |
| Hamlet | William Shakespeare | 1524 |
| Macbeth | William Shakespeare | 1533 |
| Romeo and Juliet | William Shakespeare | 1513 |

### Spanish Literature (1)

| Title | Author | Gutenberg ID |
|---|---|---|
| Don Quixote | Miguel de Cervantes | 996 |

### Science Fiction (14)

| Title | Author | Gutenberg ID |
|---|---|---|
| Frankenstein | Mary Shelley | 84 |
| The Invisible Man | H.G. Wells | 5230 |
| The Island of Doctor Moreau | H.G. Wells | 1658 |
| The First Men in the Moon | H.G. Wells | 18857 |
| A Princess of Mars | Edgar Rice Burroughs | 10662 |
| The Gods of Mars | Edgar Rice Burroughs | 364 |
| At the Earth's Core | Edgar Rice Burroughs | 62 |
| Flatland | Edwin Abbott | 11 |
| The Lost World | Arthur Conan Doyle | 29808 |
| The Call of Cthulhu | H.P. Lovecraft | 68283 |
| At the Mountains of Madness | H.P. Lovecraft | 31469 |
| The Shadow over Innsmouth | H.P. Lovecraft | 70652 |
| Herbert West: Reanimator | H.P. Lovecraft | 665 |
| The Dunwich Horror | H.P. Lovecraft | 50133 |

---

## Related Projects

- **[KGRAG](https://github.com/Flux-Frontiers/KGRAG)** — Federated knowledge graph orchestration and query layer
- **[DocKG](https://github.com/Flux-Frontiers/doc_kg)** — Semantic document knowledge graph (powers this corpus)
- **[CodeKG](https://github.com/Flux-Frontiers/code_kg)** — Structural knowledge graph for Python codebases

---

## Citation

If you use GutenbergKG in your research, please cite it. GitHub's **Cite this repository** button (top-right of the repo page) will generate APA or BibTeX automatically from [`CITATION.cff`](CITATION.cff).

**BibTeX:**

```bibtex
@software{suchanek2026gutenbergkg,
  author       = {Suchanek, Eric G.},
  title        = {{GutenbergKG}: The Knowledge Press},
  year         = {2026},
  version      = {1.0.1},
  publisher    = {Flux-Frontiers},
  url          = {https://github.com/Flux-Frontiers/gutenberg_kg},
  note         = {Universal ingestion engine for digitized text corpora;
                  79 public-domain masterworks across 9 genres as queryable
                  knowledge graphs via DocKG and KGRAG}
}
```

**APA:**

> Suchanek, E. G. (2026). *GutenbergKG: The Knowledge Press* (Version 1.0.1) [Software]. Flux-Frontiers. https://github.com/Flux-Frontiers/gutenberg_kg

---

## License

The texts in this repository are **public domain**. They were sourced from [Project Gutenberg](https://www.gutenberg.org/) and the [Internet Archive](https://archive.org/); GutenbergKG is an independent project with no affiliation with or endorsement from either organization. The download scripts and tooling are part of the [Flux Frontiers](https://github.com/Flux-Frontiers) project and are released under the [Elastic License 2.0](https://www.elastic.co/licensing/elastic-license).
