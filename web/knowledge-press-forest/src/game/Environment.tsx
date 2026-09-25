import { useFrame } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { BackSide, CanvasTexture, Color, DirectionalLight, DoubleSide, InstancedMesh, Object3D, RepeatWrapping, SRGBColorSpace } from "three";
import type { Forest } from "./forest";
import { mulberry32 } from "./math";
import type { SeasonName } from "./seasons";
import { sim } from "./sim";

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
      shadow-mapSize={[2048, 2048]} shadow-camera-left={-40} shadow-camera-right={40}
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

export function ForestFloor({ forest, season }: { forest: Forest; season: SeasonName }) {
  const grass = useRef<InstancedMesh>(null);
  const rocks = useRef<InstancedMesh>(null);
  useLayoutEffect(() => {
    if (!grass.current || !rocks.current) return;
    const random = mulberry32(247);
    const dummy = new Object3D();
    const color = new Color();
    let blades = 0;
    let stones = 0;
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
        const height = 0.18 + random() * 0.5;
        dummy.position.set(x, height / 2, z);
        dummy.rotation.set(0, angle, (random() - 0.5) * 0.4);
        dummy.scale.set(0.3 + random() * 0.5, height, 1);
        dummy.updateMatrix();
        grass.current.setMatrixAt(blades, dummy.matrix);
        color.set(season === "winter" ? "#c1bca1" : season === "autumn" ? "#9a793e" : "#637747");
        color.offsetHSL(0, 0, (random() - 0.5) * 0.16);
        grass.current.setColorAt(blades++, color);
        if (i % 8 === 0) {
          dummy.position.set(x + 0.7, 0.12, z);
          dummy.scale.set(0.3 + random() * 0.4, 0.2, 0.25 + random() * 0.3);
          dummy.updateMatrix();
          rocks.current.setMatrixAt(stones++, dummy.matrix);
        }
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
    <instancedMesh ref={grass} args={[undefined, undefined, forest.trees.length * 24]} receiveShadow>
      <coneGeometry args={[0.5, 1, 3, 1, true]} />
      <meshStandardMaterial side={DoubleSide} roughness={1} />
    </instancedMesh>
    <instancedMesh ref={rocks} args={[undefined, undefined, forest.trees.length * 3]} receiveShadow castShadow>
      <icosahedronGeometry args={[1, 0]} />
      <meshStandardMaterial color={season === "winter" ? "#cdd5d5" : "#7c8075"} roughness={1} />
    </instancedMesh>
  </>;
}
