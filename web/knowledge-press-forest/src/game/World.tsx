import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { BufferAttribute, BufferGeometry, CanvasTexture, Color, InstancedMesh, MeshStandardMaterial, Object3D, RepeatWrapping, SRGBColorSpace, TextureLoader } from "three";
import { ForestFloor, Sky, Sunlight, useGroundTexture } from "./Environment";
import { DAY_OVERRIDE } from "./daylight";
import { bookMatchesQuery, groveApproach, groveByGenre, type Forest } from "./forest";
import { disc, ribbon, type FlatMesh } from "./roads";
import { CorpusRedwood } from "./CorpusRedwood";
import { Mysterium } from "./Mysterium";
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
  const fogDensity = (season === "winter" ? 0.0077 : 0.0105) * (day ? DAY_OVERRIDE.fogDensityScale : 1);
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

      <GroveGrounds forest={forest} ground={groundColor} winter={season === "winter"} />
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

      <CorpusRedwood forest={forest} season={season} />
      {forest.exhibits.map((e) => (e.id === "mysterium" ? <Mysterium key={e.id} exhibit={e} /> : null))}

    </>
  );
}

function flatGeometry(m: FlatMesh) {
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(new Float32Array(m.pos), 3));
  g.setAttribute("normal", new BufferAttribute(new Float32Array(m.pos.length).map((_, i) => (i % 3 === 1 ? 1 : 0)), 3));
  g.setAttribute("uv", new BufferAttribute(new Float32Array(m.uv), 2));
  g.setIndex(m.index);
  g.computeBoundingSphere();
  return g;
}

// CC0 herringbone brick from ambientCG; see public/textures/road/CREDITS.md.
function brickMaterial() {
  const loader = new TextureLoader();
  const load = (map: string, srgb = false) => {
    const tex = loader.load(`textures/road/brick_${map}.jpg`);
    tex.wrapS = tex.wrapT = RepeatWrapping;
    tex.anisotropy = 8;
    if (srgb) tex.colorSpace = SRGBColorSpace;
    return tex;
  };
  return new MeshStandardMaterial({ map: load("color", true), normalMap: load("normal"), roughness: 0.9, metalness: 0 });
}

/**
 * Spokes sit lowest, the ring above them, junction plazas on top, so each join
 * is covered by the next layer instead of z-fighting.
 */
function Roads({ forest, circuit }: { forest: Forest; circuit: boolean }) {
  const geoms = useMemo(() => {
    const spokes: FlatMesh = { pos: [], uv: [], index: [] };
    const ring: FlatMesh = { pos: [], uv: [], index: [] };
    for (const line of forest.roadLines) {
      if (line.kind === "spoke") ribbon(line, 2.8, 0.035, spokes);
      else ribbon(line, 3.4, 0.045, ring);
    }
    for (const p of forest.plazas) disc(p.x, p.z, p.r, 0.055, ring);
    return { spokes: flatGeometry(spokes), ring: flatGeometry(ring) };
  }, [forest]);
  const materials = useMemo(() => {
    const spoke = brickMaterial();
    const ring = spoke.clone();
    return { spoke, ring };
  }, []);
  useEffect(() => () => { geoms.spokes.dispose(); geoms.ring.dispose(); }, [geoms]);
  useEffect(() => () => {
    materials.spoke.map?.dispose();
    materials.spoke.normalMap?.dispose();
    materials.spoke.dispose();
    materials.ring.dispose();
  }, [materials]);
  // Riding the ring warms it slightly so the tour's road reads as the lit path.
  materials.ring.emissive.set(circuit ? "#8fad86" : "#000000");
  materials.ring.emissiveIntensity = circuit ? 0.12 : 0;
  return (
    <group>
      <mesh geometry={geoms.spokes} material={materials.spoke} receiveShadow />
      <mesh geometry={geoms.ring} material={materials.ring} receiveShadow />
    </group>
  );
}

// Soft-edged disc alpha, shared by every grove's ground patch.
function useRadialAlpha() {
  const tex = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = c.height = 128;
    const ctx = c.getContext("2d")!;
    const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0, "#fff");
    g.addColorStop(0.72, "#fff");
    g.addColorStop(1, "#000");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 128, 128);
    return new CanvasTexture(c);
  }, []);
  useEffect(() => () => tex.dispose(), [tex]);
  return tex;
}

/** Each grove stands on its own tinted ground, fading out at the edge, so its extent reads at a glance. */
function GroveGrounds({ forest, ground, winter }: { forest: Forest; ground: Color; winter: boolean }) {
  const alpha = useRadialAlpha();
  return (
    <group>
      {forest.groves.map((g) => {
        const tint = new Color(winter ? "#c8d1ce" : ground).lerp(new Color(g.color), winter ? 0.25 : 0.4);
        return (
          <mesh key={g.genre} rotation={[-Math.PI / 2, 0, 0]} position={[g.x, 0.015, g.z]} receiveShadow>
            <circleGeometry args={[g.radius + 3, 48]} />
            <meshStandardMaterial color={tint} alphaMap={alpha} transparent opacity={0.6} depthWrite={false} roughness={1} />
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
      // Standing at the nearest answer, the trail has nowhere to lead.
      if (!found || bestD < 9) {
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
