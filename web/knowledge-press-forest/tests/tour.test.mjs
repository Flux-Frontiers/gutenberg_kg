import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
globalThis.window ??= { localStorage: { getItem: () => null, setItem() {} } };

function roadDistance(f, x, z) {
  let best = Infinity;
  for (const r of f.roads) {
    const dx = r.bx - r.ax, dz = r.bz - r.az;
    const t = Math.max(0, Math.min(1, ((x - r.ax) * dx + (z - r.az) * dz) / (dx * dx + dz * dz || 1)));
    best = Math.min(best, Math.hypot(x - r.ax - dx * t, z - r.az - dz * t));
  }
  // Plazas are paved too: the tour turns round on a stop's plaza where the ring doubles back.
  for (const p of f.plazas) if (Math.hypot(x - p.x, z - p.z) < p.r) return 0;
  return best;
}

function driveTour(f, x, z, yaw) {
  const { sim, teleportSim, stepVehicle } = require(`${process.env.FOREST_TEST_BUILD}/sim.js`);
  const { planTour, steerTour } = require(`${process.env.FOREST_TEST_BUILD}/tour.js`);
  teleportSim(x, z, yaw);
  const tour = planTour(f, sim.x, sim.z, sim.yaw);
  // Every route point is on the brick.
  for (const [px, pz] of tour.pts) assert.ok(roadDistance(f, px, pz) < 0.05, `route point ${px.toFixed(1)}, ${pz.toFixed(1)} is off the road`);
  const stops = new Set();
  let onRoad = false, worst = 0;
  const hz = 30;
  for (let i = 0; i < 600 * hz; i++) {
    const c = steerTour(tour, sim.x, sim.z, sim.yaw, sim.speed);
    stepVehicle(f, c.throttle, c.steer, false, 1 / hz, {});
    const d = roadDistance(f, sim.x, sim.z);
    // The start may be off the road; once the cart reaches the brick it must stay on it.
    if (d < 1) onRoad = true;
    if (onRoad) worst = Math.max(worst, d);
    for (const wp of f.circuit) if (Math.hypot(wp.x - sim.x, wp.z - sim.z) < 4) stops.add(wp.genre);
  }
  return { tour, onRoad, worst, stops };
}

test("the guided tour keeps to the road, from home and from the hub end of a spoke, past every grove", () => {
  const { getForest } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const f = getForest();
  const spoke = f.roadLines.filter((l) => l.kind === "spoke").sort((a, b) => b.pts.length - a.pts.length)[0];
  const [sx, sz] = spoke.pts[0], [nx, nz] = spoke.pts[3];
  const starts = [
    { name: "home", ...f.home },
    { name: "spoke", x: sx, z: sz, yaw: Math.atan2(-(nx - sx), -(nz - sz)) },
  ];
  for (const s of starts) {
    const { tour, onRoad, worst, stops } = driveTour(f, s.x, s.z, s.yaw);
    if (s.name === "spoke") assert.ok(tour.loopStart > 0, "a start on a spoke rides the spoke out to the ring");
    assert.ok(onRoad, `${s.name}: never reached the road`);
    // Half the narrowest road (the 2.8 m spokes).
    assert.ok(worst < 1.4, `${s.name}: strayed ${worst.toFixed(2)} m from the road`);
    assert.equal(stops.size, f.circuit.length, `${s.name}: passed ${stops.size} of ${f.circuit.length} grove stops`);
  }
});

test("the road network: a ring that never crosses itself, and a few spokes spread round the hub", () => {
  const { getForest } = require(`${process.env.FOREST_TEST_BUILD}/forest.js`);
  const f = getForest();
  const c = f.circuit;
  const cross = (p, q, r, s) => {
    const o = (a, b, d) => Math.sign((b.x - a.x) * (d.z - a.z) - (b.z - a.z) * (d.x - a.x));
    return o(p, q, r) * o(p, q, s) < 0 && o(r, s, p) * o(r, s, q) < 0;
  };
  for (let i = 0; i < c.length; i++) {
    for (let j = i + 2; j < c.length; j++) {
      if ((j + 1) % c.length === i) continue;
      assert.ok(!cross(c[i], c[(i + 1) % c.length], c[j], c[(j + 1) % c.length]), `stops ${i} and ${j} legs cross`);
    }
  }
  const spokes = f.roadLines.filter((l) => l.kind === "spoke");
  assert.ok(spokes.length >= 3 && spokes.length <= 7, `${spokes.length} spokes`);
});
