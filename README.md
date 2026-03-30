# Great Books

A curated corpus of public-domain literature from [Project Gutenberg](https://www.gutenberg.org/), structured as Markdown for knowledge-graph construction with [DocKG](https://github.com/Flux-Frontiers/doc_kg) and [DiaryKG](https://github.com/Flux-Frontiers/diary_kg).

## Repository Structure

```
great_books/
├── <Book Title>/
│   ├── <slug>.md            # Full text with Markdown heading hierarchy
│   └── reference.md         # Metadata: author, subjects, summary, source
├── scripts/
│   ├── download_gutenberg.py   # Download & convert script
│   └── catalog.txt             # Batch download catalog
└── README.md
```

Each book lives in its own directory. The `.md` files use proper heading structure (`##` for chapters/books, `###` for scenes/sub-sections) so that DocKG can build a richly structured knowledge graph with section hierarchy, semantic chunks, and cross-document similarity.

## Quick Start

No dependencies beyond Python 3.10+ standard library.

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

## What the Script Does

1. **Fetches metadata** from Gutenberg's OPDS feed (title, author, subjects, summary, language)
2. **Downloads** the plain-text UTF-8 version
3. **Strips** Project Gutenberg header/footer boilerplate
4. **Detects structure** — chapters, books, parts, volumes, acts, scenes, letters, and section breaks from common Gutenberg formatting patterns
5. **Converts to Markdown** with proper heading hierarchy (`#` title, `##` chapters, `###` sub-sections)
6. **Writes a reference file** with source metadata, subjects, and summary

### Supported heading patterns

| Pattern | Example | Level |
|---|---|---|
| Chapter | `CHAPTER XIV.`, `Chapter 3` | `##` |
| Book/Volume/Part | `BOOK THE FIRST`, `VOLUME II`, `PART III` | `##` |
| Letter | `Letter 4` | `##` |
| Act / Scene | `ACT III`, `SCENE II` | `##` / `###` |
| Titled section | `I. A SCANDAL IN BOHEMIA` | `##` |
| Sub-section break | `III.` | `###` |
| Multi-line title | `CHAPTER I.` + title on next line | merged into `##` |

## Building Knowledge Graphs

Once books are downloaded, point DocKG at the repo:

```bash
# Build a graph from a single book
dockg build "Pride and Prejudice/"

# Build from the entire corpus
dockg build .

# Query the graph
dockg query "What themes appear in Meditations?"
```

DocKG will parse the Markdown headings into a section hierarchy, chunk the text semantically, compute embeddings, and build a queryable knowledge graph in SQLite + LanceDB.

## Books in the Corpus

| Title | Author | Gutenberg ID |
|---|---|---|
| Grimms Fairy Tales | Brothers Grimm | 2591 |
| Meditations | Marcus Aurelius | 2680 |
| The King James Bible | — | 10 |
| The Federalist Papers | Hamilton, Madison, Jay | 2009 |

See `scripts/catalog.txt` for additional books ready to download.

## License

The texts in this repository are public domain via Project Gutenberg. The download script and tooling are part of the [Flux Frontiers](https://github.com/Flux-Frontiers) project.
