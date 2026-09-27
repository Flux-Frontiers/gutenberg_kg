---
name: add-book
description: >
  Add a new book to GutenbergKG and deploy it to every surface: the corpus
  (per-book DocKG + KGRAG registry), the consolidated bundle
  (bundles/gutenberg-all), the on-device Swift packs, the worker container
  image (local and Docker Hub), the Knowledge Press web forest catalog, and
  the corpus docs. Use when Eric downloads, or wants to download, a new
  Project Gutenberg or Internet Archive book and have it "deployed", "shipped",
  "rolled out" or "live everywhere"; also when a book is present in corpus/
  but missing from the bundle, the app, the image or the web forest.
---

# Add a book end to end

One book moves through six surfaces, in this order. Each stage reads the
previous stage's output, so a skipped stage is invisible downstream until
someone searches for the book and it is not there.

| # | Surface | Artifact | Produced by |
|---|---|---|---|
| 1 | Corpus | `corpus/<genre>/<book>/` (`.md`, `reference.md`) | `gutenkg download book` / `gutenkg ia download` |
| 2 | Per-book index | `corpus/<genre>/<book>/.dockg/` + KGRAG registry entry | `gutenkg ingest` |
| 3 | Bundle | `bundles/gutenberg-all/.dockg/` | `gutenkg build-corpus --update` |
| 4 | On-device packs | `bundles/gutenberg-all/swift/` | `make export-swift` |
| 5 | Worker image | `corpus-gutenberg:latest`, then Docker Hub | `make build`, `make publish-worker-image` |
| 6 | Web forest | `../knowledge_press/web/src/game/catalog*.ts` | `make export-web-catalog` |

Plus the bookkeeping that rides along: genre catalog, author pages, audit,
`docs/CORPUS.md` and README counts, a corpus snapshot.

Work from `/Users/egs/repos/gutenberg_kg`. Every `gutenkg` call is
`poetry run gutenkg` (the Makefile does the same) so a stale global install
is never used.

## Rules that apply throughout

- **Eric launches the long runs.** `build-corpus`, `export-swift`, image
  builds and `publish-worker-image` take minutes to tens of minutes. Hand
  over the exact command and wait for Eric to report back. Do not background
  them and never pipe them through `tail`.
- **Verify each stage by positive assertion** before starting the next one:
  query the artifact and confirm the new book is in it. "The command exited
  0" is not verification.
- **Ask before anything outward-facing:** pushing to Docker Hub, opening a
  PR, pushing a branch.
- **Branch first.** Never commit to `main` in either repo. Run
  `pre-commit run --all-files` before staging. Write commit and PR bodies to
  a file and pass `-F` / `--body-file`, never a heredoc.
- **Batch books.** Stages 1-2 run per book; stages 3-6 cost the same for one
  book or ten. When Eric is adding several, do stages 1-2 for all of them,
  then 3-6 once.

## Stage 0 -- Preflight

```bash
git branch --show-current          # must not be main; else: git switch -c feat/add-<slug>
git status --short                 # clean, or only this work
python3 scripts/check_pins.py      # image build refuses drifted pins anyway
```

Collect from Eric (or look up): the Gutenberg ebook ID (or IA identifier)
and the genre. If the genre is new, see "New genre" at the end. If the book is
a diary, see "Diaries" at the end; the path differs from stage 2 onward.

Check that the ID is not already in the corpus under another genre:

```bash
rg -l '<ID>' corpus/*/*/reference.md scripts/catalogs/
```

## Stage 1 -- Download

```bash
poetry run gutenkg download search --author "<author>"          # if the ID is unknown
poetry run gutenkg download book <ID> --genre <genre> --dry-run
poetry run gutenkg download book <ID> --genre <genre>
# IA: poetry run gutenkg ia download <identifier> --genre <genre>
```

Verify:

```bash
ls "corpus/<genre>/<book>/"                  # the .md and reference.md are present
rg -n 'Gutenberg|Author|Title' "corpus/<genre>/<book>/reference.md" | head
```

Read the head and tail of the `.md`. The Gutenberg license header and footer
must be stripped, and the front matter (introduction, preface, contents) must
not swamp the text; front-matter chunks dominate retrieval seeds. The headings
must be real chapter headings, since they become the Browse sections.

