import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} } };

test("the ring is one smooth closed road through every grove stop", () => {
  const { getForest } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const f = getForest();
  const rings = f.roadLines.filter((l) => l.kind === "ring");
  assert.equal(rings.length, 1);
  const ring = rings[0];
  assert.ok(ring.closed);
  for (const wp of f.circuit) {
    const d = Math.min(...ring.pts.map(([x, z]) => Math.hypot(x - wp.x, z - wp.z)));
    assert.ok(d < 0.01, `ring misses the ${wp.genre} stop by ${d.toFixed(2)} m`);
  }
  // Between stops the road turns gently. Stops sit 7-353 m from the hub, so the
  // ring zigzags and hairpins at each stop -- allowed only under that stop's plaza.
  const n = ring.pts.length;
  for (let i = 0; i < n; i++) {
    const [ax, az] = ring.pts[(i - 1 + n) % n], [bx, bz] = ring.pts[i], [cx, cz] = ring.pts[(i + 1) % n];
    const h1 = Math.atan2(bz - az, bx - ax), h2 = Math.atan2(cz - bz, cx - bx);
    const turn = Math.abs(Math.atan2(Math.sin(h2 - h1), Math.cos(h2 - h1)));
    if (turn < 0.2) continue;
    const covered = f.plazas.some((p) => Math.hypot(p.x - bx, p.z - bz) < p.r - 1.7); // 1.7 = half the ring's width
    const near = Math.min(...f.plazas.map((p) => Math.hypot(p.x - bx, p.z - bz)));
    assert.ok(covered, `uncovered turn of ${turn.toFixed(2)} rad at sample ${i}, ${near.toFixed(2)} m from a plaza centre`);
  }
  // The tour follows the same samples and names the grove it is heading for.
  assert.equal(f.ringPath.length, n);
  const genres = new Set(f.groves.map((g) => g.genre));
  assert.ok(f.ringPath.every((wp) => genres.has(wp.genre)));
});

test("a ribbon shares vertices between pieces and closes on itself", () => {
  const { ribbon, disc } = require(`${process.env.FOREST_TEST_BUILD}/roads.js`);
  const out = { pos: [], uv: [], index: [] };
  const square = { kind: "ring", pts: [[0, 0], [10, 0], [10, 10], [0, 10]], closed: true };
  ribbon(square, 2, 0.05, out);
  assert.equal(out.pos.length / 3, 8, "two edge vertices per centreline point, none duplicated");
  assert.equal(out.index.length, 4 * 6, "a closed loop of four points has four quads");
  assert.ok(out.index.every((i) => i < 8));
  // Planar UVs: the same world point gets the same UV on any piece, so bricks line up across joins.
  const d = { pos: [], uv: [], index: [] };
  disc(5, 5, 2, 0.05, d);
  assert.deepEqual(d.uv.slice(0, 2), [5 / 2.4, 5 / 2.4]);
});
