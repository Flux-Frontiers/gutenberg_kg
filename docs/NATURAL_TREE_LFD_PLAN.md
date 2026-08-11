# Natural trees for the light-field display — viz3d → quiltwright design plan

**Eric G. Suchanek, PhD** · 11 August 2026

Scope: how this repository's viz3d forest becomes (1) botanically credible trees and (2) a
renderable light-field object, and how that connects to the KGRAG **Tree of Knowledge(tm)**
concept in `kgrag_priv/docs/TREE_VISUALIZER_PLAN.md`. This is the canonical copy; the stub in
`kgrag_priv/docs/` points here. Written 11 August 2026 against `viz3d.py` at v1.9.0.

---

## 1. What exists today, precisely

**`gutenberg_kg/src/gutenberg_kg/viz3d.py` (1,529 lines) is a working forest.** Each book is a
tree: document node at the base, a brown `pv.Cylinder` trunk with height ∝ log₂(1 + chunks)
capped at 45 units, section nodes spiralling up the trunk at the golden angle with straight
branch lines to the trunk axis, chunk nodes in Fibonacci-hemisphere clusters above each section
tip, entities/topics as a floating cloud above the canopy. Books sit in Fibonacci annuli around
genre centres; genres sit in a larger annulus; 10-colour genre palette on the trunks; three-tier
LOD (icosahedra → octahedra → tetrahedra) with glyph batching; night-sky gradient background and
a 1000×1000 ground plane. Picking, text popups, per-genre/book filtering, HTML and screenshot
export — all inside a PyQt5 `QtInteractor` window.

**What makes it read as schematic rather than natural** — the gap between this and "a tree":

1. **The trunk is a straight cylinder** of constant radius. Real trunks taper, lean, and curve.
2. **Branches are straight line segments** from trunk axis to section tip — spokes, not limbs.
   There is no second-order branching anywhere: trunk → branch → done.
3. **No radius hierarchy.** Branch lines have zero thickness; nothing conveys that a limb
   carrying forty chunks is heavier than one carrying three.
4. **Leaves are Fibonacci spheres** — mathematically elegant, visually a lollipop. Real canopies
   are irregular, directional (light-seeking), and denser at the crown periphery.
5. **Perfect radial symmetry from the golden-angle spiral.** Nothing in nature is that tidy;
   the eye reads the regularity instantly at parallax, which matters on an LFD far more than on
   a flat screen — depth exposes structure that a projection hides.

**KGRAG's `kgrag_priv/docs/TREE_VISUALIZER_PLAN.md` is the other half**, still
unimplemented: stochastic L-system trees whose *parameters* encode graph statistics (height from
node count, bushiness from edge density, species from KGKind — conifer for code, oak for
diaries, willow for verse), groves, query illumination, snapshot-replay growth. Its subject is
different: one tree per *registered KG*, parameterised from `_graph_stats()` — aggregate
statistics, because at KG granularity there is no per-leaf data to place.

**The bridge already exists and is quiltwright's whole design.** `render_quilt(plotter, spec)`
takes any off-screen `pv.Plotter` with the scene composed and the camera framing the subject —
the focal point becomes the display's physical focal plane. viz3d already builds its scene into
a plotter; what stands between here and a quilt is only that the scene-building is entangled
with Qt (see §4).

---

## 2. The design decision: grow the skeleton to reach the data

Two families of algorithm produce natural-looking trees, and the choice between them is not
aesthetic — it is about what the geometry *means*.

**L-systems** (the TREE_VISUALIZER_PLAN approach) generate a skeleton from recursive rules plus
randomness. They look organic, but the shape is *decorative*: a seeded random process whose
parameters summarise the data. Right for the KGRAG per-KG tree, where aggregate stats are all
there is. Wrong for a book, where we have the actual 3-D position of every section and chunk —
an L-system would throw that information away and grow a pretty shape unrelated to it.

