import { clamp, mulberry32, seedFromKey } from "./math";

export type Vec3 = { x: number; y: number; z: number };

export type Skeleton = {
  nodes: Float32Array;
  parents: Int16Array;
  radii: Float32Array;
  n: number;
};

export type GrownTree = {
  skeleton: Skeleton;
  crown: Float32Array;
  leafPoints: Float32Array;
  leafTint: Uint8Array;
  nLeaves: number;
  trunkHeight: number;
  trunkRadius: number;
};

/** Bump when caps change so the forest cache rebuilds. */
export const GROW_VERSION = 8;

// Pipe-model exponent: parent^e = sum child^e (Leonardo's rule). Lower values
// balloon the trunk once skeletons reach the 256-node cap; thickness for tall
// trees comes from TRUNK_PER_HEIGHT instead.
const PIPE_EXP = 2;
// Trunk radius floor as a fraction of height (real trees run about 1:30-1:40).
const TRUNK_PER_HEIGHT = 0.028;
// Farthest a leaf may sit from a branch node; leaves beyond it are pulled in.
const LEAF_REACH = 0.6;

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

/** Place section tips and chunk attractors the way ForestLayout does. */
export function placeCrown(
  nChunks: number,
  genre: string,
  slug: string,
): { attractors: Float32Array; nAttract: number; trunkHeight: number; allLeaves: Float32Array; nLeaves: number } {
  const rng = mulberry32(seedFromKey(slug + ":crown"));
  const trunkHeight = Math.min(1.7 * Math.max(1, Math.log2(1 + nChunks)), 22);
  const nSections = Math.max(5, Math.round(Math.sqrt(nChunks) * 1.25));
  const branchLength = 2.1 + Math.sqrt(nSections) * 0.55;
  const nLeaf = Math.min(nChunks, 140, Math.round(48 + Math.sqrt(nChunks) * 6));
  const nAttract = Math.min(nChunks, 56, Math.round(24 + Math.sqrt(nChunks) * 3.2));

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
  const nLeaves = li;

  const attractors = new Float32Array(nAttract * 3);
  if (nLeaves <= nAttract) {
    attractors.set(leaves.subarray(0, nLeaves * 3));
  } else {
    for (let i = 0; i < nAttract; i++) {
      const src = Math.floor((i * nLeaves) / nAttract);
      attractors[i * 3] = leaves[src * 3]!;
      attractors[i * 3 + 1] = leaves[src * 3 + 1]!;
      attractors[i * 3 + 2] = leaves[src * 3 + 2]!;
    }
  }

  void genre;
  return {
    attractors,
    nAttract: Math.min(nAttract, nLeaves),
    trunkHeight,
    allLeaves: leaves,
    nLeaves,
  };
}

/**
 * Space colonization (Runions, Lane & Prusinkiewicz 2007) + pipe-model radii.
 * Attractors are the book's chunks; every limb is a path through the graph.
 */
