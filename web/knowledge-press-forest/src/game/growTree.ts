import { clamp, mulberry32, quatFromYToDir, seedFromKey } from "./math";

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
export const GROW_VERSION = 2;

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

  const maxNodes = Math.min(128, Math.round(48 + nAttract * 1.45));
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
  const maxIter = Math.min(60, 32 + nAttract);

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
  // Pipe model: walk children → parent. radius^2 parent = sum radius^2 children.
  const childSum = new Float32Array(n);
  for (let i = n - 1; i >= 1; i--) {
    const p = parents[i]!;
    if (p < 0) continue;
    childSum[p] += radii[i]! * radii[i]!;
    if (childSum[i]! > 0) {
      radii[i] = Math.sqrt(childSum[i]!);
    }
  }
  if (childSum[0]! > 0) radii[0] = Math.sqrt(childSum[0]!);
  radii[0] = Math.max(radii[0]!, 0.18);

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

export function emitWood(
  grown: GrownTree,
  originX: number,
  originZ: number,
  destPos: number[],
  destQuat: number[],
  destScale: number[],
): number {
  const { nodes, parents, radii, n } = grown.skeleton;
  let count = 0;
  const q: number[] = [0, 0, 0, 1];
  for (let i = 1; i < n; i++) {
    const p = parents[i]!;
    if (p < 0) continue;
    const ax = nodes[p * 3]!;
    const ay = nodes[p * 3 + 1]!;
    const az = nodes[p * 3 + 2]!;
    const bx = nodes[i * 3]!;
    const by = nodes[i * 3 + 1]!;
    const bz = nodes[i * 3 + 2]!;
    const dx = bx - ax;
    const dy = by - ay;
    const dz = bz - az;
    const len = Math.hypot(dx, dy, dz);
    if (len < 0.04) continue;
    const r = Math.max(0.028, (radii[i]! + radii[p]!) * 0.5);
    quatFromYToDir(dx, dy, dz, q);
    destPos.push(originX + (ax + bx) * 0.5, (ay + by) * 0.5, originZ + (az + bz) * 0.5);
    destQuat.push(q[0]!, q[1]!, q[2]!, q[3]!);
    destScale.push(r, len, r);
    count++;
  }
  return count;
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
    destScale.push(r, r * 0.55, r);
    destTint.push(grown.leafTint[i]!);
    count++;
  }
  return count;
}

export { clamp };
