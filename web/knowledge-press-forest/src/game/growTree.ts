import { clamp, mulberry32, seedFromKey } from "./math";

export type Vec3 = { x: number; y: number; z: number };

export type Skeleton = {
  nodes: Float32Array;
  parents: Int32Array;
  radii: Float32Array;
  n: number;
};

export type GrownTree = {
  skeleton: Skeleton;
  crown: Float32Array;
  /** Where each leaf's stalk meets its twig. */
  leafPoints: Float32Array;
  /** Unit stalk-to-tip direction per leaf: out from the twig and toward the sky. */
  leafDirs: Float32Array;
  leafTint: Uint8Array;
  nLeaves: number;
  /** The book's chunk count; leaf size shrinks with it, as in the Python viz3d. */
  nChunks: number;
  /** Internode length colonize chose; kill radius is 2 * step. */
  step: number;
  trunkHeight: number;
  trunkRadius: number;
};

/** Bump when caps change so the forest cache rebuilds. */
export const GROW_VERSION = 10;

// This file mirrors the Python viz3d (kg_utils.viz3d.organic.colonize and
// gutenberg_kg.treegeom.grow_tree_geometry) so both front ends grow the same
// tree from the same book: every chunk is a crown point, growth reaches for up
// to MAX_ATTRACTORS of them with no node cap, and distances come from the
// crown's own scale.
//
// The web world is smaller: trunks are 1.7 * log2(1 + chunks) here against
// ForestLayout's 4 * log2(1 + chunks), so lengths carrying absolute units
// (the tip radius) are scaled by WORLD_SCALE to keep Python's proportions.
const WORLD_SCALE = 1.7 / 4;
/** kg_utils.viz3d.organic.MAX_ATTRACTORS */
export const MAX_ATTRACTORS = 3000;
/** colonize(max_iter=800) */
const MAX_ITER = 800;
/** colonize(jitter=0.12) */
const JITTER = 0.12;
/** grow_tree(tip_radius=0.05), in web units. */
const TIP_RADIUS = 0.05 * WORLD_SCALE;
/** Runaway guard only; Python has no node cap and real books stay far below it. */
const NODE_GUARD = 200_000;
/** treegeom.LEAF_REFERENCE_COUNT: leaves shrink as (600 / chunks) ** (1/3) beyond it. */
export const LEAF_REFERENCE_COUNT = 600;

// Pipe-model exponent: parent^e = sum child^e (Leonardo's rule), as pipe_radii.
const PIPE_EXP = 2;
// Trunk radius floor as a fraction of height, for very small books.
const TRUNK_PER_HEIGHT = 0.028;
// A leaf hangs within this of a branch node; a chunk farther out is drawn in
// along the line to its nearest node, so it stays at its own place in the crown.
const LEAF_REACH = 0.35;

const GOLDEN = Math.PI * (3 - Math.sqrt(5));

export const GENRE_TROPISM: Record<string, Vec3> = {
  philosophy: { x: 0, y: 0.32, z: 0 },
  "sacred-texts": { x: 0, y: 0.28, z: 0 },
  "natural-history": { x: 0, y: 0.22, z: 0 },
  "science-fiction": { x: 0, y: 0.26, z: 0 },
  horror: { x: 0, y: 0.06, z: 0 },
  diaries: { x: 0, y: 0.05, z: 0 },
  letters: { x: 0, y: 0.05, z: 0 },
  shakespeare: { x: 0, y: 0.12, z: 0 },
  drama: { x: 0, y: 0.1, z: 0 },
  poetry: { x: 0, y: -0.1, z: 0 },
  "american-literature": { x: 0, y: 0.16, z: 0 },
  "english-literature": { x: 0, y: 0.18, z: 0 },
};

const DEFAULT_TROPISM: Vec3 = { x: 0, y: 0.18, z: 0 };

function tropismFor(genre: string): Vec3 {
  return GENRE_TROPISM[genre] ?? DEFAULT_TROPISM;
}

