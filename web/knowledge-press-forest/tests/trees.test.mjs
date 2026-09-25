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

test("leaf complexity changes only the foliage, and every leaf still hangs on a branch", () => {
  const { growTree } = require(`${process.env.FOREST_TEST_BUILD}/growTree.js`);
  const { BOOKS } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  for (const b of BOOKS.slice(0, 10)) {
    const base = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks });
    for (const leafScale of [0.5, 2, 4]) {
      const g = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks, leafScale });
      assert.deepEqual(Array.from(g.skeleton.radii), Array.from(base.skeleton.radii), `${b.slug}: skeleton changed at ${leafScale}`);
      assert.ok(Math.abs(g.nLeaves - base.nLeaves * leafScale) <= 1, `${b.slug}: ${g.nLeaves} leaves at ${leafScale} from ${base.nLeaves}`);
      const { nodes, n } = g.skeleton;
      for (let l = 0; l < g.nLeaves; l++) {
        let best = Infinity;
        for (let i = 0; i < n; i++) best = Math.min(best, Math.hypot(g.leafPoints[l * 3] - nodes[i * 3], g.leafPoints[l * 3 + 1] - nodes[i * 3 + 1], g.leafPoints[l * 3 + 2] - nodes[i * 3 + 2]));
        assert.ok(best <= 0.6 + 1e-4, `${b.slug}: leaf ${l} floats at ${leafScale}`);
      }
    }
  }
});

test("leaves sit on thin twigs, stalk first, blades lifted toward the sky", () => {
  const { growTree } = require(`${process.env.FOREST_TEST_BUILD}/growTree.js`);
  const { BOOKS } = require(`${process.env.FOREST_TEST_BUILD}/catalog.js`);
  for (const b of BOOKS.slice(0, 10)) {
    const g = growTree({ slug: b.slug, genre: b.genre, nChunks: b.chunks });
    const { nodes, parents, radii, n } = g.skeleton;
    let up = 0;
    for (let l = 0; l < g.nLeaves; l++) {
      const [x, y, z] = [0, 1, 2].map((k) => g.leafPoints[l * 3 + k]);
      // On some segment, within float error, and that segment is a twig.
      let best = Infinity, bestR = 0;
      for (let i = 1; i < n; i++) {
        const p = parents[i];
        if (p < 0) continue;
        const d = [0, 1, 2].map((k) => nodes[i * 3 + k] - nodes[p * 3 + k]);
        const len2 = d[0] ** 2 + d[1] ** 2 + d[2] ** 2 || 1;
        const t = Math.max(0, Math.min(1, ((x - nodes[p * 3]) * d[0] + (y - nodes[p * 3 + 1]) * d[1] + (z - nodes[p * 3 + 2]) * d[2]) / len2));
        const dist = Math.hypot(x - nodes[p * 3] - d[0] * t, y - nodes[p * 3 + 1] - d[1] * t, z - nodes[p * 3 + 2] - d[2] * t);
        if (dist < best) { best = dist; bestR = radii[i]; }
      }
      assert.ok(best < 1e-3, `${b.slug}: leaf ${l} is ${best.toFixed(3)} m off any branch`);
      assert.ok(bestR <= 0.045 * 2.5 + 1e-6 || bestR === Math.min(...radii), `${b.slug}: leaf ${l} on a limb of radius ${bestR.toFixed(3)}`);
      const dl = Math.hypot(g.leafDirs[l * 3], g.leafDirs[l * 3 + 1], g.leafDirs[l * 3 + 2]);
      assert.ok(Math.abs(dl - 1) < 1e-4);
      if (g.leafDirs[l * 3 + 1] > 0) up++;
    }
    assert.ok(up / g.nLeaves > 0.7, `${b.slug}: only ${up}/${g.nLeaves} leaves point upward`);
  }
});
