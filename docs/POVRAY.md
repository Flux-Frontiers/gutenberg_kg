# Ray-tracing the knowledge tree

`gutenkg pov` writes a book's tree as a POV-Ray scene built from **analytic
primitives** — a limb is a `sphere_sweep`, a leaf is one instance of a single
declared ellipsoid — rather than as a triangle dump.

```
                       ┌──→ gutenkg quilt  →  PyVista/VTK   →  quilt  (raster)
  grow_tree_geometry ──┤
                       └──→ gutenkg pov    →  .pov  →  POV-Ray →  quilt  (ray-traced)
```

Both arms start at the same function. That is the point: the ray-traced tree is
the *same* tree as the rasterised one — same skeleton, same clung leaves, same
spore halo — not a second implementation kept in step by hand.

## Why not just dump the mesh

By the time geometry reaches a `pv.Plotter` it is already tessellated. A
`mesh2` dump keeps VTK's facets *and* costs a great deal of text, re-parsed
once per view — 48 times for a Portrait quilt. Emitting intent instead is
smaller by one to two orders of magnitude, and the silhouettes stay exact at
any zoom, which is most of the reason to leave VTK in the first place.

## Quick start

```bash
# Write a scene (needs no PyVista, no GL context)
gutenkg pov --book Hamlet

# Autumn foliage with the entity halo
gutenkg pov --book Hamlet --season autumn --entities

# Ray-trace it into a Looking Glass quilt (needs a povray binary)
gutenkg pov --book Hamlet --render --spec portrait
```

Install just what the scene-writing path needs:

```bash
pip install "gutenberg-kg[pov]"
```

That extra pulls the NumPy-only geometry and `quiltwright.povgen` — **not**
PyVista, Qt, or VTK. A headless render box needs nothing more to produce
`.pov` files; only `--render` wants a `povray` binary.

## What the scene contains

| Element | POV-Ray form | Why |
|---|---|---|
| Wood | one `sphere_sweep` per root-to-tip path | carries the pipe model's per-node radii; exact silhouette |
| Foliage | `object { GutenLeaf … }` per leaf | prototype declared once, so a canopy is a line per leaf |
| Spores | `sphere` per halo point | entity/topic annotation, off by default |
| Ground | `box` slab | **on by default**; catches the contact shadow |

### The ground, and why it is on here but not in `gutenkg quilt`

`build_tree_scene` omits its ground because it draws an effectively infinite
plane, which guarantees off-budget disparity at the horizon. This slab is
finite — `--ground` is a multiple of the crown's own width, default 3 — so it
carries no such cost, and it earns its place: a ray-traced tree with no contact
shadow reads as floating. The rasterised one does not have that problem
because VTK's headlight casts nothing at all.

Its top face sits at `z = 0`, where the trunk's root node is, so the tree
stands *on* it rather than hovering over a plane parked below.

Only the key light casts. A three-way casting rig gives one tree three
overlapping shadows, which reads as three trees.

Leaves are grouped into one `union` per foliage colour, so a season's palette
costs one texture per colour rather than one per leaf.

## Three things decided for you

**Handedness.** The scene is authored **right-handed with `+z` up**, as
everything else in this repo is, and `povgen` negates `z` on emission. The
ray-traced image therefore matches the PyVista render rather than mirroring
it. A mirrored sweep would invert the hologram's depth, which is not something
you want to discover on the panel. The camera is a separate matter — see
below.

**Lighting is a `+z`-up rig, written here.** `quiltwright.povgen` ships
`lights_from_bounds`; it now takes `up=(0, 0, 1)`, which fixes the half of this
that was a bug — its offsets used to assume `+y` up and put the key light
*below the ground* of a `+z`-up scene. `povscene.tree_lights` stays for the
other half: the upstream helper is a two-light rig and cannot know which side
of the subject the camera is on, so it cannot choose a front. This scene knows
— the quilt camera stands off along `-y` — and spends a third light on it. Key
from the upper front right, shadowless fill from the left, dim back light so
the crown separates from the sky.
`test_the_key_light_is_above_the_tree_not_below_it` is the guard.

**No camera is written.** `render_pov_quilt` appends one off-axis camera per
view and POV-Ray honours the *last* one it parses, so a camera in the scene
file would be silently overridden. `tree_pov_camera` carries the viewpoint
across instead, framing the way `gutenkg quilt` does: level view along `-y`,
up `+z`, focal plane at the centre of the scene's own bounds so the crown
straddles the display surface.

**`PovCamera` is in POV-Ray coordinates, not scene coordinates.** This trips
people, and it caught this module. Geometry is authored right-handed and
converted on emission, but a `PovCamera` holds coordinates that are *already*
converted — `pov_camera_from_plotter` runs `to_pov` over the plotter's
position, focal point and up vector, and `camera_block` emits whatever it is
handed, verbatim. Frame in the right-handed world if you like, but convert
before constructing the camera. Skip that and the tree sits at negative `z`
while the lens aims at positive `z`: POV-Ray renders a flawless picture of
empty sky. Nothing in the SDL looks wrong, and any assertion that compares
right-handed against right-handed passes.

