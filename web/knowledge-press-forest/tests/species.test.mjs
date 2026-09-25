import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

test("every catalog genre maps to a species on purpose, and every species has its bark", () => {
  const { SPECIES, speciesFor } = require(`${process.env.FOREST_TEST_BUILD}/species.js`);
  const { GENRE_ORDER } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  const src = require("node:fs").readFileSync("src/game/species.ts", "utf8");
  // A new genre silently falls back to chestnut; make adding it to the table a conscious step.
  for (const genre of GENRE_ORDER) assert.ok(src.includes(`"${genre}"`) || src.includes(`\n  ${genre}:`), `unmapped genre ${genre}`);
  for (const genre of GENRE_ORDER) assert.ok(speciesFor(genre) >= 0);
  for (const s of SPECIES) {
    for (const map of ["color", "normal"]) assert.ok(existsSync(`public/textures/bark/${s.name}_${map}.jpg`), `${s.name}_${map}.jpg`);
  }
});

test("each tree's bark lands in its species' mesh", () => {
  globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} } };
  const { getForest } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const { speciesFor } = require(`${process.env.FOREST_TEST_BUILD}/species.js`);
  const forest = getForest();
  const used = new Array(forest.bark.length).fill(0);
  for (const t of forest.trees) {
    assert.equal(t.species, speciesFor(t.book.genre));
    assert.ok(t.woodStart + t.woodCount <= forest.bark[t.species].count);
    used[t.species] += t.woodCount;
  }
  assert.deepEqual(used, forest.bark.map((b) => b.count));
  for (let i = 0; i < forest.leaves.count; i++) {
    assert.equal(forest.leaves.species[i], forest.trees[forest.leaves.treeIndex[i]].species);
  }
});

test("leaf outlines are closed, mirror-symmetric and have real area", () => {
  const { SPECIES, leafOutline } = require(`${process.env.FOREST_TEST_BUILD}/species.js`);
  const area = (pts) => Math.abs(pts.reduce((a, [x, y], i) => { const [u, v] = pts[(i + 1) % pts.length]; return a + x * v - u * y; }, 0)) / 2;
  const areas = {};
  for (const s of SPECIES) {
    const pts = leafOutline(s.leaf);
    assert.ok(pts.length >= 8, `${s.name}: ${pts.length} points`);
    assert.ok(pts.every(([x, y]) => Math.abs(x) <= 2 && Math.abs(y) <= 1.05), `${s.name}: outline out of bounds`);
    const maxX = Math.max(...pts.map((p) => p[0])), minX = Math.min(...pts.map((p) => p[0]));
    assert.ok(Math.abs(maxX + minX) < 1e-6, `${s.name}: not symmetric`);
    areas[s.name] = area(pts);
  }
  // The single-needle fir leaf was ~0.2 of a chestnut leaf; a spray should hold its own.
  assert.ok(areas.fir > 0.5 * areas.chestnut, `fir ${areas.fir} vs chestnut ${areas.chestnut}`);
});
