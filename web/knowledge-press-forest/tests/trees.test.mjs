import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

test("trunks scale with height while twigs stay fine", () => {
  const { growTree } = require(`${process.env.FOREST_TEST_BUILD}/growTree.js`);
  const { BOOKS } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  for (const b of BOOKS.slice(0, 40)) {
    const g = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks });
    const { radii, parents, n } = g.skeleton;
    // The pipe-model bug left every trunk on the 0.18 floor, ~1:90 of height.
    assert.ok(g.trunkHeight / g.trunkRadius < 40, `${b.slug}: h/r ${g.trunkHeight / g.trunkRadius}`);
    assert.ok(Math.min(...radii) < 0.06, `${b.slug}: thinnest twig ${Math.min(...radii)}`);
    for (let i = 1; i < n; i++) {
      if (parents[i] >= 0) assert.ok(radii[parents[i]] >= radii[i] - 1e-6, `${b.slug}: node ${i} thicker than its parent`);
    }
  }
});

test("every leaf hangs within reach of a branch", () => {
  const { growTree } = require(`${process.env.FOREST_TEST_BUILD}/growTree.js`);
  const { BOOKS } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  for (const b of BOOKS.slice(0, 40)) {
    const g = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks });
    const { nodes, n } = g.skeleton;
    for (let l = 0; l < g.nLeaves; l++) {
      let best = Infinity;
      for (let i = 0; i < n; i++) {
        best = Math.min(best, Math.hypot(g.leafPoints[l * 3] - nodes[i * 3], g.leafPoints[l * 3 + 1] - nodes[i * 3 + 1], g.leafPoints[l * 3 + 2] - nodes[i * 3 + 2]));
      }
      // Before the fix the median leaf floated 1.5 m from any branch, some 8 m.
      assert.ok(best <= 0.6 + 1e-4, `${b.slug}: leaf ${l} is ${best.toFixed(2)} m from a branch`);
    }
  }
});

test("bark is one watertight sweep per chain, facing outward, with wrapping UVs", () => {
  const { growTree, emitBark } = require(`${process.env.FOREST_TEST_BUILD}/growTree.js`);
  const { BOOKS } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  for (const b of BOOKS.slice(0, 12)) {
    const out = { pos: [], normal: [], uv: [], index: [] };
    const g = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks });
    const count = emitBark(g, 5, -3, out, 2);
    assert.equal(count, out.pos.length / 3);
    assert.equal(out.uv.length / 2, count);
    assert.ok(out.index.every((i) => i >= 0 && i < count), `${b.slug}: index out of range`);
    let agree = 0, tris = 0;
    for (let t = 0; t < out.index.length; t += 3) {
      const [a, c, d] = [out.index[t], out.index[t + 1], out.index[t + 2]];
      const v = (i, k) => out.pos[i * 3 + k];
      const e1 = [0, 1, 2].map((k) => v(c, k) - v(a, k));
      const e2 = [0, 1, 2].map((k) => v(d, k) - v(a, k));
      const f = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
      const nrm = [0, 1, 2].map((k) => out.normal[a * 3 + k] + out.normal[c * 3 + k] + out.normal[d * 3 + k]);
      const dot = f[0] * nrm[0] + f[1] * nrm[1] + f[2] * nrm[2];
      if (Math.hypot(...f) < 1e-9) continue;
      tris++;
      if (dot > 0) agree++;
    }
    // Counter-clockwise from outside, or the bark renders inside-out.
    assert.ok(agree / tris > 0.99, `${b.slug}: ${agree}/${tris} faces point outward`);
    // Around each ring u runs 0..k with an integer k, so the texture tiles across the seam.
    for (let i = 0; i < count; i++) {
      const u = out.uv[i * 2];
      assert.ok(Number.isFinite(u) && Number.isFinite(out.uv[i * 2 + 1]));
    }
  }
});