/** Place section tips and one crown point per chunk, the way ForestLayout does. */
export function placeCrown(
  nChunks: number,
  genre: string,
  slug: string,
): { trunkHeight: number; crown: Float32Array; nCrown: number } {
  const rng = mulberry32(seedFromKey(slug + ":crown"));
  const trunkHeight = Math.min(1.7 * Math.max(1, Math.log2(1 + nChunks)), 22);
  const nSections = Math.max(5, Math.round(Math.sqrt(nChunks) * 1.25));
  const branchLength = 2.1 + Math.sqrt(nSections) * 0.55;
  const nLeaf = Math.max(1, nChunks);

  const sectionTips: Vec3[] = [];
  for (let i = 0; i < nSections; i++) {
    const t = nSections === 1 ? 0.5 : i / (nSections - 1);
    const y = trunkHeight * (0.3 + 0.65 * t);
    const angle = i * GOLDEN;
    const radius = branchLength * (1 - (y / trunkHeight) * 0.4);
    sectionTips.push({
      x: radius * Math.cos(angle),
      y,
      z: radius * Math.sin(angle),
    });
  }

  const leaves = new Float32Array(nLeaf * 3);
  let li = 0;
  const perSec = Math.max(1, Math.ceil(nLeaf / nSections));
  for (let s = 0; s < nSections && li < nLeaf; s++) {
    const tip = sectionTips[s]!;
    const facingX = tip.x;
    const facingZ = tip.z;
    const fl = Math.hypot(facingX, facingZ) || 1;
    const fx = facingX / fl;
    const fz = facingZ / fl;
    const leafR = 1.15 + Math.sqrt(perSec) * 0.18;
    const take = Math.min(perSec, nLeaf - li);
    for (let k = 0; k < take; k++) {
      const u = rng();
      const v = rng();
      const theta = u * Math.PI * 2;
      const r = leafR * Math.cbrt(v);
      const up = (rng() * 0.7 + 0.15) * leafR * 0.55;
      const px = Math.cos(theta) * r;
      const pz = Math.sin(theta) * r;
      leaves[li * 3] = tip.x + fx * r * 0.35 + px * 0.7;
      leaves[li * 3 + 1] = tip.y + up;
      leaves[li * 3 + 2] = tip.z + fz * r * 0.35 + pz * 0.7;
      li++;
    }
  }
  void genre;
  return { trunkHeight, crown: leaves, nCrown: li };
}

/** Nearest skeleton node to a point, through a uniform hash grid of the nodes. */
function nearestNodeIndex(nodes: Float32Array, n: number, cell: number) {
  const grid = new Map<string, number[]>();
  const key = (i: number, j: number, k: number) => i + "," + j + "," + k;
  for (let a = 0; a < n; a++) {
    const kk = key(Math.floor(nodes[a * 3]! / cell), Math.floor(nodes[a * 3 + 1]! / cell), Math.floor(nodes[a * 3 + 2]! / cell));
    const list = grid.get(kk);
    if (list) list.push(a); else grid.set(kk, [a]);
  }
  return (x: number, y: number, z: number) => {
    const ci = Math.floor(x / cell), cj = Math.floor(y / cell), ck = Math.floor(z / cell);
    let best = 0, bestD = Infinity;
    // Grow the searched shell until it cannot hold anything closer than the best found.
    for (let r = 0; r < 4096; r++) {
      for (let i = ci - r; i <= ci + r; i++) for (let j = cj - r; j <= cj + r; j++) for (let k = ck - r; k <= ck + r; k++) {
        if (Math.max(Math.abs(i - ci), Math.abs(j - cj), Math.abs(k - ck)) !== r) continue;
        const list = grid.get(key(i, j, k));
        if (!list) continue;
        for (const a of list) {
          const dx = x - nodes[a * 3]!, dy = y - nodes[a * 3 + 1]!, dz = z - nodes[a * 3 + 2]!;
          const d2 = dx * dx + dy * dy + dz * dz;
          if (d2 < bestD) { bestD = d2; best = a; }
        }
      }
      if (bestD <= r * cell * r * cell) break;
    }
    return best;
  };
}

/** Gaussian sample from a uniform generator (Box-Muller). */
function gauss(rng: () => number): number {
  return Math.sqrt(-2 * Math.log(1 - rng())) * Math.cos(2 * Math.PI * rng());
}

