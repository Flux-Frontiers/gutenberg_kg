# IA Catalog Workflow: Discovering and Curating Internet Archive Books

How to take a genre from "there might be good material on archive.org" to a
downloaded, ingested, catalogued corpus.

Ported from `ia_kg`, which this repo supersedes, and updated for `gutenkg ia`.

---

## Overview

A **catalog file** is a tab-separated list of Internet Archive identifiers that
records what a genre holds. You build it from search results -- curating
identifiers and overriding titles -- before committing to a bulk download.

```
scripts/catalogs/<genre>.txt   ->   gutenkg ia catalog   ->   corpus/<genre>/
```

Catalogs are also written *back* to: `gutenkg ia download` records every book it
fetches, and `gutenkg catalog-sync` repairs anything missing. So the catalog is
both the input manifest and the record of what the corpus contains, and
`gutenkg audit` warns when the two disagree.

---

## Step 1 -- Search for identifiers

```bash
gutenkg ia search "audels electric library" --max-results 25
```

```
Identifier                        Year   Title
-----------------------------------------------------------------------
audels-electric-library-vol-1    1929   Audels Electric Library Vol. 1
audels-electric-library-vol-2    1929   Audels Electric Library Vol. 2
```

IA metadata is inconsistent, so try several phrasings. Narrowing by author or
year helps (`"audels plumbers guide" author:graesser`).

---

## Step 2 -- Export a draft catalog

```bash
gutenkg ia search "audels electric library" --max-results 25 \
    --export-catalog scripts/catalogs/audel-electric.txt
```

Every result is written **commented out**, so an un-reviewed draft downloads
nothing if handed straight to `gutenkg ia catalog`:

```
# Catalog draft — IA search: audels electric library
# Every line is commented out. Uncomment the ones you want.
# Format: <identifier>[TAB<title>]  (comment lines start with #)
# Check rights before uncommenting: an IA hit's year is the edition
# scanned, not evidence the text is free.

# audels-electric-library-vol-1	Audels Electric Library Vol. 1	# 1929
# audelsnewelectri0004unse	Audels New Electric Library (Volume IV)	# 1963
```

Run several searches into different draft files and combine them while curating.

---

## Step 3 -- Check rights before uncommenting anything

**This is the step that matters most, and the one search results actively
mislead you about.** The year in a search result is the year of the *edition
that was scanned*, not evidence the text is free. Three items rejected from this
corpus all looked like period pieces in search output:

| Item | Looked like | Actually |
|---|---|---|
| `XiccarphClarkAshtonSmith…` | a 1972 listing | a scan of an in-copyright 1972 paperback |
| `hollow-earth-tales-free-e-book` | free pulp reprints | a 2020 compilation under CC BY-NC-ND |
| `audelsnewelectri008004mbp` | one of a 1929 set | a 1962 edition of a different series |

Pull the metadata before committing to a download:

```bash
curl -s "https://archive.org/metadata/<identifier>" | python -m json.tool | head -40
```

Read these fields:

- **`date` / `year`** -- the edition's publication year. Anything after 1929 needs
  a positive reason to believe it is public domain.
- **`licenseurl`** -- an explicit licence. **`-ND` (NoDerivatives) is
  disqualifying**: chunking, embedding and serving excerpts is exactly the
  derivative use it forbids. `-NC` conflicts with a public corpus.
- **`collection`** -- `folkscanomy`, `americana` and library collections are
  usually genuine digitisations. `universallibrary` is a bulk project that swept
  up in-copyright material.
- **`uploader`** -- a personal account uploading a recent commercial edition is a
  strong warning sign.

When an item fails, record the rejection in `docs/CORPUS_WISHLIST.md` with a
strikethrough and the reason, so nobody re-finds it and re-downloads it.

---

## Step 4 -- Curate the catalog

1. **Uncomment** the lines you want (drop the leading `# `).
2. **Delete or leave commented** the rest.
3. **Override titles** by editing the text after the tab. This is where curation
   lives: the override becomes the directory name, and IA titles are often
   unusable -- one Audel volume's ran past 100 characters.
4. **Add notes** as comments for the next reader.

```
# Audel Electric Library — curated 2026-09-02
# 1929 edition, public domain. Vols 5 and 6 have no 1929 scan on IA;
# only New Electric Library editions from 1960-63, which are in copyright.

audels-electric-library-vol-1	Audels Electric Library Vol 1
audels-electric-library-vol-2	Audels Electric Library Vol 2
```

The title override must match the book's directory name once downloaded, because
`gutenkg audit` reports a catalog title that differs from its directory.

---

## Step 5 -- Test one book

```bash
gutenkg ia download audels-electric-library-vol-1 --genre audel-electric
```

Check `corpus/audel-electric/` -- confirm the Markdown reads cleanly and
`reference.md` is present.

**Inspect the head of the Markdown.** IA text is OCR of scanned pages, and
Google-digitised items open with pages of scanning boilerplate that will
otherwise be ingested as though the author wrote it. The Houdini volume in
`curiosities` needed 43 such lines stripped by hand.

---

## Step 6 -- Download the full catalog

```bash
gutenkg ia catalog scripts/catalogs/audel-electric.txt
```

Genre is inferred from the filename stem (`audel-electric.txt` -> genre
`audel-electric`); `--genre` overrides it. Inference only applies when the stem
is a known genre, so a stray filename cannot invent one.

```bash
gutenkg ia catalog scripts/catalogs/audel-electric.txt --dry-run   # preview
gutenkg ia catalog scripts/catalogs/audel-electric.txt --force     # re-download
```

Re-running is safe. Downloads are idempotent on the IA identifier, not the
output path, so re-running with a changed title override skips the item rather
than writing a second copy of it under the new name.

---

## Step 7 -- Ingest, then verify

```bash
gutenkg ia survey --genre audel-electric     # md / ref / kg per book
gutenkg ingest --genre audel-electric        # build the DocKG indices
gutenkg audit                                # verify the whole corpus
```

`audit` is the check that closes the loop. It reports a book missing from its
catalog, a catalog title that disagrees with its directory, and a duplicate IA
identifier across two directories.

If it reports books "not recorded in scripts/catalogs/<genre>.txt", repair them
without re-downloading:

```bash
gutenkg catalog-sync --dry-run     # what it would add
gutenkg catalog-sync               # add it
```

---

## Catalog file format

```
# Comment lines are ignored (leading #)
<identifier>
<identifier><TAB><title override>
```

- **Identifier** -- the Internet Archive item identifier, the slug in its URL.
  Globally unique and immutable, which is why it keys idempotence, the catalog,
  and duplicate detection.
- **Title override** (optional) -- the directory name under `corpus/<genre>/`.
  Without it the title is taken from IA metadata at download time, uncurated.
- Place the file at `scripts/catalogs/<genre>.txt`.

Gutenberg catalogs share this shape with a numeric ID in place of the
identifier. A genre is either Gutenberg or IA and never both, so which parser
reads a given file is unambiguous.

---

## Adding a new genre

```bash
gutenkg genres add <genre> --source ia
gutenkg ia search "<terms>" --export-catalog scripts/catalogs/<genre>.txt
# curate: check rights, uncomment, override titles
gutenkg ia catalog scripts/catalogs/<genre>.txt
gutenkg ingest --genre <genre>
gutenkg audit
```
