<p align="center">
  <img src="assets/logos/logo_512.png" alt="GutenbergKG — The Knowledge Press" width="400"/>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12%20|%203.13-blue.svg" alt="Python"/></a>
  <a href="https://www.elastic.co/licensing/elastic-license"><img src="https://img.shields.io/badge/code-Elastic--2.0-lightgrey.svg" alt="Code License"/></a>
  <a href="https://www.gutenberg.org/"><img src="https://img.shields.io/badge/texts-Public%20Domain-green.svg" alt="Texts License"/></a>
  <img src="https://img.shields.io/badge/version-1.1.0-blue.svg" alt="Version"/>
  <img src="https://img.shields.io/badge/corpus-175%20books-orange.svg" alt="Corpus"/>
  <img src="https://img.shields.io/badge/nodes-856K-green.svg" alt="Nodes"/>
  <img src="https://img.shields.io/badge/edges-16.6M-green.svg" alt="Edges"/>
  <a href="https://github.com/Flux-Frontiers/doc_kg"><img src="https://img.shields.io/badge/DocKG-ready-blue.svg" alt="DocKG"/></a>
  <a href="https://github.com/Flux-Frontiers/KGRAG"><img src="https://img.shields.io/badge/KGRAG-integrated-purple.svg" alt="KGRAG"/></a>
  <a href="https://doi.org/10.5281/zenodo.20045390"><img src="https://zenodo.org/badge/1194808988.svg" alt="DOI"/></a>
</p>

# GutenbergKG — The Knowledge Press

**GutenbergKG** is a universal ingestion engine for digitized text corpora — named for the press that democratized books, built to do the same for structured knowledge.

It transforms the world's great public-domain literature, philosophy, and sacred texts into **queryable knowledge graphs** — enabling semantic search, thematic analysis, and cross-work discovery at a scale and depth that keyword search cannot touch. Ask *what themes connect Dostoevsky and Dante*, trace the evolution of the social contract from Rousseau to Thoreau, or find every passage in the corpus that grapples with revenge — and get semantically grounded answers drawn from the source texts themselves.

The corpus currently spans **175 public-domain masterworks across 13 genres** — 856,242 nodes, 16,563,910 edges — built and fully indexed on an Apple M5 Max in under 10 minutes.

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
| Ancient & Classical | 22 | 134,200 | 2,187,293 |
| Philosophy | 25 | 108,923 | 1,161,328 |
| Russian Literature | 13 | 90,276 | 2,760,956 |
| American Literature | 23 | 90,494 | 859,696 |
| French Literature | 12 | 89,627 | 3,264,872 |
| Science Fiction | 19 | 70,670 | 958,530 |
| World Literature | 5 | 14,898 | 1,577,512 |
| Sacred Texts | 6 | 16,362 | 748,731 |
| German Literature | 5 | 13,124 | 609,413 |
| Audel Electric (IA) | 3 | 22,922 | 168,745 |
| Spanish Literature | 1 | 11,438 | 121,414 |
| Shakespeare | 4 | 6,259 | 83,127 |
| **Total** | **175** | **856,242** | **16,563,910** |

