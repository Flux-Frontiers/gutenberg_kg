# Literary years

Every work in the corpus carries a literary year: the year it was first
published, first performed or, for ancient and sacred texts, composed. The
Knowledge Press forest uses it for its timeline slider, where each tree appears
at its work's year. Negative years are BC.

## Files

| File | What it holds | Edited by |
|---|---|---|
| `corpus/pub_dates.tsv` | The resolved year for each of the 265 works, with its source, confidence, flags and the evidence behind it | `scripts/lookup_pub_dates.py` (do not hand-edit) |
| `corpus/pub_dates_overrides.tsv` | 62 hand-dated works, each with its basis (`published`, `performed` or `composed`), confidence (`exact` or `approx`) and a note | Hand |
| `scripts/lookup_pub_dates.py` | The resolver | Code |

Both tables are keyed by `entry`, the `genre/Book Folder` path under
`corpus/`. No `reference.md` is read for writing or changed.

## How a year is chosen

Each work is resolved in this order. The first step that gives a year wins.

1. **A hand date** from `pub_dates_overrides.tsv`.
2. **A local `## Publication` date** in `reference.md` (Internet Archive works).
3. **Two lookups, cross-checked:**
    - the year the `## Summary` in `reference.md` states ("published in 1884");
    - Wikidata, matched by the Project Gutenberg ebook ID (P2034) and followed
      from an edition to its work (P629). Publication (P577) and first
      performance (P1191) beat inception (P571). A match is kept only when its
      label fits the entry's title. With no ebook match, Wikidata is searched
      by title among the author's works, the author found by Gutenberg author
      ID (P1938).

    Agreement within two years is `high` confidence. One source alone is
    `medium`. Disagreement is `conflict`; it takes the earlier year that falls
    within the author's life.

4. **An estimate** when nothing else dates the work: birth + 40, or death - 10,
    at `low` confidence. No current work needs one.

Two rules then apply to every row:

- A year after the author's death becomes the death year, flagged
  `clamped-from-<year>`. Posthumous publication is real, but the forest places
  a work in its author's lifetime.
- Every volume of a multi-volume set takes its first volume's year.

The hand dates follow fixed conventions: sacred texts by original composition,
diaries and letters by the first entry in the text, sets by the first volume.
The Audel volumes are all 1929.

## The corpus today

| Confidence | Works | Meaning |
|---|---|---|
| `high` | 97 | Summary and Wikidata agree within two years |
| `medium` | 98 | One source only |
| `hand` | 62 | From the overrides file |
| `conflict` | 8 | The sources disagree; the earlier year was taken |

By source: 97 summary and Wikidata, 74 summary only, 32 Wikidata only, 62
override. Four Wikidata years are `approx` (Herodotus, Ovid, Plutarch,
Plato's *Phaedo*) and two were clamped to the author's death (Mill's
*Autobiography*, Marlowe's *Doctor Faustus*).

<iframe src="../assets/literary_years.html" title="Corpus literary years: charts"
        style="width: 100%; height: 2400px; border: 0;" loading="lazy"></iframe>

The charts are written by `scripts/plot_pub_dates.py` from
`corpus/pub_dates.tsv`. [Open them on their own page](assets/literary_years.html).

## Reviewing conflicts

The eight `conflict` rows are worth a look after any rerun. Most are a later
edition or translation on the Wikidata side: *The Prince* (1513 written,
1532 printed), *The Trial* (1914 written, 1925 published), *The Republic*
(Wikidata gave a 1963 translation), three Lovecraft stories dated by magazine
versus book publication. To settle one, add it to the overrides file with a
note; an override always wins.

## Regenerating

The script queries Wikidata at one request every three seconds and honors
`Retry-After`, so a full run is slow. A JSON cache of every response makes
reruns fast.

```bash
# The whole corpus, or name entries after the cache path
python3 -I scripts/lookup_pub_dates.py /tmp/pub_dates_review.tsv /tmp/pub_dates_cache.json
python3 -I scripts/lookup_pub_dates.py /tmp/pub_dates_review.tsv /tmp/pub_dates_cache.json \
    "american-literature/Adventures of Huckleberry Finn"
```

The script writes a wider review TSV (author dates, Wikidata route and rejected
matches) and changes nothing under `corpus/`. Read the `conflict`, `approx`,
`clamped-*` and `error` rows, then copy the `entry` through `wd_work` columns
into `corpus/pub_dates.tsv` below its two comment lines. Then redraw the
charts on this page:

```bash
poetry run python scripts/plot_pub_dates.py   # -> docs/assets/literary_years.html
```

A book added to the corpus has no year until this is rerun for it. The web
catalog export leaves `year` out for an undated book, so the forest still
shows it.

## Where the year goes

`gutenkg export-web-catalog` reads `corpus/pub_dates.tsv` and writes each
book's `year` into the Knowledge Press catalog. A corpus without the table
exports as before, with no years. See [Knowledge Press apps](KNOWLEDGE_PRESS.md).
