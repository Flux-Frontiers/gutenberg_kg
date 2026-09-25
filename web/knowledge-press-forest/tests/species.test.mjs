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
