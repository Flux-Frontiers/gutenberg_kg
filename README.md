# Great Books

A curated corpus of public-domain literature from [Project Gutenberg](https://www.gutenberg.org/), structured for knowledge-graph construction with [DocKG](https://github.com/Flux-Frontiers/doc_kg) and [DiaryKG](https://github.com/Flux-Frontiers/diary_kg).

## Repository Structure

```
project_gutenberg/
├── <Book Title>/
│   ├── <slug>.md            # Full text with Markdown heading hierarchy
│   └── reference.md         # Metadata: author, subjects, summary, source
├── scripts/
│   ├── download_gutenberg.py   # Download & convert script
│   └── catalog.txt             # Batch download catalog
├── magna_carta.html            # Magna Carta (raw HTML source)
└── README.md
```

Each book lives in its own directory named after its title. The `.md` files use proper heading structure (`##` for chapters/books, `###` for scenes/sub-sections) so that DocKG can build a richly structured knowledge graph with section hierarchy, semantic chunks, and cross-document similarity.

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
6. **Writes** a structured `.md` file and a `reference.md` with metadata

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

DocKG will parse the text into a section hierarchy, chunk it semantically, compute embeddings, and build a queryable knowledge graph in SQLite + LanceDB.

## Books in the Corpus

| Title | Author | Gutenberg ID |
|---|---|---|
| A Midsummer Night's Dream | William Shakespeare | 1514 |
| A Modest Proposal | Jonathan Swift | 1080 |
| A Tale of Two Cities | Charles Dickens | 98 |
| Adventures of Huckleberry Finn | Mark Twain | 76 |
| Alices Adventures in Wonderland | Lewis Carroll | 11 |
| Anna Karenina | Leo Tolstoy | 1399 |
| Beyond Good and Evil | Friedrich Nietzsche | 4363 |
| Candide | Voltaire | 19942 |
| Common Sense | Thomas Paine | 147 |
| Crime and Punishment | Fyodor Dostoevsky | 2554 |
| Dead Souls | Nikolai Gogol | 1081 |
| Don Quixote | Miguel de Cervantes | 996 |
| Dracula | Bram Stoker | 345 |
| Emma | Jane Austen | 158 |
| Frankenstein | Mary Shelley | 84 |
| Great Expectations | Charles Dickens | 1400 |
| Grimms Fairy Tales | Brothers Grimm | 2591 |
| Gulliver's Travels | Jonathan Swift | 829 |
| Hamlet | William Shakespeare | 1524 |
| Heart of Darkness | Joseph Conrad | 219 |
| Jane Eyre | Charlotte Brontë | 1260 |
| Leaves of Grass | Walt Whitman | 1322 |
| Les Misérables | Victor Hugo | 135 |
| Leviathan | Thomas Hobbes | 3207 |
| Macbeth | William Shakespeare | 1533 |
| Madame Bovary | Gustave Flaubert | 2413 |
| Meditations | Marcus Aurelius | 2680 |
| Middlemarch | George Eliot | 145 |
| Moby Dick | Herman Melville | 2701 |
| Oedipus King of Thebes | Sophocles | 27673 |
| On the Origin of Species | Charles Darwin | 1228 |
| Pride and Prejudice | Jane Austen | 1342 |
| Robinson Crusoe | Daniel Defoe | 521 |
| Romeo and Juliet | William Shakespeare | 1513 |
| Sense and Sensibility | Jane Austen | 161 |
| The Aeneid | Virgil | 228 |
| The Adventures of Sherlock Holmes | Arthur Conan Doyle | 1661 |
| The Brothers Karamazov | Fyodor Dostoevsky | 28054 |
| The Call of the Wild | Jack London | 215 |
| The Count of Monte Cristo | Alexandre Dumas | 1184 |
| The Divine Comedy | Dante Alighieri | 1004 |
| The Federalist Papers | Hamilton, Madison, Jay | 1404 |
| The Idiot | Fyodor Dostoevsky | 2638 |
| The Iliad | Homer | 6130 |
| The King James Bible | — | 10 |
| The Odyssey | Homer | 1727 |
| The Picture of Dorian Gray | Oscar Wilde | 174 |
| The Prince | Niccolò Machiavelli | 1232 |
| The Red Badge of Courage | Stephen Crane | 73 |
| The Republic | Plato | 1497 |
| The Scarlet Letter | Nathaniel Hawthorne | 33 |
| The Strange Case of Dr Jekyll and Mr Hyde | Robert Louis Stevenson | 43 |
| The Three Musketeers | Alexandre Dumas | 1257 |
| The Time Machine | H.G. Wells | 35 |
| The War of the Worlds | H.G. Wells | 36 |
| The Wealth of Nations | Adam Smith | 3300 |
| The Yellow Wallpaper | Charlotte Perkins Gilman | 1952 |
| Thus Spake Zarathustra | Friedrich Nietzsche | 1998 |
| Treasure Island | Robert Louis Stevenson | 120 |
| Twenty Thousand Leagues Under the Sea | Jules Verne | 164 |
| Uncle Tom's Cabin | Harriet Beecher Stowe | 203 |
| Walden | Henry David Thoreau | 205 |
| War and Peace | Leo Tolstoy | 2600 |
| Wuthering Heights | Emily Brontë | 768 |

## License

The texts in this repository are public domain via Project Gutenberg. The download script and tooling are part of the [Flux Frontiers](https://github.com/Flux-Frontiers) project.
