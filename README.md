[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License: Public Domain](https://img.shields.io/badge/texts-Public%20Domain-green.svg)](https://www.gutenberg.org/)
[![Books](https://img.shields.io/badge/corpus-78%20books-orange.svg)](https://github.com/Flux-Frontiers/gutenberg_kg)
[![DocKG](https://img.shields.io/badge/DocKG-ready-blue.svg)](https://github.com/Flux-Frontiers/doc_kg)
[![KGRAG](https://img.shields.io/badge/KGRAG-integrated-purple.svg)](https://github.com/Flux-Frontiers/KGRAG)
[![Nodes](https://img.shields.io/badge/nodes-445K-green.svg)](https://github.com/Flux-Frontiers/gutenberg_kg)
[![Edges](https://img.shields.io/badge/edges-4.5M-green.svg)](https://github.com/Flux-Frontiers/gutenberg_kg)

<p align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Project_Gutenberg_logo.png/320px-Project_Gutenberg_logo.png" alt="Project Gutenberg" width="200"/>
</p>

# GutenbergKG

**GutenbergKG** — A curated corpus of 78 public-domain masterworks from [Project Gutenberg](https://www.gutenberg.org/), structured for knowledge-graph construction with [DocKG](https://github.com/Flux-Frontiers/doc_kg) and the [KGRAG](https://github.com/Flux-Frontiers/KGRAG) federated query framework.

The corpus spans 9 genres, 445,486 nodes, and 4,525,716 edges — queryable as independent genre corpora or as a unified `gutenberg-all` knowledge graph.

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

The result: 78 of history's most important works, instantly searchable as a unified knowledge graph — or as independently queryable genre corpora.

---

## Corpus at a Glance

| Genre | Books | Nodes | Edges |
|-------|------:|------:|------:|
| English Literature | 22 | 93,147 | 893,364 |
| Russian Literature | 6 | 66,343 | 709,346 |
| Ancient & Classical | 8 | 49,351 | 596,246 |
| French Literature | 6 | 58,073 | 672,205 |
| Philosophy | 8 | 58,265 | 506,407 |
| Science Fiction | 14 | 59,075 | 589,989 |
| American Literature | 9 | 43,473 | 364,627 |
| Shakespeare | 4 | 6,277 | 81,237 |
| Spanish Literature | 1 | 11,482 | 112,295 |
| **Total** | **78** | **445,486** | **4,525,716** |

---

## Repository Structure

```
gutenberg_kg/
├── english-literature/          # 22 English novels, novellas & stories
│   ├── <Book Title>/
│   │   ├── <slug>.md            # Full text with Markdown heading hierarchy
│   │   └── reference.md         # Author, subjects, summary, Gutenberg ID
│   └── ...
├── philosophy/                  # 8 philosophical works
├── ancient-classical/           # 8 works from antiquity
├── american-literature/         # 9 American classics
├── russian-literature/          # 6 Russian masterworks
├── french-literature/           # 6 French classics
├── shakespeare/                 # 4 Shakespeare plays
├── spanish/                     # Don Quixote
└── scripts/
    ├── ingest.py                # DocKG build + KGRAG registration + git push
    ├── download_gutenberg.py    # Download & convert script
    └── catalog.txt              # Batch download catalog
```

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
python scripts/download_gutenberg.py search --author "Jane Austen"
python scripts/download_gutenberg.py search --title "Republic"
python scripts/download_gutenberg.py search "science fiction"
```

### Download a book

```bash
python scripts/download_gutenberg.py download 1342
```

This fetches *Pride and Prejudice* from Gutenberg, strips boilerplate, converts chapter structure to Markdown headings, and saves:

```
Pride and Prejudice/
├── pride_and_prejudice.md
└── reference.md
```

### Batch download from catalog

```bash
python scripts/download_gutenberg.py catalog scripts/catalog.txt
```

The catalog file is tab-separated (`<gutenberg_id>\t<optional_title_override>`). Edit `scripts/catalog.txt` to add books.

---

## Building Knowledge Graphs

`scripts/ingest.py` is the single entry point for building DocKG indices,
registering each book with KGRAG, and optionally committing + pushing changes
to git — all in per-genre batches to avoid large monolithic commits.

### List available genres

```bash
python scripts/ingest.py --list-genres
```

### Ingest all genres

```bash
python scripts/ingest.py
```

### Ingest one or more specific genres

```bash
python scripts/ingest.py --genre american-literature
python scripts/ingest.py --genre shakespeare --genre philosophy
```

### Ingest and push each genre as it finishes

```bash
python scripts/ingest.py --push
python scripts/ingest.py --genre russian-literature --push
```

Each genre gets its own `git commit` + `git push` immediately after its books
are processed, keeping individual pushes small regardless of corpus size. Commits
contain only the source Markdown and metadata files — knowledge graph indices are
local-only build artifacts and are not committed.

### Force a full rebuild

```bash
python scripts/ingest.py --force-build
python scripts/ingest.py --force-build --genre english-literature
```

### Preview without making changes

```bash
python scripts/ingest.py --dry-run
python scripts/ingest.py --dry-run --push
```

### Full option reference

| Flag | Description |
|------|-------------|
| `--list-genres` | Print all known genres and exit |
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

## What the Ingestion Script Does

1. **Fetches metadata** from Gutenberg's OPDS feed (title, author, subjects, summary, language)
2. **Downloads** the plain-text UTF-8 version
3. **Strips** Project Gutenberg header/footer boilerplate
4. **Detects structure** — chapters, books, parts, volumes, acts, scenes, letters, and section breaks from common Gutenberg formatting patterns
5. **Converts to Markdown** with proper heading hierarchy (`#` title, `##` chapters, `###` sub-sections)
6. **Writes** a structured `.md` file and a `reference.md` with metadata

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

### Ancient & Classical (8)

| Title | Author | Gutenberg ID |
|---|---|---|
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

## License

The texts in this repository are **public domain** via [Project Gutenberg](https://www.gutenberg.org/). The download scripts and tooling are part of the [Flux Frontiers](https://github.com/Flux-Frontiers) project and are released under the [Elastic License 2.0](https://www.elastic.co/licensing/elastic-license).
