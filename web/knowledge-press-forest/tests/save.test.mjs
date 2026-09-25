import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

test("existing collections survive preference changes and library jumps close the panel", () => {
  let save = JSON.stringify({ version: 1, library: ["hamlet"], grovesVisited: ["shakespeare"], season: "winter", timeOfDay: "night" });
  globalThis.window = { localStorage: { getItem: () => save, setItem: (_, value) => { save = value; } } };
  const { useGame } = require(`${process.env.FOREST_TEST_BUILD}/store.js`);
  assert.deepEqual(useGame.getState().library, ["hamlet"]);
  assert.equal(useGame.getState().preferences.pace, "gentle");
  useGame.getState().setPreferences({ camera: "high", sensitivity: 1.2 });
  const saved = JSON.parse(save);
  assert.deepEqual(saved.library, ["hamlet"]);
  assert.deepEqual(saved.grovesVisited, ["shakespeare"]);
  assert.equal(saved.preferences.camera, "high");
  assert.equal(saved.season, "winter");
  useGame.getState().toggleLibrary();
  useGame.getState().requestJump({ x: 1, z: 2, yaw: 0 });
  assert.equal(useGame.getState().libraryOpen, false);
});

test("leaving the ring puts the lantern trail away; a grove jump keeps it", () => {
  const { useGame } = require(`${process.env.FOREST_TEST_BUILD}/store.js`);
  const st = () => useGame.getState();
  st().toggleCircuit();
  st().selectGrove("horror");
  st().toggleCircuit(); // End tour
  assert.equal(st().selectedGrove, null);
  st().toggleCircuit();
  st().selectGrove("drama");
  st().setTravelMode("free"); // steered off the ring
  assert.equal(st().selectedGrove, null);
  st().selectGrove("letters");
  st().requestJump({ x: 0, z: 0, yaw: 0 }); // atlas jump: trail should lead there
  assert.equal(st().selectedGrove, "letters");
});