/** organic.crown_spacing: median nearest-neighbour distance over up to 512 probes. */
function crownSpacing(pts: Float32Array, m: number, rng: () => number): number {
  if (m < 2) return 1;
  const probes = Math.min(512, m);
  const gaps: number[] = [];
  for (let s = 0; s < probes; s++) {
    const i = probes === m ? s : Math.floor(rng() * m);
    let best = Infinity;
    const x = pts[i * 3]!, y = pts[i * 3 + 1]!, z = pts[i * 3 + 2]!;
    for (let j = 0; j < m; j++) {
      const dx = x - pts[j * 3]!, dy = y - pts[j * 3 + 1]!, dz = z - pts[j * 3 + 2]!;
      const d2 = dx * dx + dy * dy + dz * dz;
      if (d2 > 0 && d2 < best) best = d2;
    }
    if (best < Infinity) gaps.push(Math.sqrt(best));
  }
  gaps.sort((a, b) => a - b);
  return gaps.length ? Math.max(gaps[gaps.length >> 1]!, 1e-6) : 1;
}

/**
 * Port of kg_utils.viz3d.organic.colonize. Each live attractor pulls its
 * nearest node within `influence`; every pulled node grows one `step` along the
 * averaged pull plus tropism and jitter; attractors within `kill` of a node are
 * consumed. An unreachable crown is bridged, and survivors each get a twig.
 *
 * Python recomputes the full attractor x node distance matrix every iteration.
 * Nodes are only ever added, so each attractor's nearest node is updated
 * against the new nodes alone: the same answer, O(attractors x nodes) in total.
 */
function colonize(pts: Float32Array, m: number, trop: Vec3, rng: () => number) {
  let minX = Infinity, minY = Infinity, minZ = Infinity, maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (let a = 0; a < m; a++) {
    minX = Math.min(minX, pts[a * 3]!); maxX = Math.max(maxX, pts[a * 3]!);
    minY = Math.min(minY, pts[a * 3 + 1]!); maxY = Math.max(maxY, pts[a * 3 + 1]!);
    minZ = Math.min(minZ, pts[a * 3 + 2]!); maxZ = Math.max(maxZ, pts[a * 3 + 2]!);
  }
  const extent = Math.hypot(maxX - minX, maxY - minY, maxZ - minZ);
  const step = Math.max(extent / 40, 0.5 * crownSpacing(pts, m, rng));
  const influence = 12 * step;
  const kill = 2 * step;

  const nodes: number[] = [0, 0, 0];
  const parents: number[] = [-1];
  const n = () => parents.length;
  const alive = new Uint8Array(m).fill(1);
  const nearest = new Int32Array(m);
  const nearestD = new Float64Array(m);
  for (let a = 0; a < m; a++) nearestD[a] = Math.hypot(pts[a * 3]!, pts[a * 3 + 1]!, pts[a * 3 + 2]!);

  const refresh = (from: number) => {
    const to = n();
    for (let a = 0; a < m; a++) {
      if (!alive[a]) continue;
      const ax = pts[a * 3]!, ay = pts[a * 3 + 1]!, az = pts[a * 3 + 2]!;
      // Squared distances in the hot loop; Math.hypot is several times slower.
      let best2 = nearestD[a]! * nearestD[a]!, bestK = -1;
      for (let k = from; k < to; k++) {
        const dx = ax - nodes[k * 3]!, dy = ay - nodes[k * 3 + 1]!, dz = az - nodes[k * 3 + 2]!;
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < best2) { best2 = d2; bestK = k; }
      }
      if (bestK >= 0) { nearestD[a] = Math.sqrt(best2); nearest[a] = bestK; }
    }
  };
  // March internodes from a node until the target is within stopAt.
  const bridge = (from: number, tx: number, ty: number, tz: number, stopAt: number) => {
    let cur = from;
    for (let i = 0; i < MAX_ITER && n() < NODE_GUARD; i++) {
      const gx = tx - nodes[cur * 3]!, gy = ty - nodes[cur * 3 + 1]!, gz = tz - nodes[cur * 3 + 2]!;
      const d = Math.hypot(gx, gy, gz);
      if (d <= stopAt) return;
      const s = Math.min(step, d) / d;
      nodes.push(nodes[cur * 3]! + gx * s, nodes[cur * 3 + 1]! + gy * s, nodes[cur * 3 + 2]! + gz * s);
      parents.push(cur);
      cur = n() - 1;
    }
  };

  // The root sits outside every influence sphere: lead a trunk to the nearest attractor.
  let first = 0;
  for (let a = 1; a < m; a++) if (nearestD[a]! < nearestD[first]!) first = a;
  if (m > 0) bridge(0, pts[first * 3]!, pts[first * 3 + 1]!, pts[first * 3 + 2]!, influence);
  refresh(1);

  const pull = new Map<number, [number, number, number]>();
  for (let iter = 0; iter < MAX_ITER && n() < NODE_GUARD; iter++) {
    let live = 0, inRange = 0, closest = -1;
    for (let a = 0; a < m; a++) {
      if (!alive[a]) continue;
      live++;
      if (nearestD[a]! <= influence) inRange++;
      if (closest < 0 || nearestD[a]! < nearestD[closest]!) closest = a;
    }
    if (!live) break;
    if (!inRange) {
      // The rest of the crown lies across a gap wider than the influence radius: grow a limb across it.
      const before = n();
      bridge(nearest[closest]!, pts[closest * 3]!, pts[closest * 3 + 1]!, pts[closest * 3 + 2]!, influence);
      refresh(before);
      continue;
    }
    pull.clear();
    for (let a = 0; a < m; a++) {
      if (!alive[a] || nearestD[a]! > influence) continue;
      const k = nearest[a]!;
      const vx = pts[a * 3]! - nodes[k * 3]!, vy = pts[a * 3 + 1]! - nodes[k * 3 + 1]!, vz = pts[a * 3 + 2]! - nodes[k * 3 + 2]!;
      const d = Math.hypot(vx, vy, vz);
      if (d < 1e-9) continue;
      const acc = pull.get(k) ?? [0, 0, 0];
      acc[0] += vx / d; acc[1] += vy / d; acc[2] += vz / d;
      pull.set(k, acc);
    }
    if (!pull.size) break;
    const before = n();
    for (const [k, [px, py, pz]] of pull) {
      const pl = Math.max(Math.hypot(px, py, pz), 1e-9);
      let dx = px / pl + trop.x + JITTER * gauss(rng);
      let dy = py / pl + trop.y + JITTER * gauss(rng);
      let dz = pz / pl + trop.z + JITTER * gauss(rng);
      const dl = Math.hypot(dx, dy, dz);
      if (dl < 1e-9) continue;
      dx /= dl; dy /= dl; dz /= dl;
      nodes.push(nodes[k * 3]! + dx * step, nodes[k * 3 + 1]! + dy * step, nodes[k * 3 + 2]! + dz * step);
      parents.push(k);
    }
    refresh(before);
    // Consume attractors the new nodes reached.
    for (let a = 0; a < m; a++) if (alive[a] && nearestD[a]! <= kill && nearest[a]! >= before) alive[a] = 0;
  }
  // Every chunk hangs on wood: a survivor that never won a node gets its own twig.
  for (let a = 0; a < m; a++) {
    if (!alive[a] || nearestD[a]! <= kill) continue;
    const before = n();
    bridge(nearest[a]!, pts[a * 3]!, pts[a * 3 + 1]!, pts[a * 3 + 2]!, kill);
    refresh(before);
  }
  return { nodes: Float32Array.from(nodes), parents: Int32Array.from(parents), n: n(), step };
}

