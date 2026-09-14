import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Group, MathUtils, PerspectiveCamera, Vector3 } from "three";
import { treesNear, type Forest } from "./forest";
import { sampleActions } from "./input";
import { forwardOf, sim, stepVehicle } from "./sim";
import { useGame } from "./store";

const camPos = new Vector3();
const lookAt = new Vector3();

export function Player({ forest, playing }: { forest: Forest; playing: boolean }) {
  const group = useRef<Group>(null);
  const wheelL = useRef<Group>(null);
  const wheelR = useRef<Group>(null);
  const poseAcc = useRef(0);
  const lastNearby = useRef<string | null>(null);

  const paused = useGame((s) => s.paused);
  const collect = useGame((s) => s.collect);
  const markGrove = useGame((s) => s.markGrove);
  const setNearby = useGame((s) => s.setNearby);
  const setPose = useGame((s) => s.setPose);

  const lanternColor = useMemo(() => "#f3e6c2", []);

  useFrame((state, delta) => {
    const dt = Math.min(delta, 0.1);
    if (!playing || paused) {
      // Still keep camera on the cart while paused
    } else {
      const a = sampleActions();
      stepVehicle(forest, a.throttle, a.steer, a.boost, dt);

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
    const follow = 8.4;
    const height = 4.5;
    camPos.set(sim.x - f.x * follow, sim.y + height, sim.z - f.z * follow);
    const k = 1 - Math.exp(-3.4 * dt);
    state.camera.position.lerp(camPos, k);
    lookAt.set(sim.x + f.x * 2.6, sim.y + 1.4, sim.z + f.z * 2.6);
    state.camera.lookAt(lookAt);
    const cam = state.camera as PerspectiveCamera;
    const fovTarget = MathUtils.lerp(56, 68, Math.min(1, Math.abs(sim.speed) / 22));
    cam.fov = MathUtils.lerp(cam.fov, fovTarget, 1 - Math.exp(-4 * dt));
    cam.updateProjectionMatrix();

    const g = group.current;
    if (g) {
      g.position.set(sim.x, sim.y, sim.z);
      g.lookAt(sim.x + f.x, sim.y, sim.z + f.z);
    }
    const spin = (sim.speed * dt) / 0.42;
    if (wheelL.current) wheelL.current.rotation.x += spin;
    if (wheelR.current) wheelR.current.rotation.x += spin;

    const near = treesNear(forest, sim.x, sim.z, 9);
    let bestSlug: string | null = null;
    let bestD = 9;
    for (const t of near) {
      const d = Math.hypot(t.x - sim.x, t.z - sim.z);
      if (d < bestD) {
        bestD = d;
        bestSlug = t.book.slug;
      }
    }
    if (bestSlug !== lastNearby.current) {
      lastNearby.current = bestSlug;
      setNearby(bestSlug, bestD);
    }

    for (const grove of forest.groves) {
      if (Math.hypot(grove.x - sim.x, grove.z - sim.z) < grove.radius) {
        markGrove(grove.genre);
      }
    }

    poseAcc.current += dt;
    if (poseAcc.current > 0.08) {
      poseAcc.current = 0;
      setPose(sim.x, sim.z, sim.yaw, sim.speed);
    }
  });

  return (
    <group ref={group}>
      <mesh position={[0, 0.38, 0.05]} castShadow={false}>
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
