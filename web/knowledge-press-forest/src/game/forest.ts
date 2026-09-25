import { BOOKS, type Book } from "./catalog";
import { growCorpusTree, type CorpusTree } from "./corpusTree";
import { EXHIBITS, placeExhibits, type Exhibit } from "./exhibits";
import { GROW_VERSION, emitBark, emitLeaves, growTree, type BarkBuffers, type GrownTree } from "./growTree";
import { loopOrder, packAroundHub, sunflower } from "./math";
import { routeNetwork } from "./routing";
import { SPECIES, speciesFor } from "./species";

export const GENRE_PALETTE = [
  "#c45c4a",
  "#5b8fbf",
  "#4a9b6e",
  "#c48a3a",
  "#7a6ea8",
  "#3aa89a",
  "#c46b3a",
  "#b85a78",
  "#4aa8b8",
  "#8aa84a",
];

export type Grove = {
  genre: string;
  label: string;
  x: number;
  z: number;
  radius: number;
  color: string;
  bookCount: number;
};

export type TreeSite = {
  book: Book;
  x: number;
  z: number;
  height: number;
  trunkRadius: number;
  color: string;
  /** Index into SPECIES. */
  species: number;
  /** Index into forest.chunks (its grove). */
  chunk: number;
  /** Vertex range of this tree in forest.chunks[chunk].bark. */
  woodStart: number;
  woodCount: number;
  leafStart: number;
  leafCount: number;
};

export type RoadSeg = {
  ax: number;
  az: number;
  bx: number;
  bz: number;
  kind: "spoke" | "ring";
};

export type Waypoint = {
  x: number;
  z: number;
  yaw: number;
  genre: string;
  label: string;
};

/** The hub: a paved plaza around the corpus redwood (the cart collides with its root flare). */
export const HUB_PLAZA_R = 10;
/** Bearing of the redwood's plaque from the hub; home looks back along it. */
export const HUB_PLAQUE_DIR = Math.atan2(4.6, -4.2);
export const HUB_PLAQUE_DIST = 7.2;
// Home: 15 m out along the plaque's bearing, so the plaque stands between the
// cart and the redwood; facing the hub (yaw convention of sim.yawToward).
const HOME = {
  x: Math.cos(HUB_PLAQUE_DIR) * 15,
  z: Math.sin(HUB_PLAQUE_DIR) * 15,
  yaw: Math.atan2(Math.cos(HUB_PLAQUE_DIR), Math.sin(HUB_PLAQUE_DIR)),
};

export type Chunk = {
  genre: string;
  species: number;
  x: number;
  z: number;
  /** Horizontal radius holding every trunk and crown. */
  radius: number;
  bark: { count: number; pos: Float32Array; normal: Float32Array; uv: Float32Array; index: Uint32Array };
  /** This grove's contiguous range in forest.leaves. */
  leafStart: number;
  leafCount: number;
};

/** A road centreline in the ground plane; `closed` joins the last point to the first. */
export type RoadLine = { kind: "spoke" | "ring"; pts: [number, number][]; closed: boolean };

export type Forest = {
  trees: TreeSite[];
  groves: Grove[];
  /** Straight pieces of every road line, for clearance tests. */
  roads: RoadSeg[];
  roadLines: RoadLine[];
  /** Road junctions (ring stops and the hub), each paved with a disc. */
  plazas: { x: number; z: number; r: number }[];
  /** One stop per grove, for signposts. */
  circuit: Waypoint[];
  /** The ring road sampled every ~2 m, for the guided tour to follow. */
  ringPath: Waypoint[];
  /**
   * One render chunk per grove: its bark mesh and its leaf range. A grove is one
   * genre and so one species; per-grove meshes let the renderer skip groves out
   * of view or lost in the fog instead of drawing the whole forest every frame.
   */
  chunks: Chunk[];
  leaves: {
    count: number;
    pos: Float32Array;
    scale: Float32Array;
    /** Leaf orientation quaternions (x, y, z, w). */
    quat: Float32Array;
    tint: Uint8Array;
    treeIndex: Uint16Array;
    species: Uint8Array;
  };
  /** Where the drive starts: home. */
  spawn: { x: number; z: number; yaw: number };
  /** On the hub plaza behind the redwood's plaque, facing the redwood. */
  home: { x: number; z: number; yaw: number };
  worldRadius: number;
  /** The corpus redwood at the hub: one limb per book. */
  corpusTree: CorpusTree;
  /** Set pieces in roadside glades. */
  exhibits: Exhibit[];
  /** Discs the cart cannot drive into besides trunks: the redwood and each exhibit's plinth. */
  obstacles: { x: number; z: number; r: number }[];
  grid: Map<string, number[]>;
  cell: number;
};

