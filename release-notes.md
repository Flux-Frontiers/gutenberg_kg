# Release Notes -- v1.24.0

> Released: 2026-09-26

### Added

- **Hero trees grow as species.** Each genre maps to one of nine tree
  species (`GENRE_SPECIES`: oak, chestnut, fir, plane, blackthorn, pine,
  birch, willow, poplar — the same mapping as the Knowledge Press web forest),
  and the species' growth habit from `kgmodule-utils` 0.25.0
  (`kg_utils.viz3d.species`) shapes the tree: `ForestLayout` places sections
  and diary limbs inside the species' crown envelope (`crown_sections`,
  `section_cluster`), and `grow_tree_geometry` grows the wood with the
  species' tropism, reach, step, jitter, taper, leader and droop. Each book
  nudges its species a few percent (`book_habit`), so a grove is not a row of
  clones. The book still sets the height, the sections and one crown point
  per chunk; droop carries each chunk with its twig, so every leaf stays on
  the wood. `ForestLayout.book_habits` records the habit each crown was
  placed with, and the tree's title names its species.

- **Textured bark and species leaves on the hero tree** (sweep item 64).
  `build_tree_scene` draws the wood with `kg_utils.viz3d.bark_mesh` -- one
  continuous sweep whose texture coordinates wrap each limb in whole tiles --
  wearing the species' bark (CC0 ambientCG colour maps, the web forest's own,
  shipped in `gutenberg_kg/assets/bark/` with their credits), tiled to the
  image's aspect and to the web's bark scale (`BARK_TILE`). Leaves take the
  species' outline (new `gutenberg_kg.leafshapes`: lobed oak, palmate plane,
  fir and pine needle sprays, ovate leaves of five widths, ported from the
  web's `species.ts`), placed by `species_leaf_glyphs` on the same frames
  `leaf_glyphs` uses and scaled to the ellipsoid leaf's area so the canopy
  keeps its density. `species_look=False`, or `gutenkg quilt --plain`, keeps
  the plain tree. Checked through `render_quilt`: all 48 views of a 16"
  landscape quilt carry the textured wood.

### Changed

- **`kgmodule-utils` 0.25.1**: its blackthorn and fir presets no longer
  grow wandering limbs (the blackthorn's coiled into helices; the fir grew a
  branch back down to its lowest whorl), so those genres' hero trees
  (horror, german-literature; science-fiction, natural-history) come out
  clean. Floor, lock, Dockerfile ARG and runpod requirement moved together
  (`check_pins.py --bump`).
- **`GENRE_TROPISM` now follows the species table**: each genre's upward pull
  is its species' tropism. Trees grow with the whole habit; the table stays
  for callers that only want the tropism.
- **Requires `kgmodule-utils` >= 0.25.1** for the species engine.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
