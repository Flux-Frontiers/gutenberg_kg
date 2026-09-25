import { emitBark, type BarkBuffers } from "./growTree";
import { mulberry32, seedFromKey } from "./math";

/**
 * The corpus redwood at the hub: one tree for the whole library.
 *
 * - Height is the book-tree rule (1.7 * log2(1 + chunks)) applied to the
 *   corpus's total chunk count, doubled and uncapped.
 * - One limb per book, stacked by chunk count (biggest book lowest), each
 *   reaching out toward that book's own tree in the forest. A limb's reach and
 *   base radius come from its book tree's height and trunk radius.
 * - The trunk follows the pipe model, as every book tree does: its
 *   cross-section at any height is the sum of the limbs' above it.
 */

/** Twice the book trees' 1.7 m per doubling of chunks. */
export const REDWOOD_HEIGHT_PER_LOG2 = 3.4;
/** A limb's base radius as a fraction of its book tree's trunk radius. */
const LIMB_SCALE = 0.3;
/** The lowest limb, as a fraction of height; redwoods keep a long clear bole. */
const CROWN_BASE = 0.3;
const CROWN_TOP = 0.95;
/** Radius of the leader above the top limb. */
const LEADER_R = 0.22;
const TRUNK_STEP = 0.75;
/** Horizontal reach of the lowest and highest limbs, before the book's own factor. */
const REACH_MAX = 13;
const REACH_MIN = 1.8;
/** Book trees are capped at this height (growTree.placeCrown). */
const BOOK_TREE_CAP = 22;

export type LimbSource = {
  book: { slug: string; chunks: number };
  x: number;
  z: number;
  height: number;
  trunkRadius: number;
};

export type CorpusTree = {
  height: number;
  totalChunks: number;
  limbs: number;
  /** Trunk radius at the ground, above the root flare. */
  trunkRadius: number;
  /** Outer radius of the root flare: the cart cannot drive inside it. */
  baseRadius: number;
  bark: { count: number; pos: Float32Array; normal: Float32Array; uv: Float32Array; index: Uint32Array };
  /**
   * Foliage sprays: flat needle cards lying along the limbs. Position, scale
   * (x along the spray, z across it), quaternion (x, y, z, w), shade 0-7.
   */
  foliage: { count: number; pos: Float32Array; scale: Float32Array; quat: Float32Array; shade: Uint8Array };
};