let cached: Forest | null = null;
let cachedVersion = "";

function cellKey(cx: number, cz: number): string {
  return cx + ":" + cz;
}

export function getForest(leafMultiplier = 1): Forest {
  const key = `${GROW_VERSION}:${leafMultiplier}`;
  if (cached && cachedVersion === key) return cached;
  cached = buildForest(leafMultiplier);
  cachedVersion = key;
  return cached;
}

/** Stand just outside a grove, facing its heart. */
export function groveApproach(g: Grove): Waypoint {
  const dist = Math.hypot(g.x, g.z) || 1;
  const ux = g.x / dist;
  const uz = g.z / dist;
  const stand = Math.max(7, dist - g.radius - 1.4);
  const x = ux * stand;
  const z = uz * stand;
  const yaw = Math.atan2(-ux, -uz);
  return { x, z, yaw, genre: g.genre, label: g.label };
}

export function groveByGenre(forest: Forest, genre: string): Grove | undefined {
  return forest.groves.find((g) => g.genre === genre);
}

/** Trunks in a grove stand at least this far apart, for driving room. */
const MIN_TRUNK_GAP = 7.5;
/** Clear air kept between neighbouring trees' wood (crown shyness). */
const CROWN_GAP = 0.6;
const WOOD_CELL = 2;

/**
 * Place a grove's trees as close to its heart as their wood allows: largest
 * crown first, each tree takes the innermost spot on a fine sunflower spiral
 * where its trunk keeps MIN_TRUNK_GAP and every branch keeps CROWN_GAP of air
 * from the trees already standing. Crowns may interleave (a small tree under a
 * big one's limbs) but never pass through each other. Returns trunk offsets
 * from the grove centre in `grown` order, and the farthest trunk's distance.
 */
function shyLayout(grown: GrownTree[], inner: number): { pts: { x: number; z: number }[]; outer: number } {
  const n = grown.length;
  const reach = grown.map(({ skeleton: { nodes, n: m } }) => {
    let r = 0;
    for (let k = 0; k < m; k++) r = Math.max(r, Math.hypot(nodes[k * 3]!, nodes[k * 3 + 2]!));
    return r;
  });
  const order = [...Array(n).keys()].sort((a, b) => reach[b]! - reach[a]! || a - b);
  const cands = sunflower(n * 80 + 200, inner, 2).pts;
  const placed: { i: number; x: number; z: number }[] = [];
  // Placed wood as flat (x, y, z, padded radius) runs in a 3-D hash grid.
  const grid = new Map<string, number[]>();
  const key = (x: number, y: number, z: number) => Math.floor(x / WOOD_CELL) + "," + Math.floor(y / WOOD_CELL) + "," + Math.floor(z / WOOD_CELL);
  const pad = (i: number, k: number) => grown[i]!.skeleton.radii[k]! + 0.5 * grown[i]!.step;
  const out: { x: number; z: number }[] = new Array(n);

  const woodHits = (i: number, cx: number, cz: number, near: typeof placed) => {
    const { nodes, n: m } = grown[i]!.skeleton;
    for (let k = 0; k < m; k++) {
      const x = cx + nodes[k * 3]!, y = nodes[k * 3 + 1]!, z = cz + nodes[k * 3 + 2]!;
      // Only branches inside a neighbour's crown can touch it.
      if (!near.some((p) => Math.hypot(x - p.x, z - p.z) <= reach[p.i]! + WOOD_CELL)) continue;
      const pk = pad(i, k) + CROWN_GAP;
      const gx = Math.floor(x / WOOD_CELL), gy = Math.floor(y / WOOD_CELL), gz = Math.floor(z / WOOD_CELL);
      for (let a = gx - 1; a <= gx + 1; a++) for (let b = gy - 1; b <= gy + 1; b++) for (let c = gz - 1; c <= gz + 1; c++) {
        const cell = grid.get(a + "," + b + "," + c);
        if (!cell) continue;
        for (let q = 0; q < cell.length; q += 4) {
          if (Math.hypot(x - cell[q]!, y - cell[q + 1]!, z - cell[q + 2]!) < pk + cell[q + 3]!) return true;
        }
      }
    }
    return false;
  };

  for (const i of order) {
    for (const c of cands) {
      if (placed.some((p) => Math.hypot(p.x - c.x, p.z - c.z) < MIN_TRUNK_GAP)) continue;
      const near = placed.filter((p) => Math.hypot(p.x - c.x, p.z - c.z) < reach[i]! + reach[p.i]! + CROWN_GAP);
      if (near.length && woodHits(i, c.x, c.z, near)) continue;
      placed.push({ i, x: c.x, z: c.z });
      out[i] = c;
      const { nodes, n: m } = grown[i]!.skeleton;
      for (let k = 0; k < m; k++) {
        const x = c.x + nodes[k * 3]!, y = nodes[k * 3 + 1]!, z = c.z + nodes[k * 3 + 2]!;
        const kk = key(x, y, z);
        const cell = grid.get(kk);
        if (cell) cell.push(x, y, z, pad(i, k)); else grid.set(kk, [x, y, z, pad(i, k)]);
      }
      break;
    }
  }
  return { pts: out, outer: Math.max(0, ...out.map((p) => Math.hypot(p.x, p.z))) };
}

