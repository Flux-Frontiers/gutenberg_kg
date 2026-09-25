import { getForest, treesNear, type Forest } from "./forest";
import { clamp } from "./math";
import type { Preferences } from "./preferences";

export type SimState = {
  x: number;
  y: number;
  z: number;
  yaw: number;
  speed: number;
  lat: number;
  steering: number;
  ready: boolean;
};

export const sim: SimState = {
  x: 0,
  y: 0,
  z: 8,
  yaw: 0,
  speed: 0,
  lat: 0,
  steering: 0,
  ready: false,
};

export function resetSim(forest: Forest) {
  sim.x = forest.spawn.x;
  sim.z = forest.spawn.z;
  sim.yaw = forest.spawn.yaw;
  sim.speed = 0;
  sim.lat = 0;
  sim.steering = 0;
  sim.y = 0;
  sim.ready = true;
}

export function teleportSim(x: number, z: number, yaw: number) {
  sim.x = x;
  sim.z = z;
  sim.yaw = yaw;
  sim.speed = 0;
  sim.lat = 0;
  sim.steering = 0;
  sim.y = 0;
}

export function wrapAngle(a: number): number {
  let x = a;
  while (x > Math.PI) x -= Math.PI * 2;
  while (x < -Math.PI) x += Math.PI * 2;
  return x;
}

export function yawToward(fromX: number, fromZ: number, toX: number, toZ: number): number {
  const dx = toX - fromX;
  const dz = toZ - fromZ;
  return Math.atan2(-dx, -dz);
}

export function stepVehicle(
  forest: Forest,
  throttle: number,
  steer: number,
  boost: boolean,
  dt: number,
  options: { brake?: boolean; pace?: Preferences["pace"]; sensitivity?: number } = {},
) {
  // Small steps keep collisions and handling stable across frame rates.
  const steps = Math.ceil(Math.min(Math.max(dt, 0), 0.1) / (1 / 120));
  if (!steps) return;
  for (let i = 0; i < steps; i++) step(forest, throttle, steer, boost, Math.min(dt, 0.1) / steps, options);
}

function step(forest: Forest, throttle: number, steer: number, boost: boolean, dt: number,
  options: { brake?: boolean; pace?: Preferences["pace"]; sensitivity?: number }) {
  const gentle = options.pace !== "brisk";
  // Halved for the compact layout (trees ~9 m apart): gentle is ~16 km/h.
  const maxSpeed = (gentle ? 4.5 : 9) * (boost ? 1.45 : 1);
  const accel = gentle ? 6 : 12;
  if (options.brake) {
    sim.speed = Math.sign(sim.speed) * Math.max(0, Math.abs(sim.speed) - 32 * dt);
  } else {
    sim.speed += clamp(throttle, -1, 1) * accel * dt;
  }
  const drag = throttle === 0 ? 4.5 : 0.65;
  sim.speed *= Math.exp(-drag * dt);
  if (Math.abs(sim.speed) < 0.04 && throttle === 0) sim.speed = 0;
  sim.speed = clamp(sim.speed, gentle ? -2.5 : -4.5, maxSpeed);

  const speedFactor = clamp(Math.abs(sim.speed) / 5, 0.65, 1);
  const reverse = sim.speed >= 0 ? 1 : -1;
  const turnRate = 1.55;
  sim.steering += (clamp(steer, -1, 1) - sim.steering) * (1 - Math.exp(-12 * dt));
  sim.yaw = wrapAngle(sim.yaw + sim.steering * turnRate * (options.sensitivity ?? 1) * speedFactor * reverse * dt);

  const fx = -Math.sin(sim.yaw);
  const fz = -Math.cos(sim.yaw);
  const rx = Math.cos(sim.yaw);
  const rz = -Math.sin(sim.yaw);

  sim.lat *= Math.exp(-12 * dt);

  sim.x += (fx * sim.speed + rx * sim.lat) * dt;
  sim.z += (fz * sim.speed + rz * sim.lat) * dt;

  const cartR = 1.05;
  const near = treesNear(forest, sim.x, sim.z, 8);
  for (const t of near) {
    const dx = sim.x - t.x;
    const dz = sim.z - t.z;
    const min = t.trunkRadius + cartR;
    const d = Math.hypot(dx, dz);
    if (d < min) {
      const nx = d > 1e-4 ? dx / d : -fx;
      const nz = d > 1e-4 ? dz / d : -fz;
      sim.x += nx * (min - d);
      sim.z += nz * (min - d);
      sim.speed *= 0.55;
    }
  }

  // The hub sculpture's plinth.
  const hd = Math.hypot(sim.x, sim.z);
  const hubMin = (forest.hubObstacle ?? 0) + cartR;
  if (forest.hubObstacle && hd < hubMin) {
    const nx = hd > 1e-4 ? sim.x / hd : -fx, nz = hd > 1e-4 ? sim.z / hd : -fz;
    sim.x = nx * hubMin;
    sim.z = nz * hubMin;
    sim.speed *= 0.55;
  }

  const lim = forest.worldRadius;
  const rd = Math.hypot(sim.x, sim.z);
  if (rd > lim) {
    sim.x *= lim / rd;
    sim.z *= lim / rd;
    sim.speed *= 0.4;
  }
}

export function forwardOf(yaw: number): { x: number; z: number } {
  return { x: -Math.sin(yaw), z: -Math.cos(yaw) };
}

export { getForest };