Fix text problems now. Any text change after stage 3 forces a **full**
`build-corpus`, not `--update` (see stage 3).

## Stage 2 -- Per-book index and bookkeeping

```bash
poetry run gutenkg ingest --genre <genre>         # builds only books lacking .dockg/
poetry run gutenkg catalog-sync --genre <genre>   # idempotent; records the ID in scripts/catalogs/<genre>.txt
poetry run gutenkg authors                        # regenerates corpus/authors/
poetry run gutenkg audit --genre <genre>          # must exit 0
```

Verify:

```bash
ls "corpus/<genre>/<book>/.dockg/graph.sqlite"
sqlite3 "corpus/<genre>/<book>/.dockg/graph.sqlite" "select count(*) from nodes where kind='chunk'"
rg -n '<ID>' scripts/catalogs/<genre>.txt
poetry run gutenkg query "<a phrase you know is in the book>"
poetry run python scripts/check_sections.py   # flags a book whose text sits in one oversized section
```

The chunk count must be non-trivial for the book's length (a novel is
hundreds to thousands). The query's top hits must come from this book's body,
not from its `reference.md` or preface.

## Stage 3 -- Bundle (Eric runs it)

For a **newly added book** whose text will not change again, the incremental
path is correct and takes minutes:

```bash
poetry run gutenkg build-corpus --update
```

Use `gutenkg build-corpus` directly, not `make build-corpus`: the make target
first force-rechunks and rebuilds every diary, which a prose book does not
need.

**`--update` is id-based, not content-based.** It embeds nodes whose ids are
new and keeps existing vectors for ids it has seen. A brand-new book is all
new ids, so it is fine. If this batch also *edited the text* of a book that
was already in the bundle, the edited book keeps stale vectors silently.
Then the command is the full rebuild, about 24 minutes:

```bash
poetry run gutenkg build-corpus
```

Verify (the file_path prefix is `<genre>/<book>/`):

```bash
sqlite3 bundles/gutenberg-all/.dockg/graph.sqlite \
  "select count(*) from nodes where kind='chunk' and file_path like '<genre>/<book>/%'"
```

The count must match the per-book count from stage 2, give or take the
chunks built from `reference.md`. Zero means the book did not reach the
bundle.

## Stage 4 -- On-device packs (Eric runs it)

```bash
make export-swift          # gutenkg export-swift --bundle bundles/gutenberg-all --verify --force
```

Verify:

```bash
sqlite3 bundles/gutenberg-all/swift/core.pack \
  "select key, title, author, ebook_id from books where key='<genre>/<book>'"
sqlite3 bundles/gutenberg-all/swift/gutenberg.pack \
  "select kind, count(*), count(vector_index) from passages where file_path like '<genre>/<book>/%' group by kind"
python3 -c "import json;m=json.load(open('bundles/gutenberg-all/swift/manifest.json'));print(m['generated'], m['verification'])"
```

The book row must be present with the right author and ID, the book must
have chunk and section passages with vectors, `generated` must
be from today, and the recall in `verification` must not drop against the
previous export (0.95+ at @10).

To put the new packs on devices, from `../knowledge_press`:
`make ios-deploy` (one phone), `make ios-push-all` (every paired device),
or `make mac-dev-run` for the Mac app. These read
`$(GUTENBERG_KG_DIR)/bundles/gutenberg-all/swift` and do not re-export.

## Stage 5 -- Worker image (Eric runs it)

The Dockerfile `COPY`s `bundles/gutenberg-all/` into the image, so the image
is stale until rebuilt after stage 3.

```bash
make build                 # or: make build-all  (Docker and Apple container keep separate stores)
make run                   # worker on :8000; loading the index takes a while
make query Q="<a phrase you know is in the book>"
```

The query must return hits from the new book. Then `make down`.

Publishing is outward-facing and uploads several GB. **Ask first.** Eric
launches it, from the Docker runtime (pushes from `RUNTIME=apple` have failed
on the keychain):

```bash
make publish-worker-image RUNTIME=docker
docker buildx imagetools inspect docker.io/egsuchanek/corpus-gutenberg:latest
```