**Space colonization** (Runions, Lane & Prusinkiewicz 2007 — the standard algorithm for
believable tree skeletons in graphics) inverts this. You scatter *attraction points* defining
the crown volume; the skeleton grows iteratively from the trunk base toward them, each growing
tip pulled by the attractors nearest it, attractors consumed as branches arrive. The result is
irregular, load-bearing, natural branching — because that is literally how the algorithm works:
the tree exists to reach its attractors.

**For a book-tree the attractors are not decoration — they are the chunks.** Place the chunk
nodes first (as the crown), then grow the skeleton to reach them:

- Every branch is then a *true structural path* document → section → chunk-cluster. Click
  anywhere on a limb and there is a real answer to "what does this branch carry?"
- Canopy shape becomes semantic. A book with three fat sections grows three heavy limbs; a
  book of eighty short chapters grows a fine-twigged dome; an unstructured text (chunks
  attached directly to the document — a case viz3d already handles) grows a dense unbranched
  crown like a cypress. **The botany is the data.** Two books look different because they *are*
  different, which is exactly the claim the exhibition and the book manuscript need the image
  to make.
- The irregularity the eye demands falls out for free — no jitter parameter faking it.

**Crown placement (where the attractors go).** Two options, in order of ambition:

- *v1 — structural crown:* keep viz3d's current placement logic (sections at golden-angle
  stations, chunks in hemispheres above them) but use those positions as attractors instead of
  final geometry, with per-tree random rotation and modest positional noise. Cheap, and already
  a transformation: the skeleton beneath becomes organic even though the crown is regular.
- *v2 — semantic crown:* place chunks by embedding. GutenbergKG chunks already carry
  embeddings in the sqlite-vec store (`vectors.sqlite`, built by `build_corpus.py` — the
  corpus migrated off LanceDB); UMAP/PCA to 3-D, scaled into an ellipsoidal crown volume per
  book. Then
  *thematically similar chunks hang on the same limb* — the tree's structure becomes a map of
  the book's meaning, not just its table of contents. This is the version the wall text writes
  itself for, and it is also genuinely novel — I know of no prior semantic-embedding space-
  colonization tree of a text corpus. (Verify that claim before printing it anywhere; it is
  exactly the kind of superlative the claims register exists for.)

**Species stay in the picture** — the TREE_VISUALIZER_PLAN's species table maps onto genre
here: crown-volume shape (prolate for philosophy's deep hierarchies, weeping for poetry, broad
for novels), attraction/kill radii, tropism vector (gravity droop for willow-genres, upward
bias for conifer-genres). Genre already has a colour; giving it a *silhouette* doubles the
information carried at forest distance, where colour is the only cue today.

---

## 3. Geometry: from skeleton to mesh

The space-colonization output is a node/parent skeleton. Making it look like wood:

