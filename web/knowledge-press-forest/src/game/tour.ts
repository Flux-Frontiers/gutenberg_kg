import type { Forest } from "./forest";
import { clamp } from "./math";
import { wrapAngle, yawToward } from "./sim";

/**
 * The guided tour as a route along the roads: from wherever the cart is, down
 * the nearest spoke onto the ring (unless the ring is nearer), then around the
 * ring forever. The cart follows it by pure pursuit: it steers for the route
 * point LOOKAHEAD metres past the one it has reached, so it keeps to the brick
 * instead of cutting across the grass toward a point somewhere ahead.
 */
export type Tour = {
  pts: [number, number][];
  /** The grove each point is heading for, for signposts and the atlas. */
  genre: string[];
  /** Points from here on are the ring, which repeats. */
  loopStart: number;
  /** Progress: the route point the cart has reached. */
  i: number;
};

/** How many points ahead progress may jump in one step (samples are ~2 m apart). */
const SEARCH = 6;
const CRUISE = 0.42;

/** The route shared by the cart (Player) and the lanterns that light it (World). */
export const tourState: { tour: Tour | null } = { tour: null };

export function planTour(forest: Pick<Forest, "ringPath" | "roadLines" | "circuit">, x: number, z: number, yaw: number): Tour {
  const ring = forest.ringPath;
  const nearestRing = (px: number, pz: number) => {
    let k = 0, best = Infinity;
    ring.forEach((p, i) => {
      const d = Math.hypot(p.x - px, p.z - pz);
      if (d < best) { best = d; k = i; }
    });
    return { k, d: best };
  };
  let spoke: [number, number][] | null = null, ks = 0, ds = Infinity;
  for (const line of forest.roadLines) {
    if (line.kind !== "spoke") continue;
    line.pts.forEach(([px, pz], k) => {
      const d = Math.hypot(px - x, pz - z);
      if (d < ds) { ds = d; ks = k; spoke = line.pts; }
    });
  }
  const pts: [number, number][] = [];
  const onRing = nearestRing(x, z);
  let join = onRing.k;
  // The heading the cart will arrive at the ring with.
  let hx = -Math.sin(yaw), hz = -Math.cos(yaw);
  // Spokes run from the hub out to their ring stop; ride one out if it is clearly nearer.
  const s = spoke as [number, number][] | null;
  if (s && ds + 2 < onRing.d) {
    for (let k = ks; k < s.length; k++) pts.push(s[k]!);
    const [ex, ez] = s[s.length - 1]!;
    const [px, pz] = s[Math.max(0, s.length - 2)]!;
    join = nearestRing(ex, ez).k;
    hx = ex - px; hz = ez - pz;
  }
  // Go round whichever way carries straight on from that heading.
  const n = ring.length;
  const fwd = ring[(join + 1) % n]!, back = ring[(join - 1 + n) % n]!, at = ring[join]!;
  const dir = (fwd.x - at.x) * hx + (fwd.z - at.z) * hz >= (back.x - at.x) * hx + (back.z - at.z) * hz ? 1 : -1;
  const loopStart = pts.length;
  for (let k = 0; k < n; k++) {
    const p = ring[(join + dir * k + n * n) % n]!;
    pts.push([p.x, p.z]);
  }
  // Each point heads for the next grove stop the route reaches.
  const stopAt = new Map<number, string>();
  for (const wp of forest.circuit) {
    let k = loopStart, best = Infinity;
    for (let i = loopStart; i < pts.length; i++) {
      const d = Math.hypot(pts[i]![0] - wp.x, pts[i]![1] - wp.z);
      if (d < best) { best = d; k = i; }
    }
    stopAt.set(k, wp.genre);
  }
  const genre: string[] = new Array(pts.length);
  let upcoming = "";
  for (let pass = 0; pass < 2; pass++) {
    for (let i = pts.length - 1; i >= loopStart; i--) {
      upcoming = stopAt.get(i) ?? upcoming;
      genre[i] = upcoming;
    }
  }
  for (let i = loopStart - 1; i >= 0; i--) genre[i] = genre[loopStart]!;
  return { pts, genre, loopStart, i: 0 };
}