The inspect must list both `linux/amd64` and `linux/arm64`. The full procedure
is in `docs/INSTALLATION.md`, "Publishing the worker image".

## Stage 6 -- Web forest catalog

```bash
make export-web-catalog    # writes ../knowledge_press/web/src/game/catalog*.ts
```

It reads the per-book `.dockg/` graphs from stage 2, not the bundle. Verify
in `../knowledge_press`:

```bash
rg -n 'title: "<title>"' web/src/game/catalog*.ts
git diff --stat web/src/game/
make web-test && make web-build
```

The diff should add the new book and change little else. A large unrelated
diff means chunk counts moved for other books; stop and find out why before
committing.

The web forest deploys to GitHub Pages
(https://flux-frontiers.github.io/knowledge_press/) when a change under
`web/` lands on `main`. So: branch in `knowledge_press`, commit the catalog,
and **ask** before pushing and opening the PR. Merging it is the deploy.

## Stage 7 -- Docs, snapshot, commit

```bash
poetry run python scripts/sync_corpus_docs.py --check   # shows what drifted
poetry run python scripts/sync_corpus_docs.py           # README badges/table/prose, docs/CORPUS.md, docs/PARTNERS.md
poetry run gutenkg snapshot save                        # no version: a corpus change is keyed on its timestamp
```

Stage in `gutenberg_kg` only what this work produced. The indices and
`bundles/` are gitignored and must not appear:

```bash
git add "corpus/<genre>/<book>/" scripts/catalogs/<genre>.txt corpus/authors/ \
        corpus/.snapshots/ README.md docs/CORPUS.md docs/PARTNERS.md
git status --short
```

Commit as `feat(corpus): add <Title> (<Author>, #<ID>)`, and add a line
under `## [Unreleased]` in `CHANGELOG.md`. Ask before pushing and opening
the PR.

## Final report

End with a checklist that states the verified result of each surface, and
names any stage that was skipped or is still waiting on Eric:

```
[x] corpus        corpus/<genre>/<book>/ , catalog ID <ID>, audit clean
[x] per-book KG   <N> chunks, registered
[x] bundle        <N> chunks under <genre>/<book>/
[x] swift packs   books row present, recall@10 <r>
[x] image         local :latest serves it | [ ] Docker Hub (not published)
[x] web catalog   knowledge_press PR #<n> | [ ] not yet merged (not deployed)
[x] docs          README/CORPUS.md synced, snapshot <key>
```

## Variants

**Several books.** Stages 1-2 once per book (or `gutenkg download catalog
<file> --genre <g>` for a list), then stages 3-7 once.

**New genre.** Before stage 1: `poetry run gutenkg genres add <genre>
--source gutenberg` (or `ia`), and create `scripts/catalogs/<genre>.txt`. The
`--genre` choices are read from `corpus/genres.json`, so the new genre is
accepted from then on. `regenerate_corpus_doc.GENRE_ORDER` also needs the
new genre, or it drops out of `docs/CORPUS.md`.

**Diaries.** A diary is indexed by the DiaryKG pipeline, not `ingest`. It
needs a `.diary_format` and a parser that handles its date headers. Stage 2
becomes `make build-diaries` (force-rechunks every diary), and stage 3
becomes `poetry run gutenkg build-corpus --diaries-only`, which re-bundles
the diary indices into the existing bundle. After stage 4, verify with
`sqlite3 bundles/gutenberg-all/swift/diaries.pack "select kg_name, count(*) from passages group by kg_name"`:
the new diary's slug must be listed. Stages 4-7 are unchanged.

**Changed text of an existing book.** This is not an add, but it uses the same
path: re-ingest with `gutenkg ingest --genre <g> --force-build`, then a
**full** `build-corpus` (never `--update`), then stages 4-7.

## Out of scope

- The RunPod serverless index push (`runpod/push_indices.sh`) is deferred and
  is not part of this pipeline.
- Selective bundles (`bundles/specs/*.toml`) are rebuilt with
  `gutenkg bundle make <spec> --verify --image`. They pick up the new book
  only when their spec selects its genre or the book itself; see
  `docs/BUNDLES.md`.
- Cutting a release is `/release`.
