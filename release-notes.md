# Release Notes — v1.14.0

> Released: 2026-08-11

Seven commits since v1.13.0. The theme is structure made visible: each book now
grows into a tree whose limbs are its own sections and chunks, and a tree can be
rendered as a light field and cast to a Looking Glass display. Drawing the
corpus that way immediately exposed two books whose structure had collapsed at
conversion time, which is fixed here as well.

## What changed

**A book grows into a tree, and the growth carries data.** The chunks of a book
become attraction points, and the branch skeleton is produced by space
colonization (Runions, Lane & Prusinkiewicz 2007), so every limb is a real path
document → section → chunk cluster. Branch radii follow the pipe model, so a
limb carrying half the text is visibly thicker. Two books of different structure
grow different silhouettes, and a given book grows the same tree every time —
the seed comes from its slug, since Python's builtin `hash()` is salted per
process and cannot reproduce geometry between runs.

Two departures from the published algorithm were needed, both because a book's
crown is clumpy where a plant's attractor cloud is not. Textbook colonization
stops when no attractor is within the influence radius, which strands the rest
of the canopy as a stump under a cloud of unattached leaves; growth now bridges
a limb across the gap instead. And an attractor can stay in range for the whole
run yet never win a node, because the averaged pull always goes to the crowd —
a book's one-chunk front-matter sections are exactly that case — so each
survivor is given its own twig. Every chunk hangs on wood.

**`gutenkg quilt` renders a book to a Looking Glass panel.** Stills, or
`--orbit` turntable video, with `--cast` handing the result to Bridge; the
rendering itself is done by [quiltwright](https://github.com/suchanek/quiltwright).
The stereo depth budget is printed before every render rather than after, so an
over-wide disparity costs nothing to discover. Hamlet is 420 chunks on 305
limbs, and its 8x6 quilt for the 16" Gen3 Landscape takes about two seconds on
an M5 Max. No panel is required to use any of this — a quilt is an ordinary PNG,
and the trees render in the viewer without display hardware.

**Scene construction left the Qt viewer.** Corpus scanning, layout, geometry,
and both scene builders now live in `gutenberg_kg.scene` and compose into a
plain `pv.Plotter` with no PyQt import. `viz3d.py` is one caller of that module
and the off-screen renderer is another; without the split, light-field
rendering would have needed a live `QApplication`. It also means the scene code
is testable headless, and 77 tests now cover it.

**Two sacred texts had lost their structure at conversion.** None of the
Quran's 114 sura headings matched a pattern, because Rodwell prints a footnote
digit against the word and an edition-order marker in brackets — all 2,586 body
chunks hung under a section named `PREFACE`. The Analects failed differently:
its headings were recognised but discarded, because Legge's bilingual edition
prints the Chinese heading directly above the English one and headings were
only honoured after a blank line. The Quran now carries 120 sections instead of
7, the Analects 28 instead of 8, and Sura II "The Cow" is correctly the
heaviest limb in the tree at 183 chunks. Heading counts are unchanged on
Frankenstein, Moby Dick, Pride and Prejudice, Alice, Hamlet, and Tao Te Ching,
so the relaxed gate does not invent structure elsewhere.

**Four seasons.** Foliage colour is sampled per leaf, so a canopy varies the
way a real one does rather than reading as one flat green. Winter drops ninety
percent of the leaves, which is the point — bare wood is where the pipe model
shows.

## Upgrading

The tree and quilt features need the `viz3d` extra:
`poetry install --extras viz3d`. Casting additionally needs Looking Glass
Bridge running locally. `quiltwright` is marker-gated to Python < 3.13 for now,
because it pins `requires-python <3.13` while this project supports `<3.14`;
without the marker Poetry rejects the whole resolution.

The corrected Quran and Analects Markdown is committed, so no re-download is
needed — but their indices must be rebuilt, and `gutenkg ingest` will skip a
book whose index looks current even when its source text has changed. Use
`--force-build`:

```bash
gutenkg ingest --genre sacred-texts --force-build
```

The corpus is baked into the Docker image, so `make build` is required before
the reading room reflects the corrected texts. Corpus totals move accordingly:
1,270,668 nodes and 5,095,045 edges across 241 books.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