/**
 * The leaf level never changes the skeleton, so growth is cached per book:
 * switching levels only re-places leaves.
 */
const skeletonCache = new Map<string, {
  crownInfo: { trunkHeight: number; crown: Float32Array; nCrown: number };
  attractors: Float32Array;
  grown: ReturnType<typeof colonize>;
}>();

/** colonize(max_attractors=3000): grow toward a seeded sample of the crown. */
function growSkeleton(slug: string, crown: Float32Array, nCrown: number, trop: Vec3) {
  const rng = mulberry32(seedFromKey(slug));
  const m = Math.min(nCrown, MAX_ATTRACTORS);
  let attractors = crown.subarray(0, m * 3);
  if (nCrown > MAX_ATTRACTORS) {
    const idx = Array.from({ length: nCrown }, (_, i) => i);
    for (let i = 0; i < m; i++) {
      const j = i + Math.floor(rng() * (nCrown - i));
      [idx[i], idx[j]] = [idx[j]!, idx[i]!];
    }
    attractors = new Float32Array(m * 3);
    for (let i = 0; i < m; i++) attractors.set(crown.subarray(idx[i]! * 3, idx[i]! * 3 + 3), i * 3);
  }
  return { attractors, grown: colonize(attractors, m, trop, rng) };
}

/**
 * Grow one book's tree: crown from its chunks, skeleton by space colonization,
 * pipe-model radii, and leaves for a fraction of the chunks (1 = every chunk).
 */
