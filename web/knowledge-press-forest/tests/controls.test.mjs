import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { sim, resetSim, teleportSim, stepVehicle, forwardOf } = require(`${process.env.FOREST_TEST_BUILD}/sim.js`);
const input = require(`${process.env.FOREST_TEST_BUILD}/input.js`);
const { readPreferences } = require(`${process.env.FOREST_TEST_BUILD}/preferences.js`);
const empty = { spawn: { x: 0, z: 0, yaw: 0 }, worldRadius: 1000, trees: [], grid: new Map(), cell: 16 };
function drive(seconds, throttle, steer = 0, options = {}, hz = 60) {
  for (let i = 0; i < seconds * hz; i++) stepVehicle(empty, throttle, steer, false, 1 / hz, options);
}

test("forward, reverse and turn-in-place follow the chase camera convention", () => {
  resetSim(empty);
  drive(1, 1);
  assert.ok(sim.z < -3);
  resetSim(empty);
  drive(1, -1);
  assert.ok(sim.z > 1);
  resetSim(empty);
  drive(1, 0, 1);
  assert.ok(forwardOf(sim.yaw).x < -0.5, "A turns left even while stopped");
  assert.equal(sim.x, 0);
  resetSim(empty);
  drive(1, 0, -1);
  assert.ok(forwardOf(sim.yaw).x > 0.5, "D turns right");
});

test("brake overrides held throttle and stops without reversing", () => {
  resetSim(empty);
  drive(3, 1, 0, { pace: "brisk" });
  assert.ok(sim.speed > 15);
  drive(0.7, 1, 0, { brake: true, pace: "brisk" });
  assert.equal(sim.speed, 0);
  drive(1, 1, 0, { brake: true, pace: "brisk" });
  assert.equal(sim.speed, 0);
});

test("release stops promptly; gentle mode is slower than brisk mode", () => {
  resetSim(empty);
  drive(3, 1);
  const gentle = sim.speed;
  assert.ok(gentle <= 9);
  drive(1.5, 0);
  assert.equal(sim.speed, 0);
  resetSim(empty);
  drive(3, 1, 0, { pace: "brisk" });
  assert.ok(sim.speed > gentle * 1.5);
});

test("handling is stable at 30 and 120 fps", () => {
  resetSim(empty);
  drive(2, 1, 0.6, {}, 30);
  const slow = { ...sim };
  resetSim(empty);
  drive(2, 1, 0.6, {}, 120);
  assert.ok(Math.hypot(sim.x - slow.x, sim.z - slow.z) < 0.02);
  assert.ok(Math.abs(sim.yaw - slow.yaw) < 0.01);
});

test("trunk collision resolves even at its exact centre; world edge contains the cart", () => {
  resetSim(empty);
  const forest = { ...empty, trees: [{ x: 0, z: 0, trunkRadius: 1 }], grid: new Map([["0:0", [0]]]) };
  stepVehicle(forest, 0, 0, false, 1 / 60);
  assert.ok(Math.hypot(sim.x, sim.z) >= 2.049);
  teleportSim(1001, 0, 0);
  stepVehicle(empty, 0, 0, false, 1 / 60);
  assert.ok(Math.hypot(sim.x, sim.z) <= 1000);
});

test("input reset clears held keyboard, touch axes, brake and interaction edges", () => {
  input.setInjectedKeys(["KeyW", "Space", "KeyE"]);
  let actions = input.sampleActions();
  assert.equal(actions.throttle, 1);
  assert.equal(actions.brake, true);
  assert.equal(actions.interact, true);
  assert.equal(input.sampleActions().interact, false);
  input.setTouchAxes(1, 1);
  input.setTouchBrake(true);
  input.resetInput();
  assert.deepEqual(input.sampleActions(), { throttle: 0, steer: 0, boost: false, brake: false, interact: false, interactDown: false });
  input.setInjectedKeys(["Space"]);
  assert.equal(input.sampleActions().interact, false, "Space never collects a book");
  input.resetInput();
});

test("old or malformed preferences have usable defaults and bounded sensitivity", () => {
  assert.equal(readPreferences().pace, "gentle");
  assert.equal(readPreferences({ sensitivity: NaN }).sensitivity, 1);
  assert.equal(readPreferences({ sensitivity: 100 }).sensitivity, 1.5);
  assert.equal(readPreferences({ pace: "unknown", camera: "unknown" }).camera, "follow");
  assert.equal(readPreferences({ motion: false }).motion, false);
});

test("blur and visibility clear controls; binding can be cleaned up and mounted again", () => {
  const previous = { window: globalThis.window, document: globalThis.document, HTMLElement: globalThis.HTMLElement };
  class Element extends EventTarget { closest() { return null; } }
  class Surface extends Element {
    count = 0;
    addEventListener(...args) { this.count++; super.addEventListener(...args); }
    removeEventListener(...args) { this.count--; super.removeEventListener(...args); }
  }
  globalThis.HTMLElement = Element;
  globalThis.window = new Surface();
  globalThis.document = new Surface();
  const press = () => {
    const event = new Event("keydown");
    Object.assign(event, { code: "KeyW" });
    window.dispatchEvent(event);
  };
  try {
    for (let mount = 0; mount < 2; mount++) {
      const cleanup = input.bindInput();
      press();
      assert.equal(input.sampleActions().throttle, 1);
      window.dispatchEvent(new Event("blur"));
      assert.equal(input.sampleActions().throttle, 0);
      press();
      document.hidden = true;
      document.dispatchEvent(new Event("visibilitychange"));
      assert.equal(input.sampleActions().throttle, 0);
      cleanup();
      assert.equal(document.count + window.count, 0, "no leaked listeners");
    }
  } finally {
    Object.assign(globalThis, previous);
  }
});
