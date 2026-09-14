import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { BackSide, Color, InstancedMesh, Object3D } from "three";
import { bookMatchesQuery, groveApproach, groveByGenre, type Forest } from "./forest";
import { SEASONS, type SeasonName } from "./seasons";
import { sim } from "./sim";
import { useGame } from "./store";

const dummy = new Object3D();
const TRAIL_N = 20;

export function World({ forest, season }: { forest: Forest; season: SeasonName }) {
  const pal = SEASONS[season];
  const fogColor = pal.fog;
  const skyColor = useMemo(() => new Color(pal.sky), [pal.sky]);
  const selectedGrove = useGame((s) => s.selectedGrove);
  const query = useGame((s) => s.query);
  const travelMode = useGame((s) => s.travelMode);

  return (
    <>
      <color attach="background" args={[skyColor]} />
      <fogExp2 attach="fog" args={[fogColor, season === "winter" ? 0.011 : 0.015]} />
      <hemisphereLight color={pal.ambient} groundColor={pal.ground} intensity={0.78} />
      <directionalLight position={[40, 55, 18]} intensity={0.88} color={pal.sun} />
      <directionalLight position={[-30, 20, -40]} intensity={0.2} color="#8aa0b8" />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <circleGeometry args={[forest.worldRadius + 30, 64]} />
        <meshStandardMaterial color={pal.ground} roughness={0.96} metalness={0} />
      </mesh>

      <Roads forest={forest} circuit={travelMode === "circuit"} />
      <LanternTrail forest={forest} selectedGrove={selectedGrove} query={query} />

      {forest.groves.map((g) => {
        const on = selectedGrove === g.genre;
        return (
          <group key={g.genre} position={[g.x, 0, g.z]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
              <circleGeometry args={[Math.min(g.radius * 0.55, 16), 24]} />
              <meshStandardMaterial color={pal.ground} roughness={1} />
            </mesh>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.06, 0]}>
              <ringGeometry args={[2.2, on ? 3.1 : 2.7, 20]} />
              <meshBasicMaterial color={g.color} transparent opacity={on ? 0.92 : 0.55} />
            </mesh>
          </group>
        );
      })}

      {forest.circuit.map((wp) => {
        const g = groveByGenre(forest, wp.genre);
        return (
          <mesh key={wp.genre} position={[wp.x, 0.55, wp.z]}>
            <cylinderGeometry args={[0.22, 0.28, 1.1, 6]} />
            <meshStandardMaterial
              color={g?.color ?? "#d7d1c4"}
              emissive={g?.color ?? "#d7d1c4"}
              emissiveIntensity={selectedGrove === wp.genre ? 0.55 : 0.12}
              roughness={0.55}
            />
          </mesh>
        );
      })}

      <mesh position={[0, 0.55, 0]}>
        <cylinderGeometry args={[1.55, 1.85, 0.38, 8]} />
        <meshStandardMaterial color="#6a655c" roughness={0.85} />
      </mesh>
      <mesh position={[0, 0.95, 0]}>
        <boxGeometry args={[1.15, 0.52, 0.16]} />
        <meshStandardMaterial color="#d7d1c4" roughness={0.55} />
      </mesh>

      <mesh>
        <sphereGeometry args={[forest.worldRadius * 1.45, 16, 12]} />
        <meshBasicMaterial color={pal.sky} side={BackSide} />
      </mesh>
    </>
  );
}

function Roads({ forest, circuit }: { forest: Forest; circuit: boolean }) {
  return (
    <group>
      {forest.roads.map((r, i) => {
        const dx = r.bx - r.ax;
        const dz = r.bz - r.az;
        const len = Math.hypot(dx, dz);
        if (len < 0.4) return null;
        const lit = circuit && r.kind === "ring";
        return (
          <mesh
            key={i}
            position={[(r.ax + r.bx) / 2, lit ? 0.055 : 0.04, (r.az + r.bz) / 2]}
            rotation={[0, Math.atan2(dx, dz), 0]}
          >
            <boxGeometry args={[r.kind === "ring" ? 2.05 : 1.45, 0.05, len]} />
            <meshStandardMaterial
              color={lit ? "#6e5a3d" : r.kind === "ring" ? "#5c4a36" : "#4e3f2d"}
              roughness={1}
              emissive={lit ? "#8fad86" : "#000000"}
              emissiveIntensity={lit ? 0.18 : 0}
            />
          </mesh>
        );
      })}
    </group>
  );
}

function LanternTrail({
  forest,
  selectedGrove,
  query,
}: {
  forest: Forest;
  selectedGrove: string | null;
  query: string;
}) {
  const ref = useRef<InstancedMesh>(null);

  const target = useMemo(() => {
    if (selectedGrove) {
      const g = groveByGenre(forest, selectedGrove);
      if (g) {
        const wp = groveApproach(g);
        return { x: wp.x, z: wp.z, mode: "grove" as const };
      }
    }
    if (!query.trim()) return null;
    return { mode: "query" as const, q: query };
  }, [forest, selectedGrove, query]);

  useFrame(() => {
    const mesh = ref.current;
    if (!mesh) return;
    let tx = 0;
    let tz = 0;
    if (!target) {
      mesh.count = 0;
      return;
    }
    if (target.mode === "grove") {
      tx = target.x;
      tz = target.z;
    } else {
      let bestD = Infinity;
      let found = false;
      for (const t of forest.trees) {
        if (!bookMatchesQuery(t.book, target.q)) continue;
        const d = Math.hypot(t.x - sim.x, t.z - sim.z);
        if (d < bestD) {
          bestD = d;
          tx = t.x;
          tz = t.z;
          found = true;
        }
      }
      if (!found) {
        mesh.count = 0;
        return;
      }
    }
    for (let i = 0; i < TRAIL_N; i++) {
      const t = (i + 1) / (TRAIL_N + 1);
      dummy.position.set(sim.x + (tx - sim.x) * t, 0.28, sim.z + (tz - sim.z) * t);
      dummy.scale.setScalar(0.16 + (i % 3 === 0 ? 0.06 : 0));
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.count = TRAIL_N;
  });

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, TRAIL_N]} frustumCulled={false}>
      <sphereGeometry args={[1, 8, 6]} />
      <meshBasicMaterial color="#f3e6c2" transparent opacity={0.72} />
    </instancedMesh>
  );
}
