# Knowledge Press Forest

Web port of the GutenbergKG forest: 253 public-domain books grown as trees
(space colonization + pipe model + genre tropism), laid out on a Fibonacci
annulus of genre groves. You drive a lantern cart through them.

This directory is additive — it does not replace the PyVista / Qt viewer.

See **[FEATURES.md](FEATURES.md)** for the backlog. Next: a real sky with
stars and weather.


## Run it

From this folder:

```bash
npm install
npm run dev
```

Open the URL Vite prints. Click **Start driving**.

| Key | Action |
| --- | --- |
| **W / S** | throttle / reverse |
| **A / D** | steer left / right (chase camera) |
| **E** | read the nearest tree into the press |
| **G** | grove atlas — jump to a genre |
| **Q** | ride the ring road (steer to hop off) |
| **H** | return to Hamlet |
| **L** | open the press (collected books) |
| **Esc** | pause |

Click a grove on the minimap to jump there. The cart is **not** locked to rails
unless you ride the ring. Dirt spokes run from the press to each grove so the
path is readable from the chase camera.

On a phone, use the on-screen stick. Type a word in the lantern field to
light matching groves (`stoic`, `freedom`, `fire`, `sea`) — the lantern trail
points at the nearest hit. Switch season to **Winter** to drop the canopy and
read the wood.

## Map to the PyVista stack

| gutenberg_kg | this package |
| --- | --- |
| `src/gutenberg_kg/treegeom.py` — space colonization, pipe model, tropism | [`src/game/growTree.ts`](src/game/growTree.ts) |
| `ForestLayout` — Fibonacci annulus, genre groves | [`src/game/forest.ts`](src/game/forest.ts) |
| seasons / foliage | [`src/game/seasons.ts`](src/game/seasons.ts) |
| book corpus | [`src/game/catalog.ts`](src/game/catalog.ts) |
| `viz3d.py` Qt/PyVista viewer | [`src/game/ForestCanvas.tsx`](src/game/ForestCanvas.tsx) + [`Player.tsx`](src/game/Player.tsx) |
| retrieval as a query over the forest | lantern query in [`HUD.tsx`](src/game/HUD.tsx) |

Trees are instanced (one wood draw + one leaf draw) so 253 crowns stay
interactive. Attractors, nodes, and leaves are capped for the browser;
raise the caps in `growTree.ts` if you want denser Hamlet-scale skeletons.

## Layout of `src/game`

```
catalog.ts     253 books: genre, chunks, excerpt, tags
growTree.ts    space colonization + pipe-model radii + leaf points
forest.ts      grove layout, roads, circuit waypoints, spawn at Hamlet
seasons.ts     canopy density + leaf / fog / ground palettes
sim.ts         cart pose, throttle, steer, trunk collision, teleport
Player.tsx     lantern cart + chase camera (A = left from behind)
Trees.tsx      InstancedMesh wood cylinders + icosahedron leaves
World.tsx      ground, roads, lantern trail, fog, plinth
HUD.tsx        plaque, minimap jump, atlas, lantern query, press
```

To grow from the real corpus instead of the bundled catalog, replace
`catalog.ts` with JSON from the ingestion pipeline (id, title, author,
genre, chunk count, excerpt, tags). `forest.ts` already sizes a tree from
`chunks` and leans it with `GENRE_TROPISM`.

## Stack

Vite 8 · React 19 · Three 0.186 · R3F 9 · Zustand 5 · Tailwind 4

Excerpts are public-domain Gutenberg text. No accounts, no server — the
press saves to `localStorage`.