1. **Radii by the pipe model** (da Vinci's rule): leaf-bearing tips get radius r₀; at every
   junction the parent's cross-section is the sum of the children's — rₚ = (Σ rᵢⁿ)^(1/n) with
   n ≈ 2–2.5. One postorder pass. This is what makes a trunk *inevitable* rather than drawn:
   thickness states exactly how much knowledge each limb carries, so even the trunk's final
   radius is data (total chunk count).
2. **Smooth the polylines** (Catmull-Rom through each root-to-tip path) and sweep tubes:
   `pv.Spline(path).tube(scalars="radius", absolute=True)` gives per-point radius variation;
   merge all limbs per tree, one mesh, one actor — same batching discipline viz3d already
   applies to trunks and branch lines.
3. **Leaves as oriented glyphs, not spheres.** Keep the glyph-batching approach but swap the
   icosahedron prototype for a flattened ellipsoid or two crossed quads, oriented by the local
   branch direction with jitter. At LFD viewing distance individual leaf geometry is
   subordinate to *cluster* shape; the win is irregular silhouette, not leaf detail.
4. **Bark is out of scope.** On a Portrait/16″ panel a texture that fine costs render time and
   buys nothing at the depth budget's working distance. Colour + radius + silhouette carry it.
5. **Keep the gold entity-spores.** Floating points of light above a natural canopy read as
   fireflies and are the best depth cue in the whole scene — small bright off-plane points are
   what light-field displays love. (They are also the query-illumination hook when the KGRAG
   federated-query lighting from TREE_VISUALIZER_PLAN §Query Highlighting arrives.)

Everything above is deterministic given a seed — seed from the book slug, exactly as the
TREE_VISUALIZER_PLAN already prescribes for reproducibility (`hash(entry.id)`), so a tree is
identical between sessions, renders, and the printed figure in a book chapter.

---

## 4. The path to the panel — refactor, don't rewrite

**The blocker is architectural, not algorithmic:** `create_forest_visualization(viz, nodes,
edges, plotter)` takes the Qt-bound `GutenbergForestVisualizer` and calls
`QApplication.processEvents()` mid-build. quiltwright needs the same scene in an off-screen
plotter with no Qt anywhere.

1. **Extract a pure scene builder.** `scene.py`: `build_forest_scene(nodes, edges, plotter, *,
   layout, lod, filters) -> SceneInfo` — no `viz`, no Qt, no `processEvents`; progress via a
   plain callback. The Qt window becomes one caller of it; the quilt path becomes another. This
   is the same factoring quiltwright itself uses (shared assembler, two backends), and it is
   the single highest-value change in this plan — everything else composes with it.
2. **A CLI that ends at the display.**
   `gutenberg-kg quilt --book "porin" --spec portrait --out renders/` →
   off-screen `pv.Plotter(off_screen=True)` → `build_forest_scene` → frame the hero tree →
   `render_quilt(plotter, QUILT_PRESETS["portrait"])` → `save_quilt` (the `_qs8x6a0.75` name
   Bridge parses) → optionally `cast_quilt`. A `--orbit` flag wraps `render_quilt_video` for a
   turntable quilt video — the demo-loop format a museum panel actually plays all day.
3. **Print the depth budget before rendering, always.** quiltwright's
   `format_depth_budget` — the discipline is already house style; the CLI should refuse
   nothing but *say* the disparity numbers every run.

**Layout code lands in gutenberg_kg** (`layout_organic.py`: `colonize()`, `pipe_radii()`,
`smooth_paths()`), beside `ForestLayout` — not replacing it. The schematic layout remains the
right choice for the interactive Qt explorer at full-corpus scale; the organic layout is for
hero trees, groves, and everything that faces a lens. `pycode_kg.layout3d` keeps supplying
`fibonacci_annulus`/`fibonacci_sphere` for crown seeding. quiltwright is untouched — the whole
point of its architecture is that a new scene source costs it nothing.

---

## 5. Depth budget: what can actually fuse

The corpus is 249 books / 1.3 M nodes. The full forest **will not fuse** on a light-field panel
naively — a dense point field at 300+ scene-units of spread is precisely the
`quiltwright/docs/pov-workflow.md` §7 failure case, and the museum scene already measured ~43 px adjacent-view
disparity against an ~8 px ghosting threshold on a far shallower composition. Plan the LFD
content as three tiers, in order:

| Tier | Subject | Composition | Risk |
|---|---|---|---|
| **1 — Hero tree** | One book | Single tree fills the frame, focal plane at mid-trunk, crown depth tuned to the budget; fireflies slightly off-plane | Low — this fuses, and it is the demo, the work sample, and the book figure |
| **2 — Grove** | One genre (10–25 trees) | Hero tree near focal plane, grove receding; fog + desaturation past the mid-ground doing the depth compression | Medium — needs the budget arithmetic run per composition |
| **3 — Forest / Tree of Knowledge** | Everything | *Not* 1.3 M nodes: impostors (one merged low-LOD mesh per distant tree), ground fog swallowing the far annuli, orbit video rather than static quilt | High as a still; tractable as a turntable video where motion parallax assists |

Practical composition rules, all from existing quiltwright doctrine: the 1000×1000 ground plane
must shrink or fade to fog (an effectively infinite plane guarantees off-budget disparity at
the horizon); the night-forest palette is already ideal (dark field, high contrast is the HLD
styling rule, and it flatters LFD too); scale one tree to ~2/3 frame height with the crown's
depth extent inside the fuse zone the budget prints.

**Tier 1 is the deliverable that matters.** One book, grown by space colonization to reach its
own chunks, standing in real depth on a panel — that is the image for the Sloan Books LOI
(`kgrag_priv/grants/sloan_books_track.md` §4), the museum demo's humanities piece, and the Looking Glass
case study, in one render.

---

## 6. The Tree of Knowledge, and the 1995 window

Two layers of the concept, now cleanly separated:

- **GutenbergKG forest** (this plan): trees *of one corpus*, one per book, leaves = real data.
- **KGRAG Tree of Knowledge** (TREE_VISUALIZER_PLAN): one tree per *registered KG* — the code
  graph, the diaries, the molecules, the literature — species by KGKind, the whole compiled
  practice as a forest. The organic machinery built here (colonization, pipe radii, tube
  sweep, species parameters) is exactly the renderer its Phase 1–2 lacked; its attractors come
  from `_graph_stats()`-derived synthetic crowns rather than per-chunk positions. Build it
  second, on the same `layout_organic.py`, into the same headless scene builder → quilt path.

And the iconographic close of the loop, already recorded in `kgrag_priv/grants/backstory.md`: the 1995
museum room has a tree through the arched window that reads — unplanned — as the Tree of
Knowledge. Thirty-one years later the same hands render an actual Tree of Knowledge, grown
from everything they know, onto a display where you can walk around it. The exhibition hangs
the 1995 room (as hologram) beside the 2026 tree (as light field); the book closes Part II
with it. No other single image joins the two halves of the work — molecules and meaning — this
literally.

---

## 7. Order of work

1. `build_forest_scene` extraction (§4.1) — unblocks everything, changes no behaviour.
2. `gutenberg-kg quilt` CLI against the *existing* schematic layout — proves the pipeline end
   to end in a day; the first quilt of the current forest is worth having regardless.
3. `layout_organic.py`: colonization + pipe radii + tube sweep, v1 structural crown (§2).
   Hero-tree render, depth budget in hand. **← the Tier-1 deliverable**
4. Species/genre silhouette parameters; grove composition (Tier 2).
5. v2 semantic crown from embeddings.
6. KGRAG Tree of Knowledge on the same machinery.
7. Forest-scale impostors and the orbit video (Tier 3), when a venue wants the wide shot.

Steps 1–3 are the critical path to a panel-ready object; everything after is refinement with
its own audience.

---

## Open questions

1. **Attractor counts at scale.** Space colonization is O(tips × attractors) per iteration;
   a 5,000-chunk book wants spatial hashing or attractor subsampling (grow to section-level
   attractors, then decorate chunks onto the nearest limb). Decide when the first big book is
   slow, not before.
2. **Where does genre live in v2?** If chunks place by embedding, thematically-similar books in
   different genres will grow similar crowns — is that a feature (the data speaking) or a loss
   (the genre palette's message diluted)? Likely feature; confirm by eye.
3. **Whether the sqlite-vec embeddings cover all 249 books** or only the indexed subset —
   determines whether v2 is corpus-wide or starts as a curated shelf.
4. **HLD output.** The same scene through `quiltwright.hld` styling rules (dark field, safe
   margins) gives the 2-D-video variant for Hololuminescent panels — nearly free, worth doing
   at step 2 so both display families are covered from the first render.
