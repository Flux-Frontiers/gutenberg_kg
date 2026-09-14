import { BOOKS, type Book } from "./catalog";
import { GROW_VERSION, emitLeaves, emitWood, growTree } from "./growTree";
import { fibonacciAnnulus } from "./math";

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

export type Forest = {
  trees: TreeSite[];
  groves: Grove[];
  roads: RoadSeg[];
  circuit: Waypoint[];
  wood: {
    count: number;
    pos: Float32Array;
    quat: Float32Array;
    scale: Float32Array;
  };
  leaves: {
    count: number;
    pos: Float32Array;
    scale: Float32Array;
    tint: Uint8Array;
    treeIndex: Uint16Array;
  };
  spawn: { x: number; z: number; yaw: number };
  worldRadius: number;
  grid: Map<string, number[]>;
  cell: number;
};

let cached: Forest | null = null;
let cachedVersion = -1;

function cellKey(cx: number, cz: number): string {
  return cx + ":" + cz;
}

export function getForest(): Forest {
  if (cached && cachedVersion === GROW_VERSION) return cached;
  cached = buildForest();
  cachedVersion = GROW_VERSION;
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

function buildForest(): Forest {
  const byGenre = new Map<string, Book[]>();
  for (const b of BOOKS) {
    const list = byGenre.get(b.genre) ?? [];
    list.push(b);
    byGenre.set(b.genre, list);
  }
  const genres = [...byGenre.keys()];
  const nGenres = genres.length;
  const groveInner = 52;
  const groveOuter = groveInner + nGenres * 15.5;
  const groveCenters = fibonacciAnnulus(nGenres, groveInner, groveOuter);

  const groves: Grove[] = [];
  const trees: TreeSite[] = [];
  const woodPos: number[] = [];
  const woodQuat: number[] = [];
  const woodScale: number[] = [];
  const leafPos: number[] = [];
  const leafScale: number[] = [];
  const leafTint: number[] = [];
  const leafTree: number[] = [];

  genres.forEach((genre, gi) => {
    const books = byGenre.get(genre)!;
    const c = groveCenters[gi]!;
    const bookInner = 6.5;
    const bookOuter = Math.max(14, bookInner + books.length * 2.55);
    const spots = fibonacciAnnulus(books.length, bookInner, bookOuter);
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

    books.forEach((book, bi) => {
      const s = spots[bi]!;
      const x = c.x + s.x;
      const z = c.z + s.z;
      const grown = growTree({ slug: book.slug, genre: book.genre, nChunks: book.chunks });
      const woodStart = woodPos.length / 3;
      const woodCount = emitWood(grown, x, z, woodPos, woodQuat, woodScale);
      const leafStart = leafPos.length / 3;
      const leafCount = emitLeaves(grown, x, z, leafPos, leafScale, leafTint, 0.42);
      const treeIndex = trees.length;
      for (let k = 0; k < leafCount; k++) leafTree.push(treeIndex);
      trees.push({
        book,
        x,
        z,
        height: grown.trunkHeight,
        trunkRadius: Math.max(0.28, grown.trunkRadius),
        color,
        woodStart,
        woodCount,
        leafStart,
        leafCount,
      });
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

  const roads: RoadSeg[] = [];
  const hub = 3.6;
  for (const wp of circuit) {
    const d = Math.hypot(wp.x, wp.z) || 1;
    roads.push({
      ax: (wp.x / d) * hub,
      az: (wp.z / d) * hub,
      bx: wp.x,
      bz: wp.z,
      kind: "spoke",
    });
  }
  for (let i = 0; i < circuit.length; i++) {
    const a = circuit[i]!;
    const b = circuit[(i + 1) % circuit.length]!;
    roads.push({ ax: a.x, az: a.z, bx: b.x, bz: b.z, kind: "ring" });
  }

  return {
    trees,
    groves,
    roads,
    circuit,
    wood: {
      count: woodPos.length / 3,
      pos: new Float32Array(woodPos),
      quat: new Float32Array(woodQuat),
      scale: new Float32Array(woodScale),
    },
    leaves: {
      count: leafPos.length / 3,
      pos: new Float32Array(leafPos),
      scale: new Float32Array(leafScale),
      tint: Uint8Array.from(leafTint),
      treeIndex: Uint16Array.from(leafTree),
    },
    spawn: { x: spawnX, z: spawnZ, yaw: spawnYaw },
    worldRadius: worldRadius + 18,
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

export { seedFromKey } from "./math";
