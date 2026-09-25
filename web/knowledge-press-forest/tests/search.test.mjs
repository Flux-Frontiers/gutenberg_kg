import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

const book = (slug, title) => ({ slug, title, author: "", genre: "g", genreLabel: "G", tags: [], excerpt: "" });
const tree = (slug, title, x, z) => ({ book: book(slug, title), x, z, trunkRadius: 0.6 });

test("search results come nearest first and skip non-matches", () => {
  const { searchTrees } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const forest = { trees: [tree("far", "Fire Far", 100, 0), tree("none", "Ice", 1, 0), tree("near", "Fire Near", 10, 0)] };
  assert.deepEqual(searchTrees(forest, "fire", 0, 0).map((t) => t.book.slug), ["near", "far"]);
  assert.deepEqual(searchTrees(forest, "  ", 0, 0), []);
});

test("jumping to a tree lands within reading range, on the near side, facing the trunk", () => {
  const { treeApproach } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const { forwardOf } = require(`${process.env.FOREST_TEST_BUILD}/sim.js`);
  const t = tree("t", "T", 50, 20);
  const pose = treeApproach(t, 0, 20);
  const d = Math.hypot(pose.x - t.x, pose.z - t.z);
  assert.ok(d > t.trunkRadius + 1 && d < 6.8, `distance ${d}`);
  assert.ok(pose.x < t.x);
  const f = forwardOf(pose.yaw);
  assert.ok(f.x * (t.x - pose.x) + f.z * (t.z - pose.z) > 0.99 * d, "faces the tree");
});