export function growTree(opts: {
  slug: string;
  genre: string;
  nChunks: number;
  tipRadius?: number;
  /** Fraction of the book's chunks that carry a leaf; the skeleton never changes with it. */
  leafScale?: number;
}): GrownTree {
  const { slug, genre, nChunks } = opts;
  const tipRadius = opts.tipRadius ?? TIP_RADIUS;
  const trop = tropismFor(genre);
  const cacheKey = `${slug}|${genre}|${nChunks}|${tipRadius}`;
  const cached = skeletonCache.get(cacheKey);
  const { trunkHeight, crown, nCrown } = cached?.crownInfo ?? placeCrown(nChunks, genre, slug);
  const { attractors, grown } = cached ?? growSkeleton(slug, crown, nCrown, trop);
  if (!cached) skeletonCache.set(cacheKey, { crownInfo: { trunkHeight, crown, nCrown }, attractors, grown });
  const { nodes, parents, n } = grown;


  const radii = new Float32Array(n);
  radii.fill(tipRadius);
  // Pipe model: walk children -> parent. Children have higher indices, so each
  // node's own radius is final before it is added to its parent.
  const childSum = new Float32Array(n);
  for (let i = n - 1; i >= 1; i--) {
    if (childSum[i]! > 0) radii[i] = childSum[i]! ** (1 / PIPE_EXP);
    const p = parents[i]!;
    if (p >= 0) childSum[p] += radii[i]! ** PIPE_EXP;
  }
  if (childSum[0]! > 0) radii[0] = childSum[0]! ** (1 / PIPE_EXP);
  // Tip count does not grow with the book, so tall trees came out spindly.
  // Thicken toward the floor in proportion to each segment's share of the
  // trunk, so the trunk reaches it and twigs stay nearly unchanged.
  const base = radii[0]!;
  const f = Math.max(TRUNK_PER_HEIGHT * trunkHeight, 0.18) / base;
  if (f > 1) for (let i = 0; i < n; i++) radii[i] = radii[i]! * (1 + (f - 1) * (radii[i]! / base));

  // Leaves. Like grow_tree_geometry, a leaf stands for a chunk at the chunk's
  // own crown position; the level keeps an even stride of them (1 = all). A
  // leaf is hung on the wood: its stalk on the line to the nearest node, at
  // most LEAF_REACH away, its blade pointing out along that line and lifted
  // toward the sky.
  const frac = Math.min(1, Math.max(0, opts.leafScale ?? 1));
  const kept: number[] = [];
  for (let l = 0; l < nCrown; l++) if (Math.floor((l + 1) * frac) > Math.floor(l * frac)) kept.push(l);
  if (!kept.length && nCrown) kept.push(0);
  const nLeaves = kept.length;
  const allLeaves = new Float32Array(nLeaves * 3);
  const leafDirs = new Float32Array(nLeaves * 3);
  const near = nearestNodeIndex(nodes, n, Math.max(grown.step, 0.25));
  kept.forEach((c, l) => {
    const cx = crown[c * 3]!, cy = crown[c * 3 + 1]!, cz = crown[c * 3 + 2]!;
    const k = near(cx, cy, cz);
    let vx = cx - nodes[k * 3]!, vy = cy - nodes[k * 3 + 1]!, vz = cz - nodes[k * 3 + 2]!;
    const d = Math.hypot(vx, vy, vz);
    const reach = Math.min(d, LEAF_REACH);
    if (d > 1e-6) { vx /= d; vy /= d; vz /= d; } else { vx = 0; vy = 1; vz = 0; }
    allLeaves[l * 3] = nodes[k * 3]! + vx * reach;
    allLeaves[l * 3 + 1] = nodes[k * 3 + 1]! + vy * reach;
    allLeaves[l * 3 + 2] = nodes[k * 3 + 2]! + vz * reach;
    const ox = vx, oy = vy + 0.55, oz = vz;
    const ol = Math.hypot(ox, oy, oz) || 1;
    leafDirs[l * 3] = ox / ol;
    leafDirs[l * 3 + 1] = oy / ol;
    leafDirs[l * 3 + 2] = oz / ol;
  });

  const tintRng = mulberry32(seedFromKey(slug + ":tint"));
  const leafTint = new Uint8Array(nLeaves);
  for (let i = 0; i < nLeaves; i++) leafTint[i] = Math.floor(tintRng() * 8);

  return {
    skeleton: { nodes, parents, radii, n },
    crown: attractors,
    leafPoints: allLeaves,
    leafDirs,
    nChunks,
    step: grown.step,
    leafTint,
    nLeaves,
    trunkHeight,
    trunkRadius: radii[0]!,
  };
}

