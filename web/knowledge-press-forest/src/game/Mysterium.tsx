import { useFrame } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import {
  BoxGeometry,
  CanvasTexture,
  BufferGeometry,
  DodecahedronGeometry,
  EdgesGeometry,
  Group,
  IcosahedronGeometry,
  InstancedMesh,
  MeshStandardMaterial,
  Object3D,
  OctahedronGeometry,
  Quaternion,
  TetrahedronGeometry,
  Vector3,
} from "three";
import type { Exhibit } from "./exhibits";
import { makePlaqueTexture } from "./Signposts";
import { useGame } from "./store";

/**
 * Kepler's Mysterium Cosmographicum (1596): the five Platonic solids nested
 * between the six planetary shells, each solid inscribed in one shell and
 * circumscribing the next, in Kepler's order from Saturn inward. Shells are
 * armillary rings (three great circles), not spheres; every shell turns on its
 * own axis. An exhibit in a roadside glade (exhibits.ts).
 */

const SATURN_R = 3.4;
const CENTRE_Y = 3.6 + SATURN_R;

// Inradius / circumradius for each solid: the ratio from one planetary shell to the next.
const IN_OVER_CIRC = {
  cube: 1 / Math.sqrt(3),
  tetrahedron: 1 / 3,
  dodecahedron: 0.7946544722917661,
  icosahedron: 0.7946544722917661,
  octahedron: 1 / Math.sqrt(3),
} as const;

type SolidName = keyof typeof IN_OVER_CIRC;
const ORDER: SolidName[] = ["cube", "tetrahedron", "dodecahedron", "icosahedron", "octahedron"];

function solidGeometry(name: SolidName, circumradius: number): BufferGeometry {
  switch (name) {
    case "cube": {
      const side = (2 * circumradius) / Math.sqrt(3);
      return new BoxGeometry(side, side, side);
    }
    case "tetrahedron": return new TetrahedronGeometry(circumradius);
    case "dodecahedron": return new DodecahedronGeometry(circumradius);
    case "icosahedron": return new IcosahedronGeometry(circumradius);
    case "octahedron": return new OctahedronGeometry(circumradius);
  }
}