export function growTree(opts: {
  slug: string;
  genre: string;
  nChunks: number;
  tipRadius?: number;
}): GrownTree {
  const { slug, genre, nChunks } = opts;
  const tipRadius = opts.tipRadius ?? 0.045;
  const trop = tropismFor(genre);
  const { attractors, nAttract, trunkHeight, allLeaves, nLeaves } = placeCrown(
    nChunks,
    genre,
    slug,
  );

  // At 128, 251 of 253 trees hit the cap before reaching their crowns.
  const maxNodes = Math.min(256, Math.round(48 + nAttract * 6.5));
  const nodes = new Float32Array(maxNodes * 3);
  const parents = new Int16Array(maxNodes);
  parents.fill(-1);
  let n = 0;

  const push = (x: number, y: number, z: number, parent: number) => {
    if (n >= maxNodes) return -1;
    const i = n++;
    nodes[i * 3] = x;
    nodes[i * 3 + 1] = y;
    nodes[i * 3 + 2] = z;
    parents[i] = parent;
    return i;
  };

  push(0, 0, 0, -1);
  const trunkSteps = 6;
  for (let i = 1; i <= trunkSteps; i++) {
    push(0, (trunkHeight * 0.28 * i) / trunkSteps, 0, i - 1);
  }

  const influence = 5.8 + trunkHeight * 0.12;
  const kill = 0.58;
  const step = 0.34 + Math.min(trunkHeight, 16) * 0.016;
  const alive = new Uint8Array(nAttract);
  alive.fill(1);
  const dirX = new Float32Array(maxNodes);
  const dirY = new Float32Array(maxNodes);
  const dirZ = new Float32Array(maxNodes);
  const votes = new Uint16Array(maxNodes);
  const maxIter = Math.min(90, 32 + nAttract * 2);

  for (let iter = 0; iter < maxIter && n < maxNodes - 1; iter++) {
    dirX.fill(0);
    dirY.fill(0);
    dirZ.fill(0);
    votes.fill(0);
    let grew = false;

    for (let a = 0; a < nAttract; a++) {
      if (!alive[a]) continue;
      const ax = attractors[a * 3]!;
      const ay = attractors[a * 3 + 1]!;
      const az = attractors[a * 3 + 2]!;
      let best = -1;
      let bestD = influence;
      for (let i = 0; i < n; i++) {
        const dx = ax - nodes[i * 3]!;
        const dy = ay - nodes[i * 3 + 1]!;
        const dz = az - nodes[i * 3 + 2]!;
        const d = Math.hypot(dx, dy, dz);
        if (d < kill) {
          alive[a] = 0;
          best = -1;
          break;
        }
        if (d < bestD) {
          bestD = d;
          best = i;
        }
      }
      if (best < 0 || !alive[a]) continue;
      const dx = ax - nodes[best * 3]!;
      const dy = ay - nodes[best * 3 + 1]!;
      const dz = az - nodes[best * 3 + 2]!;
      const d = Math.hypot(dx, dy, dz) || 1;
      dirX[best] += dx / d;
      dirY[best] += dy / d;
      dirZ[best] += dz / d;
      votes[best]++;
    }

    const snapshot = n;
    for (let i = 0; i < snapshot && n < maxNodes; i++) {
      if (!votes[i]) continue;
      let dx = dirX[i]! + trop.x;
      let dy = dirY[i]! + trop.y;
      let dz = dirZ[i]! + trop.z;
      const len = Math.hypot(dx, dy, dz) || 1;
      dx = (dx / len) * step;
      dy = (dy / len) * step;
      dz = (dz / len) * step;
      const nx = nodes[i * 3]! + dx;
      const ny = Math.max(0.05, nodes[i * 3 + 1]! + dy);
      const nz = nodes[i * 3 + 2]! + dz;
      push(nx, ny, nz, i);
      grew = true;
    }
    if (!grew) break;
  }

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

  // Only some leaves are attractors, so branches miss the rest; hang every
  // leaf within reach of its nearest limb (the bare lower trunk excluded).
  for (let l = 0; l < nLeaves; l++) {
    const lx = allLeaves[l * 3]!;
    const ly = allLeaves[l * 3 + 1]!;
    const lz = allLeaves[l * 3 + 2]!;
    let best = -1;
    let bestD = Infinity;
    for (let i = trunkSteps; i < n; i++) {
      const d = Math.hypot(lx - nodes[i * 3]!, ly - nodes[i * 3 + 1]!, lz - nodes[i * 3 + 2]!);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    if (best < 0 || bestD <= LEAF_REACH) continue;
    const k = LEAF_REACH / bestD;
    allLeaves[l * 3] = nodes[best * 3]! + (lx - nodes[best * 3]!) * k;
    allLeaves[l * 3 + 1] = nodes[best * 3 + 1]! + (ly - nodes[best * 3 + 1]!) * k;
    allLeaves[l * 3 + 2] = nodes[best * 3 + 2]! + (lz - nodes[best * 3 + 2]!) * k;
  }

  const rng = mulberry32(seedFromKey(slug + ":tint"));
  const leafTint = new Uint8Array(nLeaves);
  for (let i = 0; i < nLeaves; i++) leafTint[i] = Math.floor(rng() * 8);

  return {
    skeleton: { nodes, parents, radii, n },
    crown: attractors,
    leafPoints: allLeaves,
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

export function emitLeaves(
  grown: GrownTree,
  originX: number,
  originZ: number,
  destPos: number[],
  destScale: number[],
  destTint: number[],
  leafSize: number,
): number {
  const scale = Math.min(1, (600 / Math.max(grown.nLeaves, 8)) ** (1 / 3));
  const r = leafSize * scale;
  let count = 0;
  for (let i = 0; i < grown.nLeaves; i++) {
    destPos.push(
      originX + grown.leafPoints[i * 3]!,
      grown.leafPoints[i * 3 + 1]!,
      originZ + grown.leafPoints[i * 3 + 2]!,
    );
    const jitter = 0.78 + (grown.leafTint[i]! / 8) * 0.5;
    destScale.push(r * 1.12 * jitter, r * 1.78 * jitter, r * 0.22);
    destTint.push(grown.leafTint[i]!);
    count++;
  }
  return count;
}

export { clamp };