The full book list, organized by genre, is in the [Books in the Corpus](#books-in-the-corpus) section below. Planned additions are tracked in [`docs/CORPUS_WISHLIST.md`](docs/CORPUS_WISHLIST.md).

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
```

---

## Strategic Partners & Sponsors Wanted

GutenbergKG is one node in a larger initiative — the **Tree of Knowledge** — a federated network of domain knowledge graphs unified by [KGRAG](https://github.com/Flux-Frontiers/KGRAG). The goal: a persistent, publicly queryable graph of humanity's written heritage, queryable without an LLM, composable with one.

This is not a call for open contributions. We are seeking **targeted partners** who bring infrastructure, institutional reach, or commercial interest to the table.

### Hosting & Infrastructure Sponsors

The corpus SQLite + LanceDB indices are modest in size but need persistent, reliable hosting to serve researchers and developers. We are looking for sponsors willing to provide compute and storage in exchange for prominent attribution, early access to new corpora, and co-branding on the public instance.

### Licensing Partners

[KGRAG](https://github.com/Flux-Frontiers/KGRAG) and [DocKG](https://github.com/Flux-Frontiers/doc_kg) are the infrastructure that powers this corpus — and every other knowledge graph in the Tree of Knowledge ecosystem. Organizations building AI-assisted research tools, enterprise knowledge management, or domain-specific retrieval systems can license the stack for internal or commercial deployment.

### Research Collaborators

Digital humanities centers, computational linguistics labs, library science programs, and AI research groups with aligned missions. We are particularly interested in partners who can extend the corpus into non-English languages, underrepresented traditions, or specialized technical domains.

### Why now

175 works, 16 million edges, production-ready pipeline. The architecture is federated by design — new corpora slot in without touching the existing graph. The ingestion tooling is fast and fully automated. The query layer is proven. This is the inflection point before the graph becomes too large for any single team to steer.

**To discuss a partnership:** [suchanek@flux-frontiers.com](mailto:suchanek@flux-frontiers.com)

---

## Books in the Corpus

### English Literature (37)

| Title | Author |
|---|---|
| A Modest Proposal | Jonathan Swift |
| A Room with a View | E.M. Forster |
| A Tale of Two Cities | Charles Dickens |
| Alice's Adventures in Wonderland | Lewis Carroll |
| Bleak House | Charles Dickens |
| Cranford | Elizabeth Gaskell |
| David Copperfield | Charles Dickens |
| Dracula | Bram Stoker |
| Emma | Jane Austen |
| Far from the Madding Crowd | Thomas Hardy |
| Frankenstein | Mary Shelley |
| Great Expectations | Charles Dickens |
| Grimms' Fairy Tales | Brothers Grimm |
| Gulliver's Travels | Jonathan Swift |
| Heart of Darkness | Joseph Conrad |
| Howards End | E.M. Forster |
| Jane Eyre | Charlotte Brontë |
| Kim | Rudyard Kipling |
| Middlemarch | George Eliot |
| North and South | Elizabeth Gaskell |
| Pride and Prejudice | Jane Austen |
| Robinson Crusoe | Daniel Defoe |
| Sense and Sensibility | Jane Austen |
| Tess of the d'Urbervilles | Thomas Hardy |
| The Adventures of Sherlock Holmes | Arthur Conan Doyle |
| The Jungle Book | Rudyard Kipling |
| The Man Who Was Thursday | G.K. Chesterton |
| The Mayor of Casterbridge | Thomas Hardy |
| The Picture of Dorian Gray | Oscar Wilde |
| The Portrait of a Lady | Henry James |
| The Strange Case of Dr Jekyll and Mr Hyde | Robert Louis Stevenson |
| The Time Machine | H.G. Wells |
| The Turn of the Screw | Henry James |
| The War of the Worlds | H.G. Wells |
| Treasure Island | Robert Louis Stevenson |
| Vanity Fair | William Makepeace Thackeray |
| Wuthering Heights | Emily Brontë |

### Philosophy (25)

| Title | Author |
|---|---|
| A Vindication of the Rights of Woman | Mary Wollstonecraft |
| Apology | Plato |
| Beyond Good and Evil | Friedrich Nietzsche |
| Common Sense | Thomas Paine |
| Critique of Pure Reason | Immanuel Kant |
| Discourse on Method | René Descartes |
| Essays — First and Second Series | Ralph Waldo Emerson |
| Groundwork of the Metaphysics of Morals | Immanuel Kant |
| Leviathan | Thomas Hobbes |
| Nicomachean Ethics | Aristotle |
| On Liberty | John Stuart Mill |
| On the Duty of Civil Disobedience | Henry David Thoreau |
| On the Origin of Species | Charles Darwin |
| Phaedo | Plato |
| Poetics | Aristotle |
| Politics | Aristotle |
| The Art of War | Sun Tzu |
| The Federalist Papers | Hamilton, Madison, Jay |
| The Prince | Niccolò Machiavelli |
| The Problems of Philosophy | Bertrand Russell |
| The Social Contract | Jean-Jacques Rousseau |
| The Symposium | Plato |
| The Wealth of Nations | Adam Smith |
| Thus Spake Zarathustra | Friedrich Nietzsche |
| Utilitarianism | John Stuart Mill |

### Ancient & Classical (23)

| Title | Author |
|---|---|
| A Selection from the Discourses of Epictetus | Epictetus |
| Histories | Herodotus |
| History of the Peloponnesian War | Thucydides |
| Medea | Euripides |
| Meditations | Marcus Aurelius |
| Metamorphoses | Ovid |
| Oedipus King of Thebes | Sophocles |
| On Duties (De Officiis) | Cicero |
| On the Nature of Things | Lucretius |
| Oresteia | Aeschylus |
| Parallel Lives | Plutarch |
| The Aeneid | Virgil |
| The Bible (King James Version) | — |
| The Birds | Aristophanes |
| The Clouds | Aristophanes |
| The Consolation of Philosophy | Boethius |
| The Eleven Comedies Vol. I & II | Aristophanes |
| The Frogs | Aristophanes |
| The Iliad | Homer |
| The Odyssey | Homer |
| The Republic | Plato |

### American Literature (23)

| Title | Author |
|---|---|
| Adventures of Huckleberry Finn | Mark Twain |
| Leaves of Grass | Walt Whitman |
| Moby Dick | Herman Melville |
| My Ántonia | Willa Cather |
| Narrative of the Life of Frederick Douglass | Frederick Douglass |
| O Pioneers! | Willa Cather |
| Tales of Mystery and Imagination | Edgar Allan Poe |
| The Age of Innocence | Edith Wharton |
| The Awakening | Kate Chopin |
| The Call of the Wild | Jack London |
| The House of Mirth | Edith Wharton |
| The Jungle | Upton Sinclair |
| The Legend of Sleepy Hollow | Washington Irving |
| The Raven and Other Poems | Edgar Allan Poe |
| The Red Badge of Courage | Stephen Crane |
| The Scarlet Letter | Nathaniel Hawthorne |
| The Sea-Wolf | Jack London |
| The Souls of Black Folk | W.E.B. Du Bois |
| The Yellow Wallpaper | Charlotte Perkins Gilman |
| Uncle Tom's Cabin | Harriet Beecher Stowe |
| Up From Slavery | Booker T. Washington |
| Walden | Henry David Thoreau |
| White Fang | Jack London |

### Russian Literature (13)

| Title | Author |
|---|---|
| Anna Karenina | Leo Tolstoy |
| Childhood, Boyhood, Youth | Leo Tolstoy |
| Crime and Punishment | Fyodor Dostoevsky |
| Dead Souls | Nikolai Gogol |
| Fathers and Sons | Ivan Turgenev |
| Notes from Underground | Fyodor Dostoevsky |
| Oblomov | Ivan Goncharov |
| On the Eve | Ivan Turgenev |
| The Brothers Karamazov | Fyodor Dostoevsky |
| The Idiot | Fyodor Dostoevsky |
| The Overcoat | Nikolai Gogol |
| The Possessed (Demons) | Fyodor Dostoevsky |
| War and Peace | Leo Tolstoy |

### French Literature (12)

| Title | Author |
|---|---|
| Around the World in Eighty Days | Jules Verne |
| Candide | Voltaire |
| From the Earth to the Moon | Jules Verne |
| Germinal | Émile Zola |
| Journey to the Center of the Earth | Jules Verne |
| Les Misérables | Victor Hugo |
| Madame Bovary | Gustave Flaubert |
| Nana | Émile Zola |
| The Count of Monte Cristo | Alexandre Dumas |
| The Hunchback of Notre-Dame | Victor Hugo |
| The Three Musketeers | Alexandre Dumas |
| Twenty Thousand Leagues Under the Sea | Jules Verne |

### Science Fiction (19)

| Title | Author |
|---|---|
| A Journey to Other Worlds | John Jacob Astor |
| A Princess of Mars | Edgar Rice Burroughs |
| At the Earth's Core | Edgar Rice Burroughs |
| At the Mountains of Madness | H.P. Lovecraft |
| Flatland | Edwin Abbott |
| Frankenstein | Mary Shelley |
| Herbert West: Reanimator | H.P. Lovecraft |
| Pellucidar | Edgar Rice Burroughs |
| The Call of Cthulhu | H.P. Lovecraft |
| The Dunwich Horror | H.P. Lovecraft |
| The First Men in the Moon | H.G. Wells |
| The Food of the Gods | H.G. Wells |
| The Gods of Mars | Edgar Rice Burroughs |
| The Invisible Man | H.G. Wells |
| The Island of Doctor Moreau | H.G. Wells |
| The Lost World | Arthur Conan Doyle |
| The Shadow over Innsmouth | H.P. Lovecraft |
| The Warlord of Mars | Edgar Rice Burroughs |
| When the World Screamed | Arthur Conan Doyle |

### Sacred Texts (6)

| Title | Tradition |
|---|---|
| The Analects of Confucius | Confucian |
| The Bhagavad Gita | Hindu |
| The Quran (Yusuf Ali translation) | Islamic |
| Tao Te Ching | Taoist |
| The Torah / Tanakh (JPS 1917) | Jewish |
| The Upanishads (Max Müller) | Hindu |

### German Literature (5)

| Title | Author |
|---|---|
| Faust Part I | Johann Wolfgang von Goethe |
| Faust Part II | Johann Wolfgang von Goethe |
| Siddhartha | Hermann Hesse |
| The Metamorphosis | Franz Kafka |
| The Trial | Franz Kafka |

### World Literature (5)

| Title | Author/Tradition |
|---|---|
| Gitanjali | Rabindranath Tagore |
| One Thousand and One Nights | Arabian tradition |
| The Divine Comedy: Inferno | Dante Alighieri |
| The Divine Comedy: Purgatorio | Dante Alighieri |
| The Divine Comedy: Paradiso | Dante Alighieri |

### Shakespeare (4)

| Title |
|---|
| A Midsummer Night's Dream |
| Hamlet |
| Macbeth |
| Romeo and Juliet |

### Spanish Literature (1)

| Title | Author |
|---|---|
| Don Quixote | Miguel de Cervantes |

### Technical Reference — Internet Archive (3)

| Title | Source |
|---|---|
| Audels Practical Electricity | Internet Archive |
| Audels Electric Motors Guide | Internet Archive |
| Audels Radiomans Guide | Internet Archive |

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
                  175 public-domain masterworks across 13 genres as queryable
                  knowledge graphs via DocKG and KGRAG}
}
```

**APA:**

> Suchanek, E. G. (2026). *GutenbergKG: The Knowledge Press* (Version 1.1.0) [Software]. Flux-Frontiers. https://doi.org/10.5281/zenodo.20045390

---

## License

The texts in this repository are **public domain**. They were sourced from [Project Gutenberg](https://www.gutenberg.org/) and the [Internet Archive](https://archive.org/); GutenbergKG is an independent project with no affiliation with or endorsement from either organization. The download scripts and tooling are part of the [Flux Frontiers](https://github.com/Flux-Frontiers) project and are released under the [Elastic License 2.0](https://www.elastic.co/licensing/elastic-license).
