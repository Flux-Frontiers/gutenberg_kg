# Selective bundles

A bundle spec is a small TOML file that turns "ship these two books to a
phone" or "give me a standalone Shakespeare demo" into one command, instead
of hand-editing Makefile paths or remembering which flags to pass in which
order. This page is the operator's guide; the design rationale, the full
resolution rules, and every decision behind them live in
[`analysis/SELECTIVE_BUNDLE_EXPORT_PLAN.md`](../analysis/SELECTIVE_BUNDLE_EXPORT_PLAN.md).

Two committed examples to start from:
[`bundles/specs/philosophy-starter.toml`](../bundles/specs/philosophy-starter.toml)
and
[`bundles/specs/shakespeare-demo.toml`](../bundles/specs/shakespeare-demo.toml).

## Writing a spec

```toml
name = "philosophy-starter"
version = "0.1.0"
description = "Plato, Aristotle, and Kant -- small on-device demo"

genres = ["philosophy"]
# books = ["philosophy/The Republic", "2680", "Pride and Prejudice"]

diaries = false

materialize = "rebuild"
source_bundle = "bundles/gutenberg-all"

golden_queries = [
  "the categorical imperative and moral duty",
  "What does Plato say about justice?",
  "the allegory of the cave",
]

image_tag = "philosophy-starter-0.1.0"
```

