import { BOOKS, type Book } from "./catalog";
import { GROW_VERSION, emitBark, emitLeaves, growTree, type BarkBuffers } from "./growTree";
import { packAroundHub, sunflower } from "./math";
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

/** The hub: a paved plaza around the sculpture's plinth (the cart collides with the plinth). */
export const HUB_PLAZA_R = 8;
export const HUB_SCULPTURE_R = 2.6;
// Home: 13 m out along the Kepler plaque's bearing, so the plaque stands between
// the cart and the sculpture; facing the hub (yaw convention of sim.yawToward).
const HOME_DIR = Math.atan2(4.6, -4.2);
const HOME = {
  x: Math.cos(HOME_DIR) * 13,
  z: Math.sin(HOME_DIR) * 13,
  yaw: Math.atan2(Math.cos(HOME_DIR), Math.sin(HOME_DIR)),
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
  spawn: { x: number; z: number; yaw: number };
  /** On the hub plaza behind the Kepler plaque, facing the sculpture. */
  home: { x: number; z: number; yaw: number };
  worldRadius: number;
  /** Radius of the hub sculpture's plinth, which the cart cannot drive through (0: none). */
  hubObstacle?: number;
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

function buildForest(leafMultiplier: number): Forest {
  const byGenre = new Map<string, Book[]>();
  for (const b of BOOKS) {
    const list = byGenre.get(b.genre) ?? [];
    list.push(b);
    byGenre.set(b.genre, list);
  }
  const genres = [...byGenre.keys()];
  const nGenres = genres.length;
  // Compact layout: trees on an even sunflower grid TREE_SPACING apart, and
  // groves packed as close to the hub as they fit, GROVE_GAP apart for roads.
  // (The old linear spirals spread 253 trees over a ~370 m radius.)
  const TREE_SPACING = 9;
  const GROVE_GAP = 10;
  const bookInner = 6.5;
  const layouts = genres.map((g) => sunflower(byGenre.get(g)!.length, bookInner, TREE_SPACING));
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
      const grown = growTree({ slug: book.slug, genre: book.genre, nChunks: book.chunks, leafScale: leafMultiplier });
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

  const hamlet = trees.find((t) => t.book.slug === "hamlet");
  let spawnX = 0;
  let spawnZ = 8;
  let spawnYaw = 0;
  if (hamlet) {
    const dx = hamlet.x;
    const dz = hamlet.z;
    const dist = Math.hypot(dx, dz) || 1;
    spawnX = hamlet.x - (dx / dist) * 14;
    spawnZ = hamlet.z - (dz / dist) * 14;
    spawnYaw = Math.atan2(-dx / dist, -dz / dist);
  }

  const circuit = groves
    .map((g) => groveApproach(g))
    .sort((a, b) => Math.atan2(a.z, a.x) - Math.atan2(b.z, b.x));

  // Roads are routed around the trunks (routing.ts). The centreline keeps
  // ROAD_CLEARANCE from every trunk surface: half the widest road (1.7 m) plus
  // the cart's radius (1.05 m), so nothing on a road can pin the cart.
  const ROAD_CLEARANCE = 2.75;
  const obstacles = [
    ...trees.map((t) => ({ x: t.x, z: t.z, r: t.trunkRadius })),
    { x: 0, z: 0, r: HUB_SCULPTURE_R },
  ];
  const net = routeNetwork({
    hubR: HUB_PLAZA_R - 1,
    stops: circuit.map((wp) => [wp.x, wp.z] as [number, number]),
    obstacles,
    worldR: Math.max(...groves.map((g) => Math.hypot(g.x, g.z) + g.radius)) + 20,
    need: ROAD_CLEARANCE,
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
  const plazas = [{ x: 0, z: 0, r: HUB_PLAZA_R }, ...circuit.map((wp) => ({ x: wp.x, z: wp.z, r: 4 }))];
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
    spawn: { x: spawnX, z: spawnZ, yaw: spawnYaw },
    home: HOME,
    worldRadius: worldRadius + 18,
    hubObstacle: HUB_SCULPTURE_R,
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
