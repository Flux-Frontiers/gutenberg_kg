import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} } };

test("the ring is one closed road through every grove stop", () => {
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
  const n = ring.pts.length;
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

test("compact layout: groves never overlap, trees keep driving room, the hub stays clear", () => {
  const { getForest } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const f = getForest();
  for (let i = 0; i < f.groves.length; i++) {
    const a = f.groves[i];
    assert.ok(Math.hypot(a.x, a.z) - a.radius >= 22 - 1e-6, `${a.genre} crowds the hub`);
    for (let j = i + 1; j < f.groves.length; j++) {
      const b = f.groves[j];
      assert.ok(Math.hypot(a.x - b.x, a.z - b.z) >= a.radius + b.radius + 10 - 1e-6, `${a.genre} and ${b.genre} overlap`);
    }
  }
  for (let i = 0; i < f.trees.length; i++) {
    for (let j = i + 1; j < f.trees.length; j++) {
      const d = Math.hypot(f.trees[i].x - f.trees[j].x, f.trees[i].z - f.trees[j].z);
      assert.ok(d >= 7.5, `${f.trees[i].book.slug} and ${f.trees[j].book.slug} are ${d.toFixed(1)} m apart`);
    }
  }
  assert.ok(f.worldRadius < 260, `world radius ${f.worldRadius.toFixed(0)} m`);
});

test("every road keeps the cart clear of every trunk and the hub plinth", () => {
  const { getForest, HUB_SCULPTURE_R } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const f = getForest();
  // Centreline clearance = half the widest road (1.7) + the cart's radius (1.05).
  for (const line of f.roadLines) {
    for (const [x, z] of line.pts) {
      for (const t of f.trees) {
        const c = Math.hypot(x - t.x, z - t.z) - t.trunkRadius;
        assert.ok(c >= 2.75 - 0.05, `${line.kind} passes ${c.toFixed(2)} m from ${t.book.slug}`);
      }
      assert.ok(Math.hypot(x, z) - HUB_SCULPTURE_R >= 2.75 - 0.05, `${line.kind} clips the hub plinth`);
    }
  }
});
