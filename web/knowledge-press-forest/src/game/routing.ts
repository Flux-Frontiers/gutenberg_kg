/**
 * Road routing that respects the trees.
 *
 * Roads used to be straight spokes and a ring drawn through the grove stops,
 * blind to where trunks stood; after the compact layout some ran straight
 * through trees and the cart got stuck. Here every road is routed on a
 * clearance map of the trunks: A* over a grid whose step cost rises as a
 * route squeezes past a tree and falls on road already built, so routes wind
 * between trunks and merge into a network instead of running side by side.
 * Each route is then pulled taut (line-of-sight shortcuts) and smoothed, and
 * the smoothing is kept only where the whole lane stays clear.
 */

export type Point = [number, number];
export type Obstacle = { x: number; z: number; r: number };

type Grid = {
  n: number;
  cell: number;
  origin: number;
  /** Distance from each cell centre to the nearest obstacle surface (capped). */
  clear: Float32Array;
  /** 1 where a road already runs. */
  road: Uint8Array;
};

const FAR = 14;

function makeGrid(obstacles: Obstacle[], worldR: number, cell: number): Grid {
  const n = Math.ceil((2 * worldR) / cell) + 1;
  const origin = -worldR;
  const clear = new Float32Array(n * n).fill(FAR);
  const reach = Math.ceil(FAR / cell);
  for (const o of obstacles) {
    const ci = Math.round((o.x - origin) / cell), cj = Math.round((o.z - origin) / cell);
    for (let i = Math.max(0, ci - reach); i <= Math.min(n - 1, ci + reach); i++) {
      for (let j = Math.max(0, cj - reach); j <= Math.min(n - 1, cj + reach); j++) {
        const d = Math.hypot(origin + i * cell - o.x, origin + j * cell - o.z) - o.r;
        const k = i * n + j;
        if (d < clear[k]!) clear[k] = d;
      }
    }
  }
  return { n, cell, origin, clear, road: new Uint8Array(n * n) };
}

/** Clearance at any point, bilinear over the grid. */
export function clearanceAt(g: Grid, x: number, z: number): number {
  const fi = (x - g.origin) / g.cell, fj = (z - g.origin) / g.cell;
  const i = Math.max(0, Math.min(g.n - 2, Math.floor(fi))), j = Math.max(0, Math.min(g.n - 2, Math.floor(fj)));
  const u = Math.min(1, Math.max(0, fi - i)), v = Math.min(1, Math.max(0, fj - j));
  const c = (a: number, b: number) => g.clear[(i + a) * g.n + (j + b)]!;
  return (1 - u) * ((1 - v) * c(0, 0) + v * c(0, 1)) + u * ((1 - v) * c(1, 0) + v * c(1, 1));
}

/** Min-heap keyed by f-score. */
class Heap {
  private k: number[] = [];
  private f: number[] = [];
  get size() { return this.k.length; }
  push(key: number, f: number) {
    this.k.push(key); this.f.push(f);
    let i = this.k.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (this.f[p]! <= this.f[i]!) break;
      [this.k[p], this.k[i]] = [this.k[i]!, this.k[p]!];
      [this.f[p], this.f[i]] = [this.f[i]!, this.f[p]!];
      i = p;
    }
  }
  pop(): number {
    const top = this.k[0]!;
    const lk = this.k.pop()!, lf = this.f.pop()!;
    if (this.k.length) {
      this.k[0] = lk; this.f[0] = lf;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < this.k.length && this.f[l]! < this.f[m]!) m = l;
        if (r < this.k.length && this.f[r]! < this.f[m]!) m = r;
        if (m === i) break;
        [this.k[m], this.k[i]] = [this.k[i]!, this.k[m]!];
        [this.f[m], this.f[i]] = [this.f[i]!, this.f[m]!];
        i = m;
      }
    }
    return top;
  }
}

const STEPS: [number, number, number][] = [
  [1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1],
  [1, 1, Math.SQRT2], [1, -1, Math.SQRT2], [-1, 1, Math.SQRT2], [-1, -1, Math.SQRT2],
];
const ROAD_DISCOUNT = 0.4;

function nearestFree(g: Grid, i: number, j: number, need: number): [number, number] {
  for (let r = 0; r < g.n; r++) {
    for (let a = -r; a <= r; a++) for (let b = -r; b <= r; b++) {
      if (Math.max(Math.abs(a), Math.abs(b)) !== r) continue;
      const ii = i + a, jj = j + b;
      if (ii >= 0 && jj >= 0 && ii < g.n && jj < g.n && g.clear[ii * g.n + jj]! >= need) return [ii, jj];
    }
  }
  return [i, j];
}

