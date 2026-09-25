import { useFrame } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { BackSide, BufferGeometry, CanvasTexture, Color, DirectionalLight, DoubleSide, Float32BufferAttribute, IcosahedronGeometry, InstancedMesh, MeshStandardMaterial, Object3D, RepeatWrapping, SRGBColorSpace } from "three";
import type { Forest } from "./forest";
import { mulberry32 } from "./math";
import type { SeasonName } from "./seasons";
import { sim } from "./sim";
import { useGame } from "./store";

/** A camera-centred sky: no distant sphere edge when exploring the outer groves. */
export function Sky({ day, season }: { day: boolean; season: SeasonName }) {
  const dome = useRef<Object3D>(null);
  const uniforms = useMemo(() => ({
    zenith: { value: new Color(day ? (season === "winter" ? "#7496af" : "#427fae") : "#071224") },
    horizon: { value: new Color(day ? (season === "autumn" ? "#e8c8a1" : "#d1e0d6") : "#263c51") },
    daylight: { value: day ? 1 : 0 },
  }), [day, season]);
  const stars = useMemo(() => {
    const random = mulberry32(917);
    const positions = new Float32Array(750 * 3);
    for (let i = 0; i < 750; i++) {
      const y = 0.12 + random() * 0.88;
      const angle = random() * Math.PI * 2;
      const r = Math.sqrt(1 - y * y);
      positions.set([Math.cos(angle) * r * 240, y * 240, Math.sin(angle) * r * 240], i * 3);
    }
    return positions;
  }, []);
  useFrame(({ camera }) => dome.current?.position.copy(camera.position));
  return (
    <group ref={dome}>
      <mesh renderOrder={-10}>
        <sphereGeometry args={[280, 32, 16]} />
        <shaderMaterial side={BackSide} depthWrite={false} uniforms={uniforms}
          vertexShader={`varying vec3 direction;
            void main() { direction = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`}
          fragmentShader={`varying vec3 direction;
            uniform vec3 zenith; uniform vec3 horizon; uniform float daylight;
            void main() {
              vec3 d = normalize(direction);
              vec3 col = mix(horizon, zenith, pow(max(d.y, 0.0), 0.55));
              float sun = max(dot(d, normalize(vec3(40., 55., 18.))), 0.0);
              col += vec3(1., .8, .5) * pow(sun, 32.) * .28 * daylight;
              col += mix(vec3(.55, .65, .8), vec3(1., .9, .65), daylight) * smoothstep(.9992, .9997, sun);
              gl_FragColor = vec4(col, 1.);
              #include <tonemapping_fragment>
              #include <colorspace_fragment>
            }`} />
      </mesh>
      {!day && <points>
        <bufferGeometry><bufferAttribute attach="attributes-position" args={[stars, 3]} /></bufferGeometry>
        <pointsMaterial color="#e4edff" size={0.65} sizeAttenuation transparent opacity={0.8} depthWrite={false} fog={false} />
      </points>}
    </group>
  );
}

/** Tablets and phones: fewer pixels and a smaller shadow map keep the frame rate up. */
export const COARSE_POINTER = typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
/** Phones: a touch screen under 640px on its short side. */
export const PHONE = COARSE_POINTER && Math.min(screen.width, screen.height) < 640;

/** Keep one modest shadow map around the cart instead of covering the entire forest. */
export function Sunlight({ day, detail }: { day: boolean; detail: boolean }) {
  const light = useRef<DirectionalLight>(null);
  const target = useMemo(() => new Object3D(), []);
  useFrame(() => {
    if (!light.current) return;
    target.position.set(sim.x, 0, sim.z);
    light.current.position.set(sim.x + 40, 55, sim.z + 18);
    target.updateMatrixWorld();
  });
  return <>
    <primitive object={target} />
    <directionalLight ref={light} target={target} color={day ? "#fff0d2" : "#94b7e5"}
      intensity={day ? 2.4 : 0.55} castShadow={detail}
      shadow-mapSize={COARSE_POINTER ? [1024, 1024] : [2048, 2048]} shadow-camera-left={-40} shadow-camera-right={40}
      shadow-camera-top={40} shadow-camera-bottom={-40} shadow-camera-near={1} shadow-camera-far={160}
      shadow-bias={-0.0002} shadow-normalBias={0.08} />
  </>;
}

export function useGroundTexture() {
  const texture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 256;
    const ctx = canvas.getContext("2d")!;
    const random = mulberry32(372);
    ctx.fillStyle = "#b2b6a1";
    ctx.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 8000; i++) {
      const value = 80 + Math.floor(random() * 130);
      ctx.fillStyle = `rgba(${value},${value},${value * 0.85},0.25)`;
      ctx.fillRect(random() * 256, random() * 256, 1 + random() * 4, 1 + random() * 3);
    }
    const result = new CanvasTexture(canvas);
    result.wrapS = result.wrapT = RepeatWrapping;
    result.repeat.set(70, 70);
    result.colorSpace = SRGBColorSpace;
    return result;
  }, []);
  useEffect(() => () => texture.dispose(), [texture]);
  return texture;
}

/** A lumpy, faceted rock: an icosahedron whose vertices are pushed in and out by a hash of their direction. */
function rockGeometry(seed: number) {
  const g = new IcosahedronGeometry(1, 1);
  const p = g.getAttribute("position");
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    // Same direction, same push: shared corners of adjacent faces stay welded.
    const h = Math.sin(x * 12.9898 + y * 78.233 + z * 37.719 + seed) * 43758.5453;
    const k = 0.78 + 0.36 * (h - Math.floor(h));
    p.setXYZ(i, x * k, y * k * 0.72, z * k);
  }
  g.computeVertexNormals();
  return g;
}

