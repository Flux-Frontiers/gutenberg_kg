import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Color, InstancedMesh, Object3D } from "three";
import { ForestFloor, Sky, Sunlight, useGroundTexture } from "./Environment";
import { DAY_OVERRIDE } from "./daylight";
import { bookMatchesQuery, groveApproach, groveByGenre, type Forest } from "./forest";
import { Signposts } from "./Signposts";
import { SEASONS, type SeasonName } from "./seasons";
import { sim } from "./sim";
import { useGame } from "./store";

const dummy = new Object3D();
const TRAIL_N = 20;

export function World({ forest, season }: { forest: Forest; season: SeasonName }) {
  const pal = SEASONS[season];
  const timeOfDay = useGame((s) => s.timeOfDay);
  const day = timeOfDay === "day";
  const skyColor = useMemo(
    () => new Color(day ? DAY_OVERRIDE.sky : pal.sky),
    [day, pal.sky],
  );
  const fogColor = day ? DAY_OVERRIDE.fog : pal.fog;
  const fogDensity = (season === "winter" ? 0.011 : 0.015) * (day ? DAY_OVERRIDE.fogDensityScale : 1);
  const ambientColor = day ? DAY_OVERRIDE.ambient : pal.ambient;
  const hemiIntensity = 0.78 * (day ? DAY_OVERRIDE.hemiIntensity : 1);
  const detail = useGame((s) => s.preferences.detail);
  const groundTexture = useGroundTexture();
  const groundColor = useMemo(() => {
    const c = new Color(pal.ground);
    if (day) c.offsetHSL(0, -0.08, DAY_OVERRIDE.groundLightness);
    return c;
  }, [day, pal.ground]);
  const selectedGrove = useGame((s) => s.selectedGrove);
  const query = useGame((s) => s.query);
  const searchPick = useGame((s) => s.searchPick);
  const travelMode = useGame((s) => s.travelMode);

  return (
    <>
      <color attach="background" args={[skyColor]} />
      <fogExp2 attach="fog" args={[fogColor, fogDensity]} />
      <hemisphereLight color={ambientColor} groundColor={groundColor} intensity={hemiIntensity} />
      <Sunlight day={day} detail={detail} />
      <Sky day={day} season={season} />
      <directionalLight position={[-30, 20, -40]} intensity={0.2} color="#8aa0b8" />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <circleGeometry args={[forest.worldRadius + 30, 64]} />
        <meshStandardMaterial color={season === "winter" ? "#c8d1ce" : groundColor} map={groundTexture} bumpMap={groundTexture} bumpScale={0.09} roughness={0.96} metalness={0} />
      </mesh>

      <Roads forest={forest} circuit={travelMode === "circuit"} />
      {detail && <ForestFloor forest={forest} season={season} />}
      <LanternTrail forest={forest} selectedGrove={selectedGrove} query={query} searchPick={searchPick} />
      <Signposts forest={forest} />

      {forest.groves.map((g) => {
        const on = selectedGrove === g.genre;
        return (
          <group key={g.genre} position={[g.x, 0, g.z]}>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.06, 0]}>
              <ringGeometry args={[2.2, on ? 3.1 : 2.7, 20]} />
              <meshBasicMaterial color={g.color} transparent opacity={on ? 0.92 : 0.55} />
            </mesh>
          </group>
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
            receiveShadow
            key={i}
            position={[(r.ax + r.bx) / 2, lit ? 0.055 : 0.04, (r.az + r.bz) / 2]}
            rotation={[0, Math.atan2(dx, dz), 0]}
          >
            <boxGeometry args={[r.kind === "ring" ? 3.2 : 2.6, 0.05, len]} />
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
  searchPick,
}: {
  forest: Forest;
  selectedGrove: string | null;
  query: string;
  searchPick: string | null;
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
    const picked = searchPick ? forest.trees.find((t) => t.book.slug === searchPick) : undefined;
    if (picked) return { x: picked.x, z: picked.z, mode: "grove" as const };
    if (!query.trim()) return null;
    return { mode: "query" as const, q: query };
  }, [forest, selectedGrove, query, searchPick]);

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
