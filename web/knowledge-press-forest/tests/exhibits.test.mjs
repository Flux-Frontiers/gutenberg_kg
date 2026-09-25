import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} } };

test("the corpus redwood: height from the corpus, one limb per book, pipe-model trunk", () => {
  const { getForest } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const { REDWOOD_HEIGHT_PER_LOG2 } = require(`${process.env.FOREST_TEST_BUILD}/corpusTree.js`);
  const f = getForest();
  const c = f.corpusTree;
  const total = f.trees.reduce((s, t) => s + t.book.chunks, 0);
  assert.equal(c.totalChunks, total);
  assert.equal(c.limbs, f.trees.length);
  assert.ok(Math.abs(c.height - REDWOOD_HEIGHT_PER_LOG2 * Math.log2(1 + total)) < 1e-9);
  const tallest = Math.max(...f.trees.map((t) => t.height));
  assert.ok(c.height > 2 * tallest, `redwood ${c.height.toFixed(0)} m against ${tallest.toFixed(0)} m`);
  // The flare stays on the hub plaza with room for the spokes to start around it.
  assert.ok(c.baseRadius + 2.75 < 9, `flare ${c.baseRadius.toFixed(2)} m`);
  assert.ok(c.bark.count > 0 && c.foliage.count > c.limbs);
  // Every spray hangs in the crown, not on the bole or out over the groves.
  for (let i = 0; i < c.foliage.count; i++) {
    const [x, y, z] = [c.foliage.pos[i * 3], c.foliage.pos[i * 3 + 1], c.foliage.pos[i * 3 + 2]];
    assert.ok(y > c.height * 0.25 && y < c.height * 1.05, `spray ${i} at ${y.toFixed(1)} m`);
    assert.ok(Math.hypot(x, z) < 20, `spray ${i} reaches ${Math.hypot(x, z).toFixed(1)} m`);
  }
});

test("exhibits stand in roadside glades: clear of trunks, off the road, apart from the hub", () => {
  const { getForest } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const { EXHIBITS, exhibitApproach } = require(`${process.env.FOREST_TEST_BUILD}/exhibits.js`);
  const { forwardOf } = require(`${process.env.FOREST_TEST_BUILD}/sim.js`);
  const f = getForest();
  assert.equal(f.exhibits.length, EXHIBITS.length, "every exhibit found a glade");
  for (const e of f.exhibits) {
    assert.ok(Math.hypot(e.x, e.z) >= 30, `${e.id} sits under the redwood`);
    for (const t of f.trees) {
      assert.ok(Math.hypot(t.x - e.x, t.z - e.z) - t.trunkRadius >= e.treeClearance - 1e-6, `${e.id} crowds ${t.book.slug}`);
    }
    // The plaza reaches the road it faces.
    const toRoad = Math.hypot(e.roadX - e.x, e.roadZ - e.z);
    assert.ok(e.plazaR > toRoad - 1.7, `${e.id} plaza stops short of the road`);
    assert.ok(f.plazas.some((p) => p.x === e.x && p.z === e.z));
    assert.ok(f.obstacles.some((o) => o.x === e.x && o.z === e.z && o.r === e.obstacle));
    const a = exhibitApproach(e);
    const fw = forwardOf(a.yaw);
    const d = Math.hypot(e.x - a.x, e.z - a.z);
    assert.ok(d > e.obstacle + 1.05, `${e.id} approach lands on the plinth`);
    assert.ok((fw.x * (e.x - a.x) + fw.z * (e.z - a.z)) / d > 0.999, `${e.id} approach looks away`);
  }
});