- **`genres`** and **`books`** union together; either or both may be given.
  A `books` entry is resolved three ways, tried in order: an explicit
  `"<genre>/<book>"` catalog key, an all-digit Gutenberg ebook_id (scanned
  across every genre's `reference.md`), or a bare directory name unique
  across the whole corpus. No fuzzy title matching — a misspelled or
  ambiguous selector fails the command rather than silently picking the
  wrong book.
- **`diaries`** is `false` (none, the default), `true` (every diary in
  `corpus/diaries/`), or a list of diary slugs (see
  `export_swift._diary_slug` for the exact name each diary resolves to —
  `"pepys-complete"`, `"evelyn-volume-1"`, and so on, not the directory's
  full title).
- **`golden_queries`** needs at least three entries. This is not a
  suggestion: `bundle validate` refuses a spec without them. A bundle
  ships with no evidence it retrieves anything sensible unless something
  records what it should retrieve, and this is that something — see
  [The golden-query requirement](#the-golden-query-requirement) below.
- **`image_tag`** is the tag *suffix* only, defaulting to
  `"{name}-{version}"`. The repository name (`corpus-gutenberg`) is fixed
  in the Makefile and cannot be set from a spec — see
  [Tag policy](#tag-policy).

## Filter-at-export vs. rebuild

The one decision every spec makes: `materialize = "none"` or
`"rebuild"` (the default).

| | `materialize = "none"` | `materialize = "rebuild"` (default) |
|---|---|---|
| What it does | Filters an existing bundle's packs at export time | Walks `corpus/` fresh with only the selected books |
| Needs | `source_bundle` (normally `bundles/gutenberg-all`) already built | Nothing but the corpus itself |
| Produces | Swift packs only, in `bundles/<name>/swift/` | A standalone `bundles/<name>/.dockg/`, then Swift packs from that |
| Speed | Seconds — no new index | Seconds to minutes, proportional to the selection (see [Measured sizes and times](#measured-sizes-and-times)) |
| `bundle image` / `--image` | **Refused.** Swift-only has no worker-servable DocKG root | Works — bakes `bundles/<name>/.dockg/` into a tagged image |
| `product.json` | Not written (no rebuild happened) | Written at `bundles/<name>/product.json` |

Use `"none"` for a quick phone demo of books already in `gutenberg-all` — no
rebuild, no image, packs in seconds. Use `"rebuild"` (the default) when the
bundle needs to stand on its own: its own DocKG, its own container image,
its own `product.json` audit record independent of whatever `gutenberg-all`
happens to contain at the time.

## Running it

```sh
# Check a spec resolves before spending any time on it.
gutenkg bundle validate bundles/specs/philosophy-starter.toml
gutenkg bundle resolve  bundles/specs/philosophy-starter.toml

# The individual steps, if you want to run them separately.
gutenkg bundle build  bundles/specs/philosophy-starter.toml   # no-op for materialize = "none"
gutenkg bundle export bundles/specs/philosophy-starter.toml --verify
gutenkg bundle image  bundles/specs/philosophy-starter.toml   # refused for materialize = "none"

# Or the whole pipeline in one command: validate -> build -> export -> image.
gutenkg bundle make bundles/specs/philosophy-starter.toml --verify --image
```

The same thing through `make`, which is what CI and a from-scratch clone
should actually run — `SPEC=` is resolved inside each recipe via
`gutenkg bundle resolve`, never at parse time, so a bare `make help` never
shells out to it:

```sh
make build-corpus SPEC=bundles/specs/philosophy-starter.toml
make export-swift SPEC=bundles/specs/philosophy-starter.toml
make build        SPEC=bundles/specs/philosophy-starter.toml
```

`export-swift --book`/`--genre` and `build-corpus --book`/`--spec` also work
without a spec file at all, for a one-off selection: see
[`gutenkg export-swift --help`](CHEATSHEET.md#on-device-corpus-packs) and
`gutenkg build-corpus --help`. A spec is the product path — write one when
the selection is worth naming, versioning, and repeating.

## Tag policy

`IMAGE = corpus-gutenberg` is fixed in the Makefile; only the tag varies,
and only one place decides it:

| Command | Tag |
|---|---|
| `make build` (no `SPEC=`/`BUNDLE=`) | `corpus-gutenberg:latest` — the full corpus |
| `make build BUNDLE=<name>` | `corpus-gutenberg:<name>` — unversioned, local convenience only |
| `make build SPEC=<spec>` | `corpus-gutenberg:<name>-<version>` — canonical, from the spec's own `image_tag` |
| `gutenkg bundle image <spec>` / `bundle make <spec> --image` | Same canonical tag, built directly |

`corpus-gutenberg:latest` always means `gutenberg-all`. Nothing in this
workflow ever retags it — a product build gets its own tag, never `:latest`.

## The golden-query requirement

`bundle validate` rejects a spec with fewer than three `golden_queries`.
The reason is what `export --verify` and `bundle make --verify` actually
measure: recall@10 of the pack's int8 vectors against exact fp32 ground
truth, using the queries a spec supplies. With no queries, `--verify` has
nothing to check, and a bundle can ship with quantization that has quietly
degraded and nothing would ever say so.

Write real queries against the books actually selected — a query that
never matches anything in the bundle passes vacuously and tells you
nothing. `shakespeare-demo.toml`'s three queries were checked against the
real corpus while writing this doc; one ("double, double, toil and
trouble," which is *in* `Macbeth` three times) still lost to an unrelated
`A Midsummer Night's Dream` chunk on the fused dense+lexical ranking for a
4-book pack, and was swapped for a query that reliably ranks the intended
play first. Write the spec, run `gutenkg bundle export --verify`, and read
`golden.json` — don't assume a query is discriminating just because the
line is famous.

## Rollback

There is no `gutenkg bundle rollback` command — the audit trail is what
makes one unnecessary. `bundle build` (for `materialize = "rebuild"`)
writes `bundles/<name>/product.json`:

```json
{
  "name": "philosophy-starter",
  "version": "0.1.0",
  "spec_sha256": "...",
  "materialize": "rebuild",
  "catalog_keys": ["philosophy/The Republic", "..."],
  "book_count": 39,
  "diary_dirs": [],
  "created": "2026-09-07T19:11:31+00:00",
  "dockg_sha256": {"graph.sqlite": "...", "vectors.sqlite": "...", "catalog.json": "..."}
}
```

That is a frozen record of exactly what selection and what corpus state
produced this bundle — not something the worker or the Swift reader ever
reads, purely for a human asking "what shipped, and can I get it back."
Since the spec file is committed and `catalog_keys` is a pure function of
the spec plus the corpus, reproducing a prior bundle is `git checkout` to
the commit the spec (and, if it changed, the corpus) were at, then
`gutenkg bundle build` again — the `dockg_sha256` block is how you confirm
the result actually matches.

## Measured sizes and times

Real numbers, not estimates — from `analysis/SELECTIVE_BUNDLE_EXPORT_PLAN.md`
and this doc's own writing, on Turing (Apple Silicon, MPS embedding).

| Selection | Books | Nodes | DocKG build | DocKG size | Swift export |
|---|---:|---:|---:|---:|---:|
| `gutenberg-all` (full corpus) | 253 | 731,824 | ~22m | multi-GB | ~860 MB (all packs) |
| `philosophy-starter` (`genres = ["philosophy"]`) | 39 | 144,046 | 2m 38s | 725.4 MB | — |
| single book (ad-hoc `--book`, this doc's own test) | 1 | 8,367 | 9s | 35.3 MB | 4.46 MB |
| `shakespeare-demo` (4 books, `materialize = "none"`) | 4 | — (filtered from `gutenberg-all`) | n/a | n/a | 2.06 MB |

A container image follows the same pattern: `corpus-gutenberg:latest` (full
corpus) is 10.9 GB. A single-book image built the same way, from source with
the base layers cached, finished in under two minutes at 3.34 GB. The delta
between the two is almost entirely the baked-in bundle — the
Python/torch/KG-package layers are identical and shared.

These numbers are also the answer to "why not slice `gutenberg-all` instead
of rebuilding": a rebuild proportional to the subset is already fast enough
that a slicing mode would have bought only a few minutes at most, at the
cost of a second materialization path that never quite matched a real
rebuild. See
[Deferred: DocKG slice](../analysis/SELECTIVE_BUNDLE_EXPORT_PLAN.md#deferred-dockg-slice)
for the full accounting.