export type BarkBuffers = { pos: number[]; normal: number[]; uv: number[]; index: number[] };

// World width one bark texture tile covers around a trunk.
const BARK_TILE = 0.9;

/**
 * Sweep the skeleton into continuous tapered tubes with bark UVs, after
 * ez-tree's branch sweep (github.com/dgreenheck/ez-tree, MIT): rings of
 * vertices per section, a duplicated seam vertex for UV continuity, quads
 * between rings. Each chain follows the thickest child; the other children
 * start new chains at the fork. Rings are parallel-transported so the bark
 * does not twist. `aspect` is the bark image's height / width. Returns the
 * number of vertices added.
 */
export function emitBark(grown: GrownTree, originX: number, originZ: number, out: BarkBuffers, aspect: number): number {
  const { nodes, parents, radii, n } = grown.skeleton;
  const children: number[][] = Array.from({ length: n }, () => []);
  for (let i = 1; i < n; i++) if (parents[i]! >= 0) children[parents[i]!]!.push(i);
  const mainChild = (i: number) => {
    let best = -1;
    for (const c of children[i]!) if (best < 0 || radii[c]! > radii[best]!) best = c;
    return best;
  };

  const chains: number[][] = [];
  const follow = (from: number[]) => {
    const chain = from;
    for (let c = mainChild(chain[chain.length - 1]!); c >= 0; c = mainChild(c)) chain.push(c);
    return chain;
  };
  const trunk = follow([0]);
  chains.push(trunk);
  for (let ci = 0; ci < chains.length; ci++) {
    const chain = chains[ci]!;
    // A side chain's first node is the fork, whose other children its parent chain already queued.
    for (let k = ci === 0 ? 0 : 1; k < chain.length; k++) {
      const p = chain[k]!;
      const main = chain[k + 1];
      for (const c of children[p]!) if (c !== main) chains.push(follow([p, c]));
    }
  }

  const base0 = out.pos.length / 3;
  const P = (i: number, a: number) => nodes[i * 3 + a]!;
  for (const chain of chains) {
    const m = chain.length;
    if (m < 2) continue;
    const isTrunk = chain === trunk;
    // A side chain's first ring sits at the fork with the child's own radius,
    // so it tucks inside the parent instead of bulging out of it.
    const ringRadius = (k: number) => {
      const r = k === 0 && !isTrunk ? radii[chain[1]!]! : radii[chain[k]!]!;
      return isTrunk && k === 0 ? r * 1.3 : r; // root flare
    };
    const r0 = ringRadius(isTrunk ? 1 : 0);
    const R = r0 >= 0.2 ? 12 : r0 >= 0.07 ? 7 : 5;
    const around = Math.max(1, Math.round((2 * Math.PI * r0) / BARK_TILE));
    const vScale = 1 / (aspect * ((2 * Math.PI * r0) / around)); // keep the tile's aspect
    const first = out.pos.length / 3;

    let nx = 0, ny = 0, nz = 0;
    let v = 0;
    for (let k = 0; k < m; k++) {
      const i = chain[k]!;
      const a = chain[Math.max(0, k - 1)]!;
      const b = chain[Math.min(m - 1, k + 1)]!;
      let tx = P(b, 0) - P(a, 0), ty = P(b, 1) - P(a, 1), tz = P(b, 2) - P(a, 2);
      const tl = Math.hypot(tx, ty, tz) || 1;
      tx /= tl; ty /= tl; tz /= tl;
      if (k === 0) {
        // Any vector perpendicular to the first tangent.
        if (Math.abs(ty) < 0.9) { nx = tz; ny = 0; nz = -tx; } else { nx = 0; ny = -tz; nz = ty; }
      } else {
        v += Math.hypot(P(i, 0) - P(chain[k - 1]!, 0), P(i, 1) - P(chain[k - 1]!, 1), P(i, 2) - P(chain[k - 1]!, 2)) * vScale;
      }
      // Parallel transport: drop the tangent component of the previous normal.
      const d = nx * tx + ny * ty + nz * tz;
      nx -= d * tx; ny -= d * ty; nz -= d * tz;
      const nl = Math.hypot(nx, ny, nz) || 1;
      nx /= nl; ny /= nl; nz /= nl;
      const bx = ty * nz - tz * ny, by = tz * nx - tx * nz, bz = tx * ny - ty * nx;
      const r = ringRadius(k);
      const y = isTrunk && k === 0 ? -0.15 : P(i, 1); // sink the root below the ground
      for (let j = 0; j <= R; j++) {
        const ang = (2 * Math.PI * j) / R;
        const c = Math.cos(ang), s = Math.sin(ang);
        const dx = c * nx + s * bx, dy = c * ny + s * by, dz = c * nz + s * bz;
        out.pos.push(originX + P(i, 0) + dx * r, y + dy * r, originZ + P(i, 2) + dz * r);
        out.normal.push(dx, dy, dz);
        out.uv.push((j / R) * around, v);
      }
    }
    const N = R + 1;
    for (let k = 0; k < m - 1; k++) {
      for (let j = 0; j < R; j++) {
        const a = first + k * N + j, b = a + 1, c = a + N, d = c + 1;
        out.index.push(a, b, c, b, d, c);
      }
    }
  }
  return out.pos.length / 3 - base0;
}