/** A* from a to b over cells with at least `need` clearance; returns world points. */
function astar(g: Grid, a: Point, b: Point, need: number): Point[] {
  const toCell = (p: Point): [number, number] => [
    Math.max(0, Math.min(g.n - 1, Math.round((p[0] - g.origin) / g.cell))),
    Math.max(0, Math.min(g.n - 1, Math.round((p[1] - g.origin) / g.cell))),
  ];
  const [si, sj] = nearestFree(g, ...toCell(a), need);
  const [ti, tj] = nearestFree(g, ...toCell(b), need);
  const start = si * g.n + sj, goal = ti * g.n + tj;
  const gScore = new Float64Array(g.n * g.n).fill(Infinity);
  const came = new Int32Array(g.n * g.n).fill(-1);
  const closed = new Uint8Array(g.n * g.n);
  const heap = new Heap();
  gScore[start] = 0;
  heap.push(start, 0);
  while (heap.size) {
    const cur = heap.pop();
    if (cur === goal) break;
    if (closed[cur]) continue;
    closed[cur] = 1;
    const ci = Math.floor(cur / g.n), cj = cur % g.n;
    for (const [di, dj, len] of STEPS) {
      const ni = ci + di, nj = cj + dj;
      if (ni < 0 || nj < 0 || ni >= g.n || nj >= g.n) continue;
      const k = ni * g.n + nj;
      const c = g.clear[k]!;
      if (c < need || closed[k]) continue;
      // Squeezing past a trunk costs more; riding an existing road costs less.
      const squeeze = 1 + 3 * Math.exp(-(c - need) / 2);
      const cost = len * g.cell * squeeze * (g.road[k] ? ROAD_DISCOUNT : 1);
      const ng = gScore[cur]! + cost;
      if (ng < gScore[k]!) {
        gScore[k] = ng;
        came[k] = cur;
        heap.push(k, ng + Math.hypot(ni - ti, nj - tj) * g.cell * ROAD_DISCOUNT);
      }
    }
  }
  const path: Point[] = [];
  for (let k = goal; k >= 0; k = k === start ? -1 : came[k]!) {
    path.push([g.origin + Math.floor(k / g.n) * g.cell, g.origin + (k % g.n) * g.cell]);
    if (k !== start && came[k]! < 0) break; // unreachable: return what we have
  }
  path.reverse();
  path[0] = a;
  path[path.length - 1] = b;
  return path;
}

/** True when every point along a..b keeps `need` clearance. */
function lineClear(g: Grid, a: Point, b: Point, need: number): boolean {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const steps = Math.max(1, Math.ceil(len / (g.cell * 0.5)));
  for (let s = 0; s <= steps; s++) {
    const t = s / steps;
    if (clearanceAt(g, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) < need) return false;
  }
  return true;
}

/** String-pull a grid path: keep only the corners line of sight needs. */
function pullTaut(g: Grid, path: Point[], need: number): Point[] {
  if (path.length < 3) return path;
  const out: Point[] = [path[0]!];
  let anchor = 0;
  while (anchor < path.length - 1) {
    let next = anchor + 1;
    for (let j = path.length - 1; j > anchor + 1; j--) {
      if (lineClear(g, path[anchor]!, path[j]!, need)) { next = j; break; }
    }
    out.push(path[next]!);
    anchor = next;
  }
  return out;
}

/** Centripetal Catmull-Rom through pts (open or closed), resampled every ~step metres. */
export function spline(pts: Point[], step: number, closed: boolean): { pts: Point[]; span: number[] } {
  const n = pts.length;
  if (n < 2) return { pts: pts.slice(), span: pts.map((_, i) => i) };
  const at = (i: number) => (closed ? pts[(i + n) % n]! : pts[Math.max(0, Math.min(n - 1, i))]!);
  const out: Point[] = [];
  const span: number[] = [];
  const spans = closed ? n : n - 1;
  for (let i = 0; i < spans; i++) {
    const p0 = at(i - 1), p1 = at(i), p2 = at(i + 1), p3 = at(i + 2);
    const d = (a: Point, b: Point) => Math.max(1e-4, Math.hypot(b[0] - a[0], b[1] - a[1]) ** 0.5);
    const t0 = 0, t1 = t0 + d(p0, p1), t2 = t1 + d(p1, p2), t3 = t2 + d(p2, p3);
    const steps = Math.max(1, Math.ceil(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / step));
    for (let s = 0; s < steps; s++) {
      const t = t1 + ((t2 - t1) * s) / steps;
      const lerp = (a: Point, b: Point, ta: number, tb: number): Point =>
        [a[0] + ((b[0] - a[0]) * (t - ta)) / (tb - ta), a[1] + ((b[1] - a[1]) * (t - ta)) / (tb - ta)];
      const a1 = lerp(p0, p1, t0, t1), a2 = lerp(p1, p2, t1, t2), a3 = lerp(p2, p3, t2, t3);
      out.push(lerp(lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3), t1, t2));
      span.push(i);
    }
  }
  if (!closed) { out.push(pts[n - 1]!); span.push(n - 1); }
  return { pts: out, span };
}