/** Edge segments of a solid as brass rods: one instanced cylinder per edge. */
function Rods({ name, radius, rod, material }: { name: SolidName; radius: number; rod: number; material: MeshStandardMaterial }) {
  const ref = useRef<InstancedMesh>(null);
  const edges = useMemo(() => {
    const g = solidGeometry(name, radius);
    const e = new EdgesGeometry(g);
    g.dispose();
    const p = e.getAttribute("position");
    const segs: [Vector3, Vector3][] = [];
    for (let i = 0; i < p.count; i += 2) segs.push([new Vector3().fromBufferAttribute(p, i), new Vector3().fromBufferAttribute(p, i + 1)]);
    e.dispose();
    return segs;
  }, [name, radius]);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const o = new Object3D();
    const up = new Vector3(0, 1, 0);
    edges.forEach(([a, b], i) => {
      const d = new Vector3().subVectors(b, a);
      o.position.copy(a).addScaledVector(d, 0.5);
      o.quaternion.copy(new Quaternion().setFromUnitVectors(up, d.clone().normalize()));
      o.scale.set(rod, d.length(), rod);
      o.updateMatrix();
      mesh.setMatrixAt(i, o.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }, [edges, rod]);
  return (
    <instancedMesh ref={ref} args={[undefined, material, edges.length]} castShadow>
      <cylinderGeometry args={[1, 1, 1, 6]} />
    </instancedMesh>
  );
}

/** A planetary shell as an armillary: three orthogonal great circles. */
function Shell({ radius, tube, material }: { radius: number; tube: number; material: MeshStandardMaterial }) {
  return (
    <group>
      {[[0, 0, 0], [Math.PI / 2, 0, 0], [0, Math.PI / 2, 0]].map((r, i) => (
        <mesh key={i} rotation={r as [number, number, number]} material={material} castShadow>
          <torusGeometry args={[radius, tube, 6, 72]} />
        </mesh>
      ))}
    </group>
  );
}

const KEPLER_BODY =
  "The five Platonic solids, nested between the six planetary spheres as Johannes Kepler " +
  "proposed in 1596. Each solid fits inside one planet's sphere and around the next. From the " +
  "outside in: Saturn, cube, Jupiter, tetrahedron, Mars, dodecahedron, Earth, icosahedron, " +
  "Venus, octahedron, Mercury, with the Sun at the center. The spacing here is Kepler's own: " +
  "each sphere is the inner radius of the solid around it. He was wrong about the planets, and " +
  "right that geometry could be asked the question.";

/** Between the sculpture and the road, facing the road, so it reads with the sculpture behind it. */
function KeplerPlaque({ exhibit: e }: { exhibit: Exhibit }) {
  const tex = useMemo<CanvasTexture>(() => makePlaqueTexture("Mysterium Cosmographicum", "Johannes Kepler · 1596", KEPLER_BODY), []);
  useEffect(() => () => tex.dispose(), [tex]);
  const dx = e.roadX - e.x, dz = e.roadZ - e.z;
  const d = Math.hypot(dx, dz) || 1;
  const x = (dx / d) * (e.obstacle + 1.9), z = (dz / d) * (e.obstacle + 1.9);
  return (
    <group position={[x, 0, z]} rotation={[0, Math.atan2(dx, dz), 0]}>
      {[-1.25, 1.25].map((px) => (
        <mesh key={px} position={[px, 0.8, 0]}>
          <cylinderGeometry args={[0.07, 0.09, 1.6, 6]} />
          <meshStandardMaterial color="#4a3a2a" roughness={0.9} />
        </mesh>
      ))}
      {/* Tilted back like a lectern so it reads from the cart. */}
      <mesh position={[0, 1.55, 0.05]} rotation={[-0.35, 0, 0]}>
        <boxGeometry args={[3.0, 1.5, 0.06]} />
        <meshStandardMaterial map={tex} roughness={0.7} />
      </mesh>
    </group>
  );
}

export function Mysterium({ exhibit }: { exhibit: Exhibit }) {
  const R = exhibit.obstacle;
  const day = useGame((s) => s.timeOfDay === "day");
  const materials = useMemo(() => ({
    brass: new MeshStandardMaterial({ color: "#c9a24a", metalness: 0.65, roughness: 0.32 }),
    silver: new MeshStandardMaterial({ color: "#cfd6dc", metalness: 0.6, roughness: 0.3 }),
    stone: new MeshStandardMaterial({ color: "#7d776c", roughness: 0.88 }),
    sun: new MeshStandardMaterial({ color: "#ffd27a", emissive: "#ffb84a", emissiveIntensity: 1.6, roughness: 0.4 }),
  }), []);
  useEffect(() => () => Object.values(materials).forEach((m) => m.dispose()), [materials]);
  useEffect(() => {
    // Brass glows faintly at night so the sculpture still reads from the groves.
    materials.brass.emissive.set(day ? "#000000" : "#6b4a12");
    materials.brass.emissiveIntensity = day ? 0 : 0.35;
  }, [day, materials]);

  // Kepler's radii: each shell is the inradius of the solid outside it.
  const layers = useMemo(() => {
    const out: { solid: SolidName; shellR: number }[] = [];
    let r = SATURN_R;
    for (const solid of ORDER) {
      out.push({ solid, shellR: r });
      r *= IN_OVER_CIRC[solid];
    }
    return { out, mercury: r };
  }, []);

  const shells = useRef<(Group | null)[]>([]);
  useFrame((_, delta) => {
    const s = useGame.getState();
    if (!s.preferences.motion || s.paused) return;
    const dt = Math.min(delta, 0.1);
    shells.current.forEach((g, i) => {
      if (!g) return;
      // Alternate direction and tilt the axis per shell, slower outside, like the planets.
      const w = (0.05 + i * 0.035) * (i % 2 ? -1 : 1);
      g.rotation.y += w * dt;
      g.rotation.x += w * 0.37 * dt;
    });
  });

  return (
    <group position={[exhibit.x, 0, exhibit.z]}>
      <KeplerPlaque exhibit={exhibit} />
      {/* Stepped plinth; the cart collides with its lowest step (exhibit.obstacle). */}
      <mesh position={[0, 0.25, 0]} material={materials.stone} castShadow receiveShadow>
        <cylinderGeometry args={[R - 0.2, R, 0.5, 8]} />
      </mesh>
      <mesh position={[0, 0.75, 0]} material={materials.stone} castShadow receiveShadow>
        <cylinderGeometry args={[1.7, 1.9, 0.5, 8]} />
      </mesh>
      <mesh position={[0, 2.1, 0]} material={materials.stone} castShadow>
        <cylinderGeometry args={[0.32, 0.5, 2.2, 8]} />
      </mesh>
      <group position={[0, CENTRE_Y, 0]}>
        {layers.out.map(({ solid, shellR }, i) => (
          <group key={solid} ref={(g) => { shells.current[i] = g; }}>
            <Shell radius={shellR} tube={Math.max(0.018, shellR * 0.012)} material={materials.silver} />
            <Rods name={solid} radius={shellR} rod={Math.max(0.02, shellR * 0.016)} material={materials.brass} />
          </group>
        ))}
        <group ref={(g) => { shells.current[layers.out.length] = g; }}>
          <Shell radius={layers.mercury} tube={0.015} material={materials.silver} />
        </group>
        <mesh material={materials.sun}>
          <icosahedronGeometry args={[Math.max(0.12, layers.mercury * 0.45), 1]} />
        </mesh>
        {!day ? <pointLight color="#ffc56b" intensity={9} distance={22} decay={2} /> : null}
      </group>
    </group>
  );
}