export function growCorpusTree(sources: LimbSource[], barkAspect: number): CorpusTree {
  const rng = mulberry32(seedFromKey("corpus-redwood"));
  const totalChunks = sources.reduce((s, t) => s + t.book.chunks, 0);
  const height = REDWOOD_HEIGHT_PER_LOG2 * Math.log2(1 + totalChunks);
  const limbs = [...sources].sort((a, b) => b.book.chunks - a.book.chunks || a.book.slug.localeCompare(b.book.slug));
  const n = limbs.length;

  // Trunk nodes 0..K up the axis; each limb forks from the node at or below its height.
  const K = Math.ceil(height / TRUNK_STEP);
  const nodeY = (k: number) => Math.min(height, k * TRUNK_STEP);
  const attach = limbs.map((_, i) => {
    const t = n > 1 ? i / (n - 1) : 0.5;
    return Math.min(K - 1, Math.floor((height * (CROWN_BASE + (CROWN_TOP - CROWN_BASE) * t)) / TRUNK_STEP));
  });
  const limbR = limbs.map((t) => LIMB_SCALE * t.trunkRadius);
  // Pipe model down the trunk: r_k^2 = leader^2 + sum of limb r^2 forking at or above k.
  const above = new Float64Array(K + 2);
  attach.forEach((k, i) => { above[k] += limbR[i]! ** 2; });
  for (let k = K; k >= 0; k--) above[k] += above[k + 1]!;
  const trunkRadius = Math.sqrt(LEADER_R ** 2 + above[0]!);

  const nodes: number[] = [];
  const parents: number[] = [];
  const radii: number[] = [];
  const push = (x: number, y: number, z: number, parent: number, r: number) => {
    nodes.push(x, y, z);
    parents.push(parent);
    radii.push(r);
    return parents.length - 1;
  };
  for (let k = 0; k <= K; k++) {
    const y = nodeY(k);
    let r = Math.sqrt(LEADER_R ** 2 + above[k]!);
    // The leader tapers to a point above the top limb.
    if (y > height * CROWN_TOP) r *= Math.max(0.15, (height - y) / (height * (1 - CROWN_TOP)));
    // Buttressed root flare over the first few metres.
    r *= 1 + 0.15 * Math.exp(-y / 1.5);
    push(0, y, 0, k - 1, r);
  }
  // emitBark widens the trunk's first ring by 1.3 for its own flare.
  const baseRadius = radii[0]! * 1.3;

  const fPos: number[] = [];
  const fScale: number[] = [];
  const fQuat: number[] = [];
  const fShade: number[] = [];
  // A redwood spray is flat: three cards fanned out from each point, drooping.
  const spray = (x: number, y: number, z: number, azimuth: number, droop: number, s: number) => {
    for (const fan of [-0.55, 0, 0.55]) {
      // Yaw so local +x runs along the spray, then tip it down by `droop`.
      const hy = -(azimuth + fan + (rng() - 0.5) * 0.3) / 2, hz = -(droop + Math.abs(fan) * 0.3) / 2;
      const sy = Math.sin(hy), cy = Math.cos(hy), sz = Math.sin(hz), cz = Math.cos(hz);
      const len = 2.2 * s * (fan ? 0.8 : 1);
      // The card's centre sits half its length out, so its base meets the limb.
      const ca = Math.cos(azimuth + fan), sa = Math.sin(azimuth + fan);
      fPos.push(x + ca * len * 0.4, y - Math.sin(droop) * len * 0.4, z + sa * len * 0.4);
      fScale.push(len, 1, 0.9 * s);
      fQuat.push(sy * sz, sy * cz, cy * sz, cy * cz);
      fShade.push(Math.floor(rng() * 8));
    }
  };

  limbs.forEach((t, i) => {
    const k = attach[i]!;
    const u0 = n > 1 ? i / (n - 1) : 0.5;
    const y0 = nodeY(k);
    const azimuth = Math.atan2(t.z, t.x) + (rng() - 0.5) * 0.3;
    const ax = Math.cos(azimuth), az = Math.sin(azimuth);
    const book = 0.55 + 0.45 * Math.min(1, t.height / BOOK_TREE_CAP);
    const reach = (REACH_MIN + (REACH_MAX - REACH_MIN) * (1 - u0) ** 1.1) * book;
    const surface = radii[k]!;
    const m = Math.max(3, Math.ceil(reach / 1.2));
    // Out from the trunk, sagging mid-limb and turning up at the tip.
    const at = (u: number) => {
      const h = surface + reach * u;
      return [ax * h, y0 + reach * (-0.05 * u - 0.18 * u * u + 0.2 * u * u * u), az * h] as const;
    };
    let prev = k;
    for (let j = 1; j <= m; j++) {
      const u = j / m;
      const [x, y, z] = at(u);
      prev = push(x, y, z, prev, limbR[i]! * (1 - 0.8 * u));
    }
    // Sprays along the outer two-thirds, a few set off to either side to fill the crown.
    const count = Math.max(2, Math.round(reach * 0.6));
    const size = 0.7 + 0.5 * Math.min(1, reach / REACH_MAX);
    for (let c = 0; c < count; c++) {
      const u = 0.35 + (0.65 * (c + 0.5)) / count;
      const [x, y, z] = at(u);
      const side = (rng() - 0.5) * 1.4 * size;
      spray(x - az * side, y + 0.1, z + ax * side, azimuth + (rng() - 0.5) * 0.5, 0.15 + rng() * 0.2, size * (0.85 + rng() * 0.3));
    }
  });
  // A narrow spire of sprays around the leader.
  for (let c = 0; c < 10; c++) {
    const f = c / 9;
    const y = height * (CROWN_TOP - 0.05 + 0.09 * f);
    const a = c * 2.39996;
    const r = 0.9 * (1 - f) + 0.15;
    spray(Math.cos(a) * r, y, Math.sin(a) * r, a, -0.5 - 0.4 * f, 0.8 - 0.4 * f);
  }

  const bark: BarkBuffers = { pos: [], normal: [], uv: [], index: [] };
  const count = emitBark(
    { skeleton: { nodes: Float32Array.from(nodes), parents: Int32Array.from(parents), radii: Float32Array.from(radii), n: parents.length } },
    0, 0, bark, barkAspect,
  );
  return {
    height,
    totalChunks,
    limbs: n,
    trunkRadius,
    baseRadius,
    bark: {
      count,
      pos: new Float32Array(bark.pos),
      normal: new Float32Array(bark.normal),
      uv: new Float32Array(bark.uv),
      index: new Uint32Array(bark.index),
    },
    foliage: {
      count: fShade.length,
      pos: new Float32Array(fPos),
      scale: new Float32Array(fScale),
      quat: new Float32Array(fQuat),
      shade: Uint8Array.from(fShade),
    },
  };
}
