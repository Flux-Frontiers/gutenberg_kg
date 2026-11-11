# Release Notes -- v1.35.0

> Released: 2026-11-10

### Added

- **A literary year for every corpus work.** `corpus/pub_dates.tsv` gives
  each of the 265 works the year it was first published, performed or (for
  ancient and sacred texts) composed, with its source and confidence. It is
  the data behind the Knowledge Press forest's timeline slider.
  `scripts/lookup_pub_dates.py` resolves it from hand dates in
  `corpus/pub_dates_overrides.tsv`, the year each reference summary states,
  and Wikidata (by Gutenberg ebook ID, or by title among the author's works
  found by Gutenberg author ID). A year after the author's death becomes the
  death year; a set's volumes share the first volume's year. No
  `reference.md` is changed.
- **`gutenkg export-web-catalog` writes each book's `year`.** The Knowledge
  Press catalog gains an optional `year` per book, read from
  `corpus/pub_dates.tsv`. A corpus without the table exports as before.

### Documentation

- **Literary years guide** (`docs/PUB_DATES.md`): how each year is resolved,
  the overrides conventions, the confidence breakdown, reviewing conflicts and
  regenerating the table. Linked from the README, the cheatsheet and the
  Knowledge Press page.
- **Interactive literary-years charts in the guide.** `scripts/plot_pub_dates.py`
  writes `docs/assets/literary_years.html` from `corpus/pub_dates.tsv`: works
  by era, each genre's span with one dot per work, the confidence and source
  breakdowns, and the years to review. Plotly, following the site's light or
  dark scheme; `docs/PUB_DATES.md` embeds it.

### Changed

- **kg-rag floor 0.18.2** (pyproject, Dockerfile `KG_RAG_VERSION`, runpod).

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