/** Densify a polyline so samples are at most `step` apart (used when smoothing would clip a tree). */
function densify(pts: Point[], step: number, closed: boolean): { pts: Point[]; span: number[] } {
  const out: Point[] = [];
  const span: number[] = [];
  const n = pts.length;
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const a = pts[i]!, b = pts[(i + 1) % n]!;
    const steps = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / step));
    for (let s = 0; s < steps; s++) { out.push([a[0] + ((b[0] - a[0]) * s) / steps, a[1] + ((b[1] - a[1]) * s) / steps]); span.push(i); }
  }
  if (!closed) { out.push(pts[n - 1]!); span.push(n - 1); }
  return { pts: out, span };
}

/** Smooth when the whole smoothed lane is clear, otherwise keep the taut corners. */
function finish(g: Grid, pts: Point[], need: number, closed: boolean) {
  const smooth = spline(pts, 2, closed);
  return smooth.pts.every(([x, z]) => clearanceAt(g, x, z) >= need) ? smooth : densify(pts, 2, closed);
}

function markRoad(g: Grid, pts: Point[], halfWidth: number) {
  const r = Math.ceil(halfWidth / g.cell);
  for (const [x, z] of pts) {
    const ci = Math.round((x - g.origin) / g.cell), cj = Math.round((z - g.origin) / g.cell);
    for (let i = ci - r; i <= ci + r; i++) for (let j = cj - r; j <= cj + r; j++) {
      if (i >= 0 && j >= 0 && i < g.n && j < g.n) g.road[i * g.n + j] = 1;
    }
  }
}

/**
 * Route the network: a spoke from the hub's edge to every stop, then the ring
 * through the stops in angle order. `need` is the clearance a road centreline
 * keeps from every obstacle surface (half the road plus a margin).
 */
export function routeNetwork(opts: {
  hubR: number;
  stops: Point[];
  obstacles: Obstacle[];
  worldR: number;
  need: number;
  cell?: number;
}): { spokes: Point[][]; ring: { pts: Point[]; leg: number[] }; clearance: (x: number, z: number) => number } {
  const g = makeGrid(opts.obstacles, opts.worldR, opts.cell ?? 1);
  const { need, stops, hubR } = opts;
  const spokes: Point[][] = [];
  // Nearest stops first, so farther spokes can ride the roads already laid.
  const order = stops.map((_, i) => i).sort((a, b) => Math.hypot(...stops[a]!) - Math.hypot(...stops[b]!));
  const bySpoke: Point[][] = [];
  for (const i of order) {
    const [sx, sz] = stops[i]!;
    const d = Math.hypot(sx, sz) || 1;
    const from: Point = [(sx / d) * hubR, (sz / d) * hubR];
    const route = finish(g, pullTaut(g, astar(g, from, stops[i]!, need), need), need, false).pts;
    markRoad(g, route, need);
    bySpoke[i] = route;
  }
  for (const r of bySpoke) spokes.push(r);

  const legPts: Point[] = [];
  const legOf: number[] = [];
  for (let i = 0; i < stops.length; i++) {
    const taut = pullTaut(g, astar(g, stops[i]!, stops[(i + 1) % stops.length]!, need), need);
    markRoad(g, taut, need);
    // Drop each leg's last point: it is the next leg's first.
    for (let k = 0; k < taut.length - 1; k++) { legPts.push(taut[k]!); legOf.push(i); }
  }
  const ring = finish(g, legPts, need, true);
  return {
    spokes,
    ring: { pts: ring.pts, leg: ring.span.map((s) => legOf[s]!) },
    clearance: (x, z) => clearanceAt(g, x, z),
  };
}
