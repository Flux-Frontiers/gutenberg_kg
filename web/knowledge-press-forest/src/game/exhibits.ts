import type { RoadLine } from "./forest";

/**
 * Exhibits: set pieces that stand in roadside glades around the forest, each on
 * its own paved plaza that meets the road, with a plaque between the road and
 * the piece. Placement is deterministic: every exhibit takes the most open
 * glade along the roads that is far enough from the hub and from the others.
 */

export type ExhibitSpec = {
  id: string;
  label: string;
  /** Radius the cart cannot enter (the piece's plinth). */
  obstacle: number;
  /** Clear ground needed from any trunk, crowns included. */
  treeClearance: number;
};

export type Exhibit = ExhibitSpec & {
  x: number;
  z: number;
  /** The paved plaza's radius; its edge reaches over the road it stands beside. */
  plazaR: number;
  /** Nearest point on the road: the plaque faces it and a jump lands on it. */
  roadX: number;
  roadZ: number;
};

export const EXHIBITS: ExhibitSpec[] = [
  { id: "mysterium", label: "Mysterium Cosmographicum", obstacle: 2.6, treeClearance: 10 },
];

/** Keep exhibits out from under the redwood's crown and apart from one another. */
const MIN_HUB_DIST = 30;
const MIN_SPACING = 45;
// Road centreline clearance: half the widest road (1.7 m) + the cart (1.05 m).
const ROAD_CLEARANCE = 2.75;

function segDist(x: number, z: number, ax: number, az: number, bx: number, bz: number) {
  const dx = bx - ax, dz = bz - az;
  const t = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz || 1)));
  return Math.hypot(x - ax - dx * t, z - az - dz * t);
}

export function placeExhibits(opts: {
  specs: ExhibitSpec[];
  roadLines: RoadLine[];
  trees: { x: number; z: number; trunkRadius: number }[];
  worldRadius: number;
}): Exhibit[] {
  const { roadLines, trees, worldRadius } = opts;
  const segs: [number, number, number, number][] = [];
  for (const line of roadLines) {
    const n = line.pts.length;
    for (let i = 0; i < (line.closed ? n : n - 1); i++) {
      const [ax, az] = line.pts[i]!;
      const [bx, bz] = line.pts[(i + 1) % n]!;
      segs.push([ax, az, bx, bz]);
    }
  }
  const placed: Exhibit[] = [];
  for (const spec of opts.specs) {
    const standOff = spec.obstacle + ROAD_CLEARANCE + 1;
    let best: Exhibit | null = null;
    let bestScore = -Infinity;
    for (const [ax, az, bx, bz] of segs) {
      const len = Math.hypot(bx - ax, bz - az);
      if (len < 1e-6) continue;
      const nx = -(bz - az) / len, nz = (bx - ax) / len;
      for (let s = 0; s <= len; s += 2) {
        const px = ax + ((bx - ax) * s) / len, pz = az + ((bz - az) * s) / len;
        for (const side of [-1, 1]) {
          for (let d = standOff; d <= standOff + 2; d += 0.5) {
            const x = px + nx * side * d, z = pz + nz * side * d;
            const hub = Math.hypot(x, z);
            if (hub < MIN_HUB_DIST || hub > worldRadius - 12) continue;
            if (placed.some((e) => Math.hypot(e.x - x, e.z - z) < MIN_SPACING)) continue;
            // This road must be the nearest one, and no road may clip the plinth.
            if (segs.some((g) => segDist(x, z, ...g) < d - 0.01)) continue;
            let clear = Infinity;
            for (const t of trees) clear = Math.min(clear, Math.hypot(t.x - x, t.z - z) - t.trunkRadius);
            if (clear < spec.treeClearance) continue;
            // The most open glade wins; nearer the hub breaks ties.
            const score = Math.min(clear, spec.treeClearance + 8) - hub * 0.01;
            if (score > bestScore) {
              bestScore = score;
              best = { ...spec, x, z, plazaR: d - 0.4, roadX: px, roadZ: pz };
            }
          }
        }
      }
    }
    if (best) placed.push(best);
  }
  return placed;
}

/** Stand on the road beside the exhibit, facing it (yaw convention of sim.yawToward). */
export function exhibitApproach(e: Exhibit): { x: number; z: number; yaw: number } {
  const dx = e.roadX - e.x, dz = e.roadZ - e.z;
  const d = Math.hypot(dx, dz) || 1;
  const x = e.x + (dx / d) * (d + 3);
  const z = e.z + (dz / d) * (d + 3);
  return { x, z, yaw: Math.atan2(-(e.x - x), -(e.z - z)) };
}
