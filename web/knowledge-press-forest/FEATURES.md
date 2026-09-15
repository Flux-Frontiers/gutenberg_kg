# Features

Backlog for the web forest. Shipped items stay here so the PyVista mapping
doesn’t get lost. New work goes on `web/forest-wayfinding` until it is ready
for `main`.

## Next

### Sky, stars, and weather
A real sky dome — not a flat fog color.

- **Sky** with a proper gradient (zenith → horizon), sun disk, and season-tinted
  twilight so Summer and Winter don’t share the same lid.
- **Stars** as a real field (magnitude, color temperature, slow sidereal drift),
  visible at dusk/night and in winter, not a texture sticker.
- **Weather** as a first-class layer: clear, high haze, rain, snow (winter
  already drops the canopy — snow should actually fall), and wind that moves
  the leaves. Tied to season, overridable from the HUD like Spring/Summer.

This is the next world pass. The groves read as a model until the sky does.

## Later

| Feature | Notes |
| --- | --- |
| Jump to a tree, not only a grove | From the press list and from query hits. Land at the trunk, facing the plaque. |
| Day / night clock | Drives the sky. Night makes stars and the lantern the point. |
| Ambient audio | Wind, wet leaves, a distant press. Unlock on first gesture. |
| Breadcrumb lanterns | Optional trail of your own lights so a long wander still has a way home. |
| Live corpus ingest | `python scripts/export_web_catalog.py` counts `kind='chunk'` nodes in each book's `graph.sqlite` and rewrites the TypeScript catalog. The web forest does not re-chunk. |

## Shipped

| Feature | Where |
| --- | --- |
| Space-colonization trees, pipe-model radii, genre tropism | `growTree.ts` |
| Fibonacci annulus groves, 253-book catalog | `forest.ts`, `catalog.ts` |
| WASD lantern cart, chase cam (A = left from behind) | `Player.tsx`, `sim.ts` |
| Seasons (canopy density, palettes) | `seasons.ts` |
| Lantern query over titles, tags, excerpts | `HUD.tsx`, `Trees.tsx` |
| Grove atlas, minimap jump, Hamlet return | `HUD.tsx` |
| Carriage roads (spokes + ring) | `forest.ts`, `World.tsx` |
| Ride-the-ring tour (steer to hop off) | `Player.tsx` |
| Named grove signposts | `Signposts.tsx` |
| Denser skeletons (raised attractor / node caps) | `growTree.ts` |
| Press / local library | `store.ts` |
