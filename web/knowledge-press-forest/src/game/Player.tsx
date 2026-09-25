import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Group, MathUtils, PerspectiveCamera, Vector3 } from "three";
import { treesNear, type Forest } from "./forest";
import { resetInput, sampleActions } from "./input";
import { clamp } from "./math";
import { forwardOf, sim, stepVehicle, teleportSim } from "./sim";
import { planTour, steerTour, tourState } from "./tour";
import { useGame } from "./store";

const camPos = new Vector3();
/** Within this of a picked tree, the cart has arrived (reading range plus a margin). */
const TRAIL_ARRIVED = 9;
const lookAt = new Vector3();

export function Player({ forest, playing }: { forest: Forest; playing: boolean }) {
  const group = useRef<Group>(null);
  const wheelL = useRef<Group>(null);
  const wheelR = useRef<Group>(null);
  const poseAcc = useRef(0);
  const wasBlocked = useRef(false);
  // Camera tilt in radians, held between drives; Up/Down or the right stick.
  const pitch = useRef(0);
  const lastMarked = useRef<string | null>(null);

  const paused = useGame((s) => s.paused);
  const collect = useGame((s) => s.collect);
  const markGrove = useGame((s) => s.markGrove);
  const setNearby = useGame((s) => s.setNearby);
  const setPose = useGame((s) => s.setPose);

  const lanternColor = useMemo(() => "#f3e6c2", []);

  useFrame((state, delta) => {
    const dt = Math.min(delta, 0.1);
    const game = useGame.getState();
    const { preferences, jump } = game;
    const blocked = !playing || paused || game.libraryOpen || game.atlasOpen || game.catalogOpen || Boolean(document.activeElement?.matches("input, textarea, select, [contenteditable=true]"));
    if (blocked) {
      sim.speed = sim.lat = sim.steering = 0;
      if (!wasBlocked.current) resetInput();
    }
    wasBlocked.current = blocked;
    if (jump) {
      teleportSim(jump.x, jump.z, jump.yaw);
      useGame.getState().clearJump();
      const f = forwardOf(sim.yaw);
      state.camera.position.set(sim.x - f.x * 8.4, sim.y + 4.5, sim.z - f.z * 8.4);
      lookAt.set(sim.x + f.x * 2.6, sim.y + 1.4, sim.z + f.z * 2.6);
      state.camera.lookAt(lookAt);
    }

    if (blocked) {
      // Still keep camera on the cart while paused
    } else {
      const a = sampleActions();
      let throttle = a.throttle;
      let steer = a.steer;
      const mode = useGame.getState().travelMode;
      if (mode !== "circuit") tourState.tour = null;
      else if (forest.ringPath.length > 1) {
        if (Math.abs(a.steer) > 0.38 || a.brake || a.throttle < 0) {
          tourState.tour = null;
          useGame.getState().setTravelMode("free");
          useGame.getState().setToast("Free drive");
        } else {
          tourState.tour ??= planTour(forest, sim.x, sim.z, sim.yaw);
          const c = steerTour(tourState.tour, sim.x, sim.z, sim.yaw, sim.speed);
          steer = c.steer;
          if (throttle === 0) throttle = c.throttle;
          useGame.getState().selectGrove(c.genre);
        }
      }
      stepVehicle(forest, throttle, steer, a.boost, dt, { ...preferences, brake: a.brake });
      pitch.current = clamp(pitch.current + a.pitch * 1.1 * dt, -0.45, 0.75);

      if (a.interact) {
        const near = treesNear(forest, sim.x, sim.z, 6.8);
        let best = near[0];
        let bestD = Infinity;
        for (const t of near) {
          const d = Math.hypot(t.x - sim.x, t.z - sim.z);
          if (d < bestD) {
            bestD = d;
            best = t;
          }
        }
        if (best && bestD < 6.8) collect(best.book.slug, best.book.title);
      }
    }

    const f = forwardOf(sim.yaw);
    const inCart = preferences.camera === "cart";
    if (inCart) {
      // Turtle's-eye: on the back seat, low, looking over the lantern. Rigid, no chase lag.
      camPos.set(sim.x - f.x * 0.45, sim.y + 1.3, sim.z - f.z * 0.45);
      state.camera.position.copy(camPos);
      lookAt.set(sim.x + f.x * 10, sim.y + 1.15, sim.z + f.z * 10);
    } else {
      const follow = preferences.camera === "high" ? 12 : 8.4;
      const height = preferences.camera === "high" ? 10 : 4.5;
      camPos.set(sim.x - f.x * follow, sim.y + height, sim.z - f.z * follow);
      state.camera.position.lerp(camPos, 1 - Math.exp(-3.4 * dt));
      lookAt.set(sim.x + f.x * 2.6, sim.y + 1.4, sim.z + f.z * 2.6);
    }
    // Tilt by raising or lowering the look point over its horizontal distance.
    lookAt.y += Math.hypot(lookAt.x - state.camera.position.x, lookAt.z - state.camera.position.z) * Math.tan(pitch.current);
    state.camera.lookAt(lookAt);
    const cam = state.camera as PerspectiveCamera;
    const fovTarget = inCart ? 72 : 58;
    cam.fov = MathUtils.lerp(cam.fov, fovTarget, 1 - Math.exp(-4 * dt));
    cam.updateProjectionMatrix();

    const g = group.current;
    if (g) {
      g.position.set(sim.x, sim.y, sim.z);
      g.lookAt(sim.x + f.x, sim.y, sim.z + f.z);
      if (preferences.motion) g.rotateZ(-sim.steering * Math.min(Math.abs(sim.speed), 12) * 0.003);
    }
    const spin = (sim.speed * dt) / 0.42;
    if (wheelL.current) wheelL.current.rotation.x += spin;
    if (wheelR.current) wheelR.current.rotation.x += spin;

    const near = treesNear(forest, sim.x, sim.z, 16);
    let bestSlug: string | null = null;
    let bestD = 16;
    for (const t of near) {
      const d = Math.hypot(t.x - sim.x, t.z - sim.z);
      if (d < bestD) {
        bestD = d;
        bestSlug = t.book.slug;
      }
    }

    for (const grove of forest.groves) {
      if (Math.hypot(grove.x - sim.x, grove.z - sim.z) < grove.radius) {
        if (lastMarked.current !== grove.genre) {
          lastMarked.current = grove.genre;
          markGrove(grove.genre);
        }
        // Arrived at the grove the trail was leading to: put the lantern trail away.
        if (game.travelMode === "free" && game.selectedGrove === grove.genre) game.selectGrove(null);
      }
    }

    // Arrived at the tree the trail was leading to: put the trail and the query away.
    if (game.searchPick) {
      const t = forest.trees.find((tr) => tr.book.slug === game.searchPick);
      if (!t || Math.hypot(t.x - sim.x, t.z - sim.z) < TRAIL_ARRIVED) game.setQuery("");
    }

    poseAcc.current += dt;
    if (poseAcc.current > 0.08) {
      poseAcc.current = 0;
      setNearby(bestSlug, bestD);
      setPose(sim.x, sim.z, sim.yaw, sim.speed);
    }
  });

  return (
    <group ref={group}>
      <mesh position={[0, 0.38, 0.05]} castShadow receiveShadow>
        <boxGeometry args={[1.15, 0.32, 1.85]} />
        <meshStandardMaterial color="#5a3d28" roughness={0.85} />
      </mesh>
      <mesh position={[0, 0.62, -0.15]}>
        <boxGeometry args={[1.02, 0.22, 1.1]} />
        <meshStandardMaterial color="#4a3322" roughness={0.8} />
      </mesh>
      <mesh position={[0, 0.78, -0.35]}>
        <boxGeometry args={[0.42, 0.16, 0.32]} />
        <meshStandardMaterial color="#7a2e2e" roughness={0.7} />
      </mesh>
      <mesh position={[0.22, 0.78, -0.12]}>
        <boxGeometry args={[0.34, 0.14, 0.26]} />
        <meshStandardMaterial color="#2e3a5a" roughness={0.7} />
      </mesh>
      <mesh position={[-0.2, 0.78, -0.08]}>
        <boxGeometry args={[0.3, 0.12, 0.22]} />
        <meshStandardMaterial color="#3d4a32" roughness={0.7} />
      </mesh>
      <mesh position={[0, 0.55, 0.95]}>
        <boxGeometry args={[0.08, 0.7, 0.08]} />
        <meshStandardMaterial color="#3a322c" />
      </mesh>
      <mesh position={[0, 1.02, 0.95]}>
        <boxGeometry args={[0.18, 0.22, 0.18]} />
        <meshStandardMaterial color={lanternColor} emissive={lanternColor} emissiveIntensity={1.4} />
      </mesh>
      <pointLight position={[0, 1.05, 0.95]} color="#f6e7c2" intensity={6.5} distance={18} decay={2} />
      <group ref={wheelL} position={[-0.68, 0.32, 0.45]}>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.32, 0.32, 0.14, 10]} />
          <meshStandardMaterial color="#2a2420" roughness={0.95} />
        </mesh>
      </group>
      <group ref={wheelR} position={[0.68, 0.32, 0.45]}>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.32, 0.32, 0.14, 10]} />
          <meshStandardMaterial color="#2a2420" roughness={0.95} />
        </mesh>
      </group>
      <group position={[-0.68, 0.32, -0.55]}>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.28, 0.28, 0.12, 10]} />
          <meshStandardMaterial color="#2a2420" />
        </mesh>
      </group>
      <group position={[0.68, 0.32, -0.55]}>
        <mesh rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.28, 0.28, 0.12, 10]} />
          <meshStandardMaterial color="#2a2420" />
        </mesh>
      </group>
    </group>
  );
}
