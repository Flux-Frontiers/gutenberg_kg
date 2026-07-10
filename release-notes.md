# Release Notes — v1.8.0

> Released: 2026-07-10

GutenbergKG 1.8.0 smooths the rough edges of first-run setup and corpus
integrity. A new `gutenkg init` command pulls the local ML models the pipeline
needs before you touch any data, so a fresh clone no longer dies halfway through
a build with a missing-model error. Alongside it, the deployed chat app gains a
full corpus browser, a smarter model picker, and an audit check that catches the
insidious class of bug where a book's declared title and its actual text quietly
disagree.

## What changed

**One-shot model setup.** `gutenkg init` fetches the spaCy and embedder models
the local pipeline depends on, meant to be run once after cloning and
`poetry install`. It fails fast and legibly up front instead of letting
`chunk-diaries` / `ingest` / `build-corpus` blow up mid-run on a model that was
never downloaded. Pass `--check` to report model status without downloading.
Docker builds don't need it — the image pre-downloads the embedder at build time
and never runs spaCy at runtime.

**Read the corpus, not just search it.** A new "Browse" page in the deployed app
lets you walk every book by genre and read it chapter by chapter, reconstructed
from the DocKG section/chunk nodes already baked into the worker's index — no raw
corpus text needs to ship in the image. Four new handler ops (`list_genres`,
`list_books`, `get_chapters`, `get_chapter`) serve it through the existing
`/runsync` endpoint next to search.

**A model picker that doesn't sabotage answers.** The synthesis model dropdown
now filters out reasoning models (Agents-A1, DeepSeek-R1, gpt-oss) and non-chat
utility models (document converters, embedders). Their chain-of-thought prose
isn't reliably strippable and was truncating RAG answers before the real
response ever arrived.

**Catching mislabeled books.** `gutenkg audit` now compares each book's
`reference.md` title against the title quoted in its auto-generated summary
(sourced from the real fetched text) and flags a divergence as an error —
surfacing a wrong Gutenberg ID that would otherwise silently mislabel a whole
book. A `KNOWN_TITLE_VARIANTS` allowlist exempts legitimate alternate
titles and translations. The check drove a corpus-wide relabel/re-fetch pass
across nine genres, plus ~40 new author pages and a regenerated `docs/CORPUS.md`.

## Upgrading

After pulling, run `gutenkg init` once to make sure the local models are present
before your next build. No data migration is required, and existing consolidated
bundles keep working — rebuild only if you want the corpus relabels and the
refreshed author index. The new Browse page and model-picker filtering are
served automatically by the updated handler; redeploy the worker image to pick
them up.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