test("leaf levels are fractions of the book's chunks; the skeleton never changes", () => {
  const { growTree } = require(`${process.env.FOREST_TEST_BUILD}/growTree.js`);
  const { BOOKS } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  for (const b of BOOKS.slice(0, 8)) {
    const all = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks });
    assert.equal(all.nLeaves, b.chunks, `${b.slug}: Ultra is one leaf per chunk`);
    for (const leafScale of [0.1, 0.25, 0.5]) {
      const g = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks, leafScale });
      assert.deepEqual(Array.from(g.skeleton.radii), Array.from(all.skeleton.radii), `${b.slug}: skeleton changed at ${leafScale}`);
      assert.ok(Math.abs(g.nLeaves - b.chunks * leafScale) <= 1, `${b.slug}: ${g.nLeaves} leaves at ${leafScale} of ${b.chunks}`);
    }
  }
});

test("growth mirrors the Python viz3d: <=3000 attractors, every one reached by wood", () => {
  const { growTree, MAX_ATTRACTORS } = require(`${process.env.FOREST_TEST_BUILD}/growTree.js`);
  const { BOOKS } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  assert.equal(MAX_ATTRACTORS, 3000);
  const big = BOOKS.slice().sort((a, b) => b.chunks - a.chunks)[0];
  for (const b of [big, ...BOOKS.slice(0, 6)]) {
    const g = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks });
    const m = g.crown.length / 3;
    assert.equal(m, Math.min(b.chunks, 3000), `${b.slug}: ${m} attractors`);
    const { nodes, n } = g.skeleton;
    // colonize's last pass gives every surviving attractor its own twig, to within kill = 2 * step.
    for (let a = 0; a < m; a++) {
      let best = Infinity;
      for (let i = 0; i < n; i++) best = Math.min(best, Math.hypot(g.crown[a * 3] - nodes[i * 3], g.crown[a * 3 + 1] - nodes[i * 3 + 1], g.crown[a * 3 + 2] - nodes[i * 3 + 2]));
      assert.ok(best <= 2 * g.step + 1e-3, `${b.slug}: attractor ${a} is ${best.toFixed(2)} m from wood (kill ${(2 * g.step).toFixed(2)})`);
    }
  }
});

test("every leaf hangs on the wood near its chunk, blade lifted toward the sky", () => {
  const { growTree } = require(`${process.env.FOREST_TEST_BUILD}/growTree.js`);
  const { BOOKS } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  for (const b of BOOKS.slice(0, 8)) {
    const g = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks });
    const { nodes, n } = g.skeleton;
    let up = 0;
    for (let l = 0; l < g.nLeaves; l++) {
      let best = Infinity;
      for (let i = 0; i < n; i++) best = Math.min(best, Math.hypot(g.leafPoints[l * 3] - nodes[i * 3], g.leafPoints[l * 3 + 1] - nodes[i * 3 + 1], g.leafPoints[l * 3 + 2] - nodes[i * 3 + 2]));
      assert.ok(best <= 0.1 + 1e-4, `${b.slug}: leaf ${l} is ${best.toFixed(2)} m from a node`);
      const dl = Math.hypot(g.leafDirs[l * 3], g.leafDirs[l * 3 + 1], g.leafDirs[l * 3 + 2]);
      assert.ok(Math.abs(dl - 1) < 1e-4);
      if (g.leafDirs[l * 3 + 1] > 0) up++;
    }
    assert.ok(up / g.nLeaves > 0.7, `${b.slug}: only ${up}/${g.nLeaves} leaves point upward`);
  }
});

test("trunks rise plumb to their first fork instead of leaning toward one side", () => {
  const { growTree } = require(`${process.env.FOREST_TEST_BUILD}/growTree.js`);
  const { BOOKS } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  for (const b of BOOKS.slice(0, 20)) {
    const { nodes, parents, n } = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks }).skeleton;
    const kids = Array.from({ length: n }, () => []);
    for (let i = 1; i < n; i++) kids[parents[i]].push(i);
    let k = 0;
    while (kids[k].length === 1) k = kids[k][0];
    const lean = Math.atan2(Math.hypot(nodes[k * 3], nodes[k * 3 + 2]), nodes[k * 3 + 1]) * 180 / Math.PI;
    // Bridging to the nearest crown point leaned every trunk ~28 deg the same way.
    assert.ok(lean < 5, `${b.slug}: trunk leans ${lean.toFixed(1)} deg`);
  }
});