function next(t: Tour, i: number): number {
  return i + 1 < t.pts.length ? i + 1 : t.loopStart;
}

/** The point `dist` metres along the route past point `i`. */
function along(t: Tour, i: number, dist: number): number {
  let j = i, acc = 0;
  for (let guard = 0; acc < dist && guard < t.pts.length; guard++) {
    const n = next(t, j);
    acc += Math.hypot(t.pts[n]![0] - t.pts[j]![0], t.pts[n]![1] - t.pts[j]![1]);
    j = n;
  }
  return j;
}

/** The largest change of heading along the route in the next `dist` metres, in radians. */
function turnAhead(t: Tour, i: number, dist: number): number {
  const heading = (j: number) => {
    const n = next(t, j);
    return Math.atan2(t.pts[n]![1] - t.pts[j]![1], t.pts[n]![0] - t.pts[j]![0]);
  };
  const h0 = heading(i);
  let worst = 0, j = i, acc = 0;
  for (let guard = 0; acc < dist && guard < t.pts.length; guard++) {
    const n = next(t, j);
    acc += Math.hypot(t.pts[n]![0] - t.pts[j]![0], t.pts[n]![1] - t.pts[j]![1]);
    j = n;
    worst = Math.max(worst, Math.abs(wrapAngle(heading(j) - h0)));
  }
  return worst;
}

/** Advance progress and return the controls that hold the cart to the route. */
export function steerTour(t: Tour, x: number, z: number, yaw: number, speed: number): { steer: number; throttle: number; genre: string } {
  let best = t.i, bestD = Math.hypot(t.pts[t.i]![0] - x, t.pts[t.i]![1] - z);
  for (let k = 1, j = t.i; k <= SEARCH; k++) {
    j = next(t, j);
    const d = Math.hypot(t.pts[j]![0] - x, t.pts[j]![1] - z);
    if (d < bestD) { bestD = d; best = j; }
  }
  t.i = best;
  // Distance off the route: to the segments either side of the point reached.
  const seg = (a: number, b: number) => {
    const [ax, az] = t.pts[a]!, [bx, bz] = t.pts[b]!;
    const dx = bx - ax, dz = bz - az;
    const u = clamp(((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz || 1), 0, 1);
    return Math.hypot(x - ax - dx * u, z - az - dz * u);
  };
  const off = Math.min(seg(t.i, next(t, t.i)), t.i > 0 ? seg(t.i - 1, t.i) : Infinity);
  // Look further ahead the faster the cart goes: tight at a crawl, smooth at speed.
  const [tx, tz] = t.pts[along(t, t.i, clamp(2.5 + 0.8 * Math.abs(speed), 3, 6))]!;
  const err = wrapAngle(yawToward(x, z, tx, tz) - yaw);
  // Slow for the bends ahead (the ring doubles back at some grove stops):
  // coast when over the bend's speed, so drag brakes the cart before the turn.
  const bend = Math.max(turnAhead(t, t.i, 10), Math.abs(err));
  // Off the centreline (coming out of a turn), hold back until it is regained.
  const limit = (1.2 + 3 * Math.max(0, 1 - bend / 1.9)) * Math.max(0.45, 1 - Math.max(0, off - 0.5) / 2);
  return {
    steer: clamp(err * 1.8, -1, 1),
    throttle: speed > limit ? 0 : CRUISE,
    genre: t.genre[t.i]!,
  };
}

/** `n` points along the route ahead of the cart, `spacing` metres apart, for the lantern trail. */
export function tourAhead(t: Tour, n: number, spacing: number): [number, number][] {
  const out: [number, number][] = [];
  let j = t.i;
  for (let k = 0; k < n; k++) {
    j = along(t, j, spacing);
    out.push(t.pts[j]!);
  }
  return out;
}
