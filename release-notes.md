# Release Notes -- v1.25.0

> Released: 2026-09-26

### Added

- Species bark in `gutenkg pov`. The POV-Ray wood was untextured because a
  `sphere_sweep` has no texture coordinates. It is now a `mesh2` built from
  `kg_utils.viz3d.bark_sweep` and textured with the species' bark
  photograph through quiltwright's `ImageTexture`. The season tints the bark
  as in the web forest (`bark_tint`), relief comes from the photograph's
  brightness, and `PovScene.write` copies the photograph next to the `.pov`.
  The scene declares `#version 3.7`, without which POV-Ray uses its pre-3.7
  lighting and the photograph washes out. `--plain`, or `species_look=False`
  on `tree_pov_scene` and `build_tree_pov_scene`, keeps the analytic sweeps.
  On Hamlet's tree the mesh traces in 0.9 s against 72 s for the sweeps and
  has no seams at the forks.
- Species leaf placement matching the web forest, in both renderers.
  `species_leaf_frames` (in `treegeom`, NumPy only) places each leaf with
  kgmodule-utils' `hang_leaves`: the stalk on the nearest twig, the blade
  pointing out and up, the face toward the sky, sized as the web's
  `emitLeaves` sizes it. `gutenkg pov` draws each leaf as an instanced
  `polygon` of the species' outline, and `species_leaf_glyphs` (the `gutenkg
  quilt` path) uses the same outline and frame. Both previously used
  `leaf_frames`, which set leaves off the wood with a random roll, so many
  showed edge-on. The plain look still uses `leaf_frames` and ellipsoids.
  `species_leaf_glyphs` drops its `cling` and `seed` arguments and adds
  `n_tints`.

### Changed

- `kgmodule-utils` floored at 0.26.0 and `quiltwright` at 0.16.0, for
  `hang_leaves`, `ImageTexture`, `Mesh2(uv=...)` and `PovScene(version=...)`.
  The floor, lock, Dockerfile ARG and runpod requirement moved together, and
  both `quiltwright` entries (`viz3d`, `pov`) resolve to one locked version.

---

_Full changelog: [CHANGELOG.md](CHANGELOG.md)_
