import type { RoadLine } from "./forest";

export type FlatMesh = { pos: number[]; uv: number[]; index: number[] };

// World metres per brick-texture repeat. UVs are planar (x, z) / tile, so the
// herringbone runs unbroken across every join, curve and plaza.
const BRICK_TILE = 2.4;

function vertex(out: FlatMesh, x: number, y: number, z: number) {
  out.pos.push(x, y, z);
  out.uv.push(x / BRICK_TILE, z / BRICK_TILE);
}

/**
 * A flat strip of `width` along a centreline at height `y`. Each point's edge
 * vertices sit on the bisector of its neighbouring segments, so consecutive
 * pieces share vertices instead of overlapping or leaving wedges.
 */
export function ribbon(line: RoadLine, width: number, y: number, out: FlatMesh) {
  const { pts, closed } = line;
  const n = pts.length;
  if (n < 2) return;
  const first = out.pos.length / 3;
  for (let i = 0; i < n; i++) {
    const prev = pts[closed ? (i - 1 + n) % n : Math.max(0, i - 1)]!;
    const next = pts[closed ? (i + 1) % n : Math.min(n - 1, i + 1)]!;
    let tx = next[0] - prev[0], tz = next[1] - prev[1];
    const tl = Math.hypot(tx, tz) || 1;
    tx /= tl;
    tz /= tl;
    const [x, z] = pts[i]!;
    const h = width / 2;
    vertex(out, x - tz * h, y, z + tx * h);
    vertex(out, x + tz * h, y, z - tx * h);
  }
  const quads = closed ? n : n - 1;
  for (let i = 0; i < quads; i++) {
    const a = first + i * 2, b = a + 1;
    const c = first + ((i + 1) % n) * 2, d = c + 1;
    out.index.push(a, c, b, b, c, d);
  }
}

/** A paved disc, used to cover junctions. */
export function disc(x: number, z: number, r: number, y: number, out: FlatMesh, segments = 28) {
  const centre = out.pos.length / 3;
  vertex(out, x, y, z);
  for (let s = 0; s <= segments; s++) {
    const a = (2 * Math.PI * s) / segments;
    vertex(out, x + Math.cos(a) * r, y, z + Math.sin(a) * r);
  }
  for (let s = 0; s < segments; s++) out.index.push(centre, centre + 2 + s, centre + 1 + s);
}