/**
 * Does the ring double back at this stop (arrive and leave within 60 degrees of
 * each other)? Such a stop gets a wide turning circle instead of a junction disc.
 */
function turnsBack(ring: [number, number][], wp: { x: number; z: number }): boolean {
  const n = ring.length;
  let k = 0, best = Infinity;
  ring.forEach(([x, z], i) => {
    const d = Math.hypot(x - wp.x, z - wp.z);
    if (d < best) { best = d; k = i; }
  });
  const [ax, az] = ring[(k - 3 + n) % n]!, [bx, bz] = ring[k]!, [cx, cz] = ring[(k + 3) % n]!;
  const inx = bx - ax, inz = bz - az, outx = cx - bx, outz = cz - bz;
  const cos = (inx * outx + inz * outz) / ((Math.hypot(inx, inz) * Math.hypot(outx, outz)) || 1);
  return cos < -0.5;
}

function buildForest(leafMultiplier: number): Forest {
  const byGenre = new Map<string, Book[]>();
  for (const b of BOOKS) {
    const list = byGenre.get(b.genre) ?? [];
    list.push(b);
    byGenre.set(b.genre, list);
  }
  const genres = [...byGenre.keys()];
  const nGenres = genres.length;
  // Compact layout: trees packed as tight as their crowns allow (shyLayout),
  // and groves packed as close to the hub as they fit, GROVE_GAP apart for roads.
  const GROVE_GAP = 10;
  const bookInner = 6.5;
  const grownBy = genres.map((g) => byGenre.get(g)!.map((book) =>
    growTree({ slug: book.slug, genre: book.genre, nChunks: book.chunks, leafScale: leafMultiplier })));
  const layouts = grownBy.map((g) => shyLayout(g, bookInner));
  const groveRadius = (outer: number) => Math.max(14, outer) + 6;
  const groveCenters = packAroundHub(layouts.map((l) => groveRadius(l.outer)), 22, GROVE_GAP);

  const groves: Grove[] = [];
  const trees: TreeSite[] = [];
  const chunks: Chunk[] = [];
  const leafSpecies: number[] = [];
  const leafPos: number[] = [];
  const leafScale: number[] = [];
  const leafTint: number[] = [];
  const leafQuat: number[] = [];
  const leafTree: number[] = [];

  genres.forEach((genre, gi) => {
    const books = byGenre.get(genre)!;
    const c = groveCenters[gi]!;
    const bookOuter = Math.max(14, layouts[gi]!.outer);
    const spots = layouts[gi]!.pts;
    const color = GENRE_PALETTE[gi % GENRE_PALETTE.length]!;
    groves.push({
      genre,
      label: books[0]?.genreLabel ?? genre,
      x: c.x,
      z: c.z,
      radius: bookOuter + 6,
      color,
      bookCount: books.length,
    });
    const species = speciesFor(genre);
    const bark: BarkBuffers = { pos: [], normal: [], uv: [], index: [] };
    const chunkLeafStart = leafPos.length / 3;

    books.forEach((book, bi) => {
      const s = spots[bi]!;
      const x = c.x + s.x;
      const z = c.z + s.z;
      const grown = grownBy[gi]![bi]!;
      const woodStart = bark.pos.length / 3;
      const woodCount = emitBark(grown, x, z, bark, SPECIES[species]!.barkAspect);
      const leafStart = leafPos.length / 3;
      const leafCount = emitLeaves(grown, x, z, leafPos, leafScale, leafTint, leafQuat, 0.22);
      const treeIndex = trees.length;
      for (let k = 0; k < leafCount; k++) {
        leafTree.push(treeIndex);
        leafSpecies.push(species);
      }
      trees.push({
        book,
        x,
        z,
        height: grown.trunkHeight,
        trunkRadius: Math.max(0.28, grown.trunkRadius),
        color,
        species,
        chunk: gi,
        woodStart,
        woodCount,
        leafStart,
        leafCount,
      });
    });
    chunks.push({
      genre,
      species,
      x: c.x,
      z: c.z,
      radius: bookOuter + 12,
      bark: {
        count: bark.pos.length / 3,
        pos: new Float32Array(bark.pos),
        normal: new Float32Array(bark.normal),
        uv: new Float32Array(bark.uv),
        index: new Uint32Array(bark.index),
      },
      leafStart: chunkLeafStart,
      leafCount: leafPos.length / 3 - chunkLeafStart,
    });
  });

  const cell = 16;
  const grid = new Map<string, number[]>();
  trees.forEach((t, i) => {
    const cx = Math.floor(t.x / cell);
    const cz = Math.floor(t.z / cell);
    const k = cellKey(cx, cz);
    const arr = grid.get(k);
    if (arr) arr.push(i);
    else grid.set(k, [i]);
  });

  let worldRadius = 80;
  for (const g of groves) {
    const d = Math.hypot(g.x, g.z) + g.radius;
    if (d > worldRadius) worldRadius = d;
  }

  // The ring visits the stops as one short loop that never crosses itself.
  // Angle order alone zigzags between near and far groves, doubling back at
  // every stop, because the groves sit at very different distances from the hub.
  const byAngle = groves
    .map((g) => groveApproach(g))
    .sort((a, b) => Math.atan2(a.z, a.x) - Math.atan2(b.z, b.x));
  const circuit = loopOrder(byAngle, byAngle.map((_, i) => i)).map((i) => byAngle[i]!);
  // A few spokes, spread around the hub, instead of one to every grove:
  // nearest stops first, each at least SPOKE_SPREAD from the spokes already chosen.
  const SPOKE_SPREAD = Math.PI / 3.2;
  const spokeTo: number[] = [];
  for (const i of circuit.map((_, i) => i).sort((a, b) => Math.hypot(circuit[a]!.x, circuit[a]!.z) - Math.hypot(circuit[b]!.x, circuit[b]!.z))) {
    const a = Math.atan2(circuit[i]!.z, circuit[i]!.x);
    if (spokeTo.every((j) => Math.abs(Math.atan2(Math.sin(a - Math.atan2(circuit[j]!.z, circuit[j]!.x)), Math.cos(a - Math.atan2(circuit[j]!.z, circuit[j]!.x)))) >= SPOKE_SPREAD)) spokeTo.push(i);
  }

  // Roads are routed around the trunks (routing.ts). The centreline keeps
  // ROAD_CLEARANCE from every trunk surface: half the widest road (1.7 m) plus
  // the cart's radius (1.05 m), so nothing on a road can pin the cart.
  const ROAD_CLEARANCE = 2.75;
  const fir = SPECIES.find((s) => s.name === "fir")!;
  const corpusTree = growCorpusTree(trees, fir.barkAspect);
  const net = routeNetwork({
    hubR: HUB_PLAZA_R - 1,
    stops: circuit.map((wp) => [wp.x, wp.z] as [number, number]),
    obstacles: [
      ...trees.map((t) => ({ x: t.x, z: t.z, r: t.trunkRadius })),
      { x: 0, z: 0, r: corpusTree.baseRadius },
    ],
    worldR: Math.max(...groves.map((g) => Math.hypot(g.x, g.z) + g.radius)) + 20,
    need: ROAD_CLEARANCE,
    spokeTo,
  });
  const roadLines: RoadLine[] = net.spokes.map((pts) => ({ kind: "spoke", pts, closed: false }));
  const ring = { pts: net.ring.pts, span: net.ring.leg };
  roadLines.push({ kind: "ring", pts: ring.pts, closed: true });
  const roads: RoadSeg[] = [];
  for (const line of roadLines) {
    const n = line.pts.length;
    for (let i = 0; i < (line.closed ? n : n - 1); i++) {
      const [ax, az] = line.pts[i]!;
      const [bx, bz] = line.pts[(i + 1) % n]!;
      roads.push({ ax, az, bx, bz, kind: line.kind });
    }
  }
  const exhibits = placeExhibits({ specs: EXHIBITS, roadLines, trees, worldRadius });
  const plazas = [
    { x: 0, z: 0, r: HUB_PLAZA_R },
    ...circuit.map((wp) => ({ x: wp.x, z: wp.z, r: turnsBack(ring.pts, wp) ? 6 : 4 })),
    ...exhibits.map((e) => ({ x: e.x, z: e.z, r: e.plazaR })),
  ];
  // Each ring sample carries the grove whose stop comes next, so the tour still
  // lights the right signpost and trail.
  const ringPath: Waypoint[] = ring.pts.map(([x, z], i) => {
    const [nx, nz] = ring.pts[(i + 1) % ring.pts.length]!;
    const wp = circuit[(ring.span[i]! + 1) % circuit.length]!;
    return { x, z, yaw: Math.atan2(-(nx - x), -(nz - z)), genre: wp.genre, label: wp.label };
  });

  return {
    trees,
    groves,
    roads,
    roadLines,
    plazas,
    circuit,
    ringPath,
    chunks,
    leaves: {
      count: leafPos.length / 3,
      pos: new Float32Array(leafPos),
      scale: new Float32Array(leafScale),
      quat: new Float32Array(leafQuat),
      tint: Uint8Array.from(leafTint),
      treeIndex: Uint16Array.from(leafTree),
      species: Uint8Array.from(leafSpecies),
    },
    spawn: HOME,
    home: HOME,
    worldRadius: worldRadius + 18,
    corpusTree,
    exhibits,
    obstacles: [{ x: 0, z: 0, r: corpusTree.baseRadius }, ...exhibits.map((e) => ({ x: e.x, z: e.z, r: e.obstacle }))],
    grid,
    cell,
  };
}

