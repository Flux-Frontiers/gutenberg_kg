import { getForest, treesNear, type Forest } from "./forest";
import { clamp } from "./math";

export type SimState = {
  x: number;
  y: number;
  z: number;
  yaw: number;
  speed: number;
  lat: number;
  ready: boolean;
};

export const sim: SimState = {
  x: 0,
  y: 0.42,
  z: 8,
  yaw: 0,
  speed: 0,
  lat: 0,
  ready: false,
};

export function resetSim(forest: Forest) {
  sim.x = forest.spawn.x;
  sim.z = forest.spawn.z;
  sim.yaw = forest.spawn.yaw;
  sim.speed = 0;
  sim.lat = 0;
  sim.y = 0.42;
  sim.ready = true;
}

export function stepVehicle(
  forest: Forest,
  throttle: number,
  steer: number,
  boost: boolean,
  dt: number,
) {
  const maxSpeed = boost ? 28 : 16.5;
  const accel = throttle >= 0 ? 18 : 22;
  sim.speed += throttle * accel * dt;
  const drag = throttle === 0 ? 3.4 : 1.1;
  sim.speed *= 1 - drag * dt;
  if (Math.abs(sim.speed) < 0.04 && throttle === 0) sim.speed = 0;
  sim.speed = clamp(sim.speed, -7, maxSpeed);

  const speedFactor = clamp(Math.abs(sim.speed) / 7.5, 0.12, 1);
  const reverse = sim.speed >= 0 ? 1 : -1;
  const turnRate = 1.55;
  sim.yaw += steer * turnRate * speedFactor * reverse * dt;

  const fx = -Math.sin(sim.yaw);
  const fz = -Math.cos(sim.yaw);
  const rx = Math.cos(sim.yaw);
  const rz = -Math.sin(sim.yaw);

  sim.lat += -steer * sim.speed * 0.08 * dt;
  sim.lat *= 1 - 7.5 * dt;

  sim.x += (fx * sim.speed + rx * sim.lat) * dt;
  sim.z += (fz * sim.speed + rz * sim.lat) * dt;

  const cartR = 1.05;
  const near = treesNear(forest, sim.x, sim.z, 8);
  for (const t of near) {
    const dx = sim.x - t.x;
    const dz = sim.z - t.z;
    const min = t.trunkRadius + cartR;
    const d = Math.hypot(dx, dz);
    if (d < min && d > 1e-4) {
      const push = (min - d) / d;
      sim.x += dx * push;
      sim.z += dz * push;
      sim.speed *= 0.55;
    }
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