## How this is verified

`TestDualRender` renders the same tree through both backends at a matched
camera and compares silhouettes against a black background — lighting models
differ, so pixels never will. Measured with the viewpoint carried across:

| Measure | Result |
|---|---|
| Silhouette IoU | **0.877** |
| Coverage | 1.90% raster vs 1.76% ray-traced |
| Bounding box | within 1–2 px on every edge |

IoU is deflated by what the subject is: a canopy is thousands of small
disconnected blades, so a pixel of misregistration costs far more than it
would on a solid object. The residual is per-leaf roll (documented as
differing from `vtkGlyph3D`) and an exact ellipsoid against an 8×6 tessellated
one. The bounding box is what actually pins the lens — a wrong FOV, a wrong
dolly or a mirrored axis all move those edges, and none survive 3 px.

A separate test renders through `tree_pov_camera` rather than a carried
camera, because the carried-camera tests isolate geometry and would happily
pass with the framing broken. That is the one that fails on an unconverted
camera.

The tests skip unless both a `povray` binary and a working off-screen GL stack
are present. On Debian/Ubuntu:

```bash
apt-get install -y povray xvfb libgl1-mesa-dri libglx-mesa0
xvfb-run -a pytest tests/test_povscene.py
```

## Dials

| Flag | Effect |
|---|---|
| `--subdivisions` | spline samples per skeleton segment. The one dial trading file size for limb smoothness; `4` matches the PyVista path |
| `--leaf-size` | leaf radius before density scaling. Leaves shrink by the cube root of chunk count, so a dense book renders fine — raise this to thicken its canopy |
| `--season` | foliage palette. Winter drops most leaves, baring the wood |
| `--fov` / `--zoom` | per-view vertical FOV and dolly, same meaning as `gutenkg quilt` |
| `--ground` | ground slab edge as a multiple of crown width; `0` omits it |
| `--brightness` | key-light multiplier, default 2.6 — see below |
| `--sky` | background colour override, `#rrggbb` |

### Why the default brightness is 2.6 and not 1

A canopy of thousands of small blades self-shadows heavily, and the wood is a
dark brown against a dark sky. At unit intensity the first Pepys render — 9,993
leaves — came out with the trunk unreadable: geometrically perfect, visually
black. Nothing in the test suite noticed, because the SDL was correct. Only
looking at the image did.

## Known limits

- **`limb_paths` is not bit-identical to `pv.Spline`.** It interpolates the
  same control points through a uniform Catmull-Rom, and upstream bounds the
  divergence at 2% of scene scale. When two backends must agree to the pixel,
  call `smooth_paths` once and hand both the same points.
- **Leaf glyph *roll* differs from VTK.** Position, aim and silhouette agree;
  the orthonormal completion is deterministic but is not `vtkGlyph3D`'s.
- **`sphere_sweep` ends are hemispherical, `tube` ends are flat.** A tapered
  limb extends slightly further past its thick end in POV-Ray.
- **Instanced leaves do not contribute to `PovScene.bounds()`** — an instance
  cannot be measured without resolving its prototype — so the wood and spores
  are what frame the shot and place the lights. In practice the wood reaches
  the crown anyway.

## The API

```python
from gutenberg_kg.bookgraph import load_book_graph, scan_corpus
from gutenberg_kg.povscene import build_tree_pov_scene, tree_pov_camera

meta = scan_corpus(Path("corpus"))["tragedy"][0]
nodes, edges = load_book_graph(meta)

scene, geometry = build_tree_pov_scene(nodes, edges, slug=meta.slug, genre=meta.genre)
scene.write("hamlet.pov")
camera = tree_pov_camera(scene, fov=14.0, zoom=1.2)
```

`build_tree_pov_scene` returns the geometry alongside the scene because framing
needs the crown, and regrowing the tree to get it would be both slow and a
chance for the two to disagree.

## Module layout

| Module | Needs PyVista | Holds |
|---|---|---|
| `gutenberg_kg.bookgraph` | no | corpus discovery, per-book graph loading |
| `gutenberg_kg.treegeom` | no | `ForestLayout`, seasons, `grow_tree_geometry` |
| `gutenberg_kg.povscene` | no | the analytic POV-Ray backend |
| `gutenberg_kg.scene` | **yes** | the PyVista backend, plus re-exports of the above |

`scene.py` re-exports every public name from `bookgraph` and `treegeom`, so
`from gutenberg_kg.scene import ForestLayout` keeps working. New code should
import from whichever module matches what it needs.