export function treesNear(forest: Forest, x: number, z: number, radius: number): TreeSite[] {
  const { grid, cell, trees } = forest;
  const r = radius;
  const minCx = Math.floor((x - r) / cell);
  const maxCx = Math.floor((x + r) / cell);
  const minCz = Math.floor((z - r) / cell);
  const maxCz = Math.floor((z + r) / cell);
  const out: TreeSite[] = [];
  const r2 = r * r;
  for (let cx = minCx; cx <= maxCx; cx++) {
    for (let cz = minCz; cz <= maxCz; cz++) {
      const ids = grid.get(cellKey(cx, cz));
      if (!ids) continue;
      for (const i of ids) {
        const t = trees[i]!;
        const dx = t.x - x;
        const dz = t.z - z;
        if (dx * dx + dz * dz <= r2) out.push(t);
      }
    }
  }
  return out;
}

export function bookMatchesQuery(book: Book, q: string): boolean {
  if (!q.trim()) return false;
  const s = q.trim().toLowerCase();
  if (book.title.toLowerCase().includes(s)) return true;
  if (book.author.toLowerCase().includes(s)) return true;
  if (book.genreLabel.toLowerCase().includes(s)) return true;
  if (book.genre.toLowerCase().includes(s)) return true;
  if (book.tags.some((t) => t.includes(s))) return true;
  if (book.excerpt.toLowerCase().includes(s)) return true;
  return false;
}

/** Matching trees, nearest to (x, z) first. */
export function searchTrees(forest: Pick<Forest, "trees">, q: string, x: number, z: number): TreeSite[] {
  return forest.trees
    .filter((t) => bookMatchesQuery(t.book, q))
    .sort((a, b) => Math.hypot(a.x - x, a.z - z) - Math.hypot(b.x - x, b.z - z));
}

/** A pose a few metres from the tree on the side facing (fromX, fromZ), looking at the trunk. */
export function treeApproach(t: TreeSite, fromX: number, fromZ: number): { x: number; z: number; yaw: number } {
  const dx = fromX - t.x;
  const dz = fromZ - t.z;
  const d = Math.hypot(dx, dz) || 1;
  const stand = t.trunkRadius + 4.5; // Inside the 6.8 m read radius.
  const x = t.x + (dx / d) * stand;
  const z = t.z + (dz / d) * stand;
  return { x, z, yaw: Math.atan2(-(t.x - x), -(t.z - z)) };
}

export { seedFromKey } from "./math";