/** A grass tuft: three tapered blades crossed at 60 degrees, bending a little outward. */
function tuftGeometry() {
  const pos: number[] = [];
  for (let b = 0; b < 3; b++) {
    const a = (b * Math.PI) / 3, cx = Math.cos(a), cz = Math.sin(a);
    const w = 0.09, lean = 0.12 * (b % 2 ? 1 : -1);
    // base-left, base-right, tip (leaning), as one triangle, plus a mid pair for shape
    pos.push(-cx * w, 0, -cz * w, cx * w, 0, cz * w, cx * lean, 1, cz * lean);
    pos.push(-cx * w * 0.6, 0.45, -cz * w * 0.6, cx * w * 0.6, 0.45, cz * w * 0.6, cx * lean, 1, cz * lean);
  }
  const g = new BufferGeometry();
  g.setAttribute("position", new Float32BufferAttribute(pos, 3));
  g.computeVertexNormals();
  return g;
}

export function ForestFloor({ forest, season }: { forest: Forest; season: SeasonName }) {
  const grass = useRef<InstancedMesh>(null);
  const rocks = useRef<InstancedMesh>(null);
  const rockGeo = useMemo(() => rockGeometry(3.7), []);
  const tuftGeo = useMemo(() => tuftGeometry(), []);
  const sway = useMemo(() => ({ value: 0 }), []);
  const grassMat = useMemo(() => {
    const m = new MeshStandardMaterial({ side: DoubleSide, roughness: 1 });
    m.onBeforeCompile = (shader) => {
      shader.uniforms.swayTime = sway;
      shader.vertexShader = "uniform float swayTime;\n" + shader.vertexShader.replace("#include <begin_vertex>", `
        #include <begin_vertex>
        float ph = instanceMatrix[3].x * .21 + instanceMatrix[3].z * .17;
        transformed.x += sin(swayTime * 2.1 + ph) * .14 * position.y;
        transformed.z += cos(swayTime * 1.7 + ph) * .08 * position.y;
      `);
    };
    m.customProgramCacheKey = () => "forest-grass-sway-v1";
    return m;
  }, [sway]);
  useEffect(() => () => { rockGeo.dispose(); tuftGeo.dispose(); grassMat.dispose(); }, [rockGeo, tuftGeo, grassMat]);
  useFrame((_, delta) => {
    const s = useGame.getState();
    if (s.preferences.motion && !s.paused) sway.value += Math.min(delta, 0.1);
  });
  useLayoutEffect(() => {
    if (!grass.current || !rocks.current) return;
    const random = mulberry32(247);
    const dummy = new Object3D();
    const color = new Color();
    let blades = 0;
    let stones = 0;
    const placeRock = (x: number, z: number, size: number) => {
      dummy.position.set(x, size * 0.18, z); // half-sunk
      dummy.rotation.set(random() * 0.6, random() * Math.PI * 2, random() * 0.6);
      dummy.scale.set(size * (0.8 + random() * 0.5), size * (0.6 + random() * 0.5), size * (0.8 + random() * 0.5));
      dummy.updateMatrix();
      rocks.current!.setMatrixAt(stones, dummy.matrix);
      color.set(season === "winter" ? "#cdd5d5" : "#7c8075").offsetHSL(0, 0, (random() - 0.5) * 0.12);
      rocks.current!.setColorAt(stones++, color);
    };
    for (const tree of forest.trees) {
      for (let i = 0; i < 24; i++) {
        const angle = random() * Math.PI * 2;
        const radius = tree.trunkRadius + 1.3 + random() * 6;
        const x = tree.x + Math.cos(angle) * radius;
        const z = tree.z + Math.sin(angle) * radius;
        // Leave the carriage paths clear.
        if (forest.roads.some((r) => {
          const dx = r.bx - r.ax, dz = r.bz - r.az;
          const t = Math.max(0, Math.min(1, ((x - r.ax) * dx + (z - r.az) * dz) / (dx * dx + dz * dz)));
          return Math.hypot(x - r.ax - dx * t, z - r.az - dz * t) < 2;
        })) continue;
        // A quarter of the floor litter is stone, the rest grass.
        if (random() < 0.25) {
          placeRock(x, z, 0.18 + random() * 0.32);
          continue;
        }
        const height = 0.22 + random() * 0.45;
        dummy.position.set(x, 0, z);
        dummy.rotation.set(0, angle, 0);
        dummy.scale.set(1 + random() * 0.6, height, 1 + random() * 0.6);
        dummy.updateMatrix();
        grass.current.setMatrixAt(blades, dummy.matrix);
        color.set(season === "winter" ? "#c1bca1" : season === "autumn" ? "#9a793e" : "#637747");
        color.offsetHSL(0, 0, (random() - 0.5) * 0.16);
        grass.current.setColorAt(blades++, color);
      }
    }
    grass.current.count = blades;
    rocks.current.count = stones;
    for (const mesh of [grass.current, rocks.current]) {
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.computeBoundingSphere();
    }
  }, [forest, season]);
  return <>
    <instancedMesh ref={grass} args={[tuftGeo, grassMat, forest.trees.length * 24]} receiveShadow />
    <instancedMesh ref={rocks} args={[rockGeo, undefined, forest.trees.length * 24]} receiveShadow castShadow>
      <meshStandardMaterial flatShading roughness={0.95} />
    </instancedMesh>
  </>;
}