/**
 * Instance each leaf with its stalk (the shape's y = -1 end) on the twig and
 * its blade along leafDirs, rolled so the face turns to the sky.
 */
export function emitLeaves(
  grown: GrownTree,
  originX: number,
  originZ: number,
  destPos: number[],
  destScale: number[],
  destTint: number[],
  destQuat: number[],
  leafSize: number,
): number {
  // grow_tree_geometry: a dense crown tiled at full size is an opaque shell, so
  // leaves shrink with the book's chunk count beyond LEAF_REFERENCE_COUNT.
  const r = leafSize * Math.min(1, (LEAF_REFERENCE_COUNT / Math.max(grown.nChunks, 1)) ** (1 / 3));
  let count = 0;
  for (let i = 0; i < grown.nLeaves; i++) {
    const jitter = 0.78 + (grown.leafTint[i]! / 8) * 0.5;
    const sx = r * 1.12 * jitter, sy = r * 1.78 * jitter;
    // Leaf frame: y along the blade, z the face normal as close to world up as y allows.
    const yx = grown.leafDirs[i * 3]!, yy = grown.leafDirs[i * 3 + 1]!, yz = grown.leafDirs[i * 3 + 2]!;
    let zx = -yy * yx, zy = 1 - yy * yy, zz = -yy * yz;
    const zl = Math.hypot(zx, zy, zz);
    if (zl < 1e-4) { zx = 1; zy = 0; zz = 0; } else { zx /= zl; zy /= zl; zz /= zl; }
    const xx = yy * zz - yz * zy, xy = yz * zx - yx * zz, xz = yx * zy - yy * zx;
    quatFromBasis(xx, xy, xz, yx, yy, yz, zx, zy, zz, destQuat);
    destPos.push(
      originX + grown.leafPoints[i * 3]! + yx * sy,
      grown.leafPoints[i * 3 + 1]! + yy * sy,
      originZ + grown.leafPoints[i * 3 + 2]! + yz * sy,
    );
    destScale.push(sx, sy, r * 0.22);
    destTint.push(grown.leafTint[i]!);
    count++;
  }
  return count;
}

/** Quaternion (x, y, z, w) of the rotation whose columns are the given basis. */
function quatFromBasis(
  m00: number, m10: number, m20: number,
  m01: number, m11: number, m21: number,
  m02: number, m12: number, m22: number,
  out: number[],
) {
  const tr = m00 + m11 + m22;
  let x, y, z, w;
  if (tr > 0) {
    const s = 0.5 / Math.sqrt(tr + 1);
    w = 0.25 / s; x = (m21 - m12) * s; y = (m02 - m20) * s; z = (m10 - m01) * s;
  } else if (m00 > m11 && m00 > m22) {
    const s = 2 * Math.sqrt(1 + m00 - m11 - m22);
    w = (m21 - m12) / s; x = 0.25 * s; y = (m01 + m10) / s; z = (m02 + m20) / s;
  } else if (m11 > m22) {
    const s = 2 * Math.sqrt(1 + m11 - m00 - m22);
    w = (m02 - m20) / s; x = (m01 + m10) / s; y = 0.25 * s; z = (m12 + m21) / s;
  } else {
    const s = 2 * Math.sqrt(1 + m22 - m00 - m11);
    w = (m10 - m01) / s; x = (m02 + m20) / s; y = (m12 + m21) / s; z = 0.25 * s;
  }
  out.push(x, y, z, w);
}

export { clamp };
