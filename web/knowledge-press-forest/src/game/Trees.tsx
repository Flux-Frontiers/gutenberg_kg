import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { BufferAttribute, BufferGeometry, Color, DoubleSide, InstancedMesh, MeshDepthMaterial, MeshStandardMaterial, Object3D, RepeatWrapping, RGBADepthPacking, Shape, ShapeGeometry, SRGBColorSpace, TextureLoader, Vector2 } from "three";
import { useGame } from "./store";
import type { Forest } from "./forest";
import { bookMatchesQuery } from "./forest";
import { SEASONS, type SeasonName } from "./seasons";
import { leafOutline, SPECIES, type LeafShape, type Species } from "./species";

const dummy = new Object3D();
const color = new Color();
const white = new Color("#ffffff");

// CC0 bark from ambientCG; see public/textures/bark/CREDITS.md.
function barkMaterial(species: Species) {
  const loader = new TextureLoader();
  const load = (map: string, srgb = false) => {
    const tex = loader.load(`textures/bark/${species.name}_${map}.jpg`);
    tex.wrapS = tex.wrapT = RepeatWrapping;
    tex.anisotropy = 8;
    if (srgb) tex.colorSpace = SRGBColorSpace;
    return tex;
  };
  return new MeshStandardMaterial({
    map: load("color", true),
    normalMap: load("normal"),
    roughness: 0.92,
    vertexColors: true,
    metalness: 0,
  });
}

function leafGeometry(leaf: LeafShape) {
  const g = new ShapeGeometry(new Shape(leafOutline(leaf).map(([x, y]) => new Vector2(x, y))));
  g.computeVertexNormals();
  return g;
}

function keepLeaf(i: number, density: number): boolean {
  if (density >= 0.999) return true;
  // Mix adjacent indices; the old sequence kept almost every early winter leaf.
  const h = ((Math.imul(i + 1, 1664525) ^ Math.imul(i + 7, 1013904223)) >>> 0) / 4294967296;
  return h < density;
}

export function Trees({
  forest,
  season,
  query,
}: {
  forest: Forest;
  season: SeasonName;
  query: string;
}) {
  const ringRef = useRef<InstancedMesh>(null);
  const palette = SEASONS[season];
  const q = query.trim();
  const wind = useMemo(() => ({ value: 0 }), []);
  const windStrength = useMemo(() => ({ value: 0 }), []);
  const materials = useMemo(() => {
    const leaf = new MeshStandardMaterial({ roughness: 0.8, side: DoubleSide });
    const depth = new MeshDepthMaterial({ depthPacking: RGBADepthPacking, side: DoubleSide });
    for (const material of [leaf, depth]) {
      material.onBeforeCompile = (shader) => {
        shader.uniforms.windTime = wind;
        shader.uniforms.windStrength = windStrength;
        shader.vertexShader = "uniform float windTime; uniform float windStrength;\n" + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace("#include <begin_vertex>", `
          #include <begin_vertex>
          float phase = instanceMatrix[3].x * .31 + instanceMatrix[3].z * .27;
          transformed.x += sin(windTime * 1.4 + phase) * .12 * windStrength * (position.y + 1.0);
          transformed.z += cos(windTime + phase) * .06 * windStrength;
        `);
      };
      material.customProgramCacheKey = () => "forest-leaf-wind-v1";
    }
    return { leaf, depth };
  }, [wind, windStrength]);
  useEffect(() => () => { materials.leaf.dispose(); materials.depth.dispose(); }, [materials]);

  const bark = useMemo(() => forest.bark.map((b) => {
    const g = new BufferGeometry();
    g.setAttribute("position", new BufferAttribute(b.pos, 3));
    g.setAttribute("normal", new BufferAttribute(b.normal, 3));
    g.setAttribute("uv", new BufferAttribute(b.uv, 2));
    g.setAttribute("color", new BufferAttribute(new Float32Array(b.count * 3), 3));
    g.setIndex(new BufferAttribute(b.index, 1));
    g.computeBoundingSphere();
    return g;
  }), [forest]);
  const barkMats = useMemo(() => SPECIES.map(barkMaterial), []);
  const leafGeoms = useMemo(() => SPECIES.map((s) => leafGeometry(s.leaf)), []);
  // Leaf indices per species, one instanced mesh each.
  const leafSets = useMemo(() => SPECIES.map((_, si) => {
    const out: number[] = [];
    for (let i = 0; i < forest.leaves.count; i++) if (forest.leaves.species[i] === si) out.push(i);
    return out;
  }), [forest]);
  const leafRefs = useRef<(InstancedMesh | null)[]>([]);
  useEffect(() => () => bark.forEach((g) => g.dispose()), [bark]);
  useEffect(() => () => leafGeoms.forEach((g) => g.dispose()), [leafGeoms]);
  useEffect(() => () => {
    for (const m of barkMats) {
      m.map?.dispose();
      m.normalMap?.dispose();
      m.dispose();
    }
  }, [barkMats]);
  useFrame((_, delta) => {
    const s = useGame.getState();
    windStrength.value = s.preferences.motion ? 1 : 0;
    if (s.preferences.motion && !s.paused) wind.value += Math.min(delta, 0.1);
  });

  const match = useMemo(() => {
    if (!q) return null;
    const set = new Set<number>();
    forest.trees.forEach((t, i) => {
      if (bookMatchesQuery(t.book, q)) set.add(i);
    });
    return set;
  }, [forest, q]);

  useLayoutEffect(() => {
    // The season's wood colour tints the photo bark rather than replacing it.
    const colors = bark.map((g) => g.getAttribute("color") as BufferAttribute);
    const tint = new Color(palette.wood).lerp(white, 0.55);
    for (let ti = 0; ti < forest.trees.length; ti++) {
      const tree = forest.trees[ti]!;
      const attr = colors[tree.species]!;
      color.copy(tint);
      if (match && !match.has(ti)) color.multiplyScalar(0.45);
      for (let k = 0; k < tree.woodCount; k++) attr.setXYZ(tree.woodStart + k, color.r, color.g, color.b);
    }
    for (const attr of colors) attr.needsUpdate = true;
  }, [forest, bark, palette.wood, match]);

  useLayoutEffect(() => {
    const { pos, scale, tint, treeIndex } = forest.leaves;
    leafSets.forEach((set, si) => {
      const mesh = leafRefs.current[si];
      if (!mesh) return;
      const [dh, ds, dl] = SPECIES[si]!.foliageShift;
      const foliage = palette.foliage.map((hex) => new Color(hex).offsetHSL(dh, ds, dl));
      for (let n = 0; n < set.length; n++) {
        const i = set[n]!;
        const treeI = treeIndex[i]!;
        const dim = match && !match.has(treeI);
        const visible = keepLeaf(i, palette.density) && !dim;
        dummy.position.set(pos[i * 3]!, pos[i * 3 + 1]!, pos[i * 3 + 2]!);
        const s = visible ? 1 : match && dim ? 0.15 : 0;
        dummy.scale.set(scale[i * 3]! * s, scale[i * 3 + 1]! * s, scale[i * 3 + 2]! * s);
        dummy.rotation.set(
          ((i * 1.7) % 1.1) - 0.45,
          (i * 2.399) % 6.2832,
          0.55 + ((i * 0.31) % 0.7),
        );
        dummy.updateMatrix();
        mesh.setMatrixAt(n, dummy.matrix);
        color.copy(foliage[tint[i]! % foliage.length]!);
        if (match && match.has(treeI)) color.offsetHSL(0, 0.05, 0.08);
        mesh.setColorAt(n, color);
      }
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.count = set.length;
    });
  }, [forest, leafSets, palette, match]);

  useLayoutEffect(() => {
    const mesh = ringRef.current;
    if (!mesh) return;
    forest.trees.forEach((t, i) => {
      dummy.position.set(t.x, 0.05, t.z);
      dummy.rotation.set(-Math.PI / 2, 0, 0);
      const on = match ? match.has(i) : false;
      dummy.scale.set(on ? t.trunkRadius * 4.2 : 0.0001, on ? t.trunkRadius * 4.2 : 0.0001, 1);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      color.set(t.color);
      mesh.setColorAt(i, color);
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [forest, match]);

  return (
    <group>
      {bark.map((g, si) => (
        <mesh key={`bark-${si}`} geometry={g} material={barkMats[si]} frustumCulled={false} castShadow receiveShadow />
      ))}
      {leafSets.map((set, si) => (
        <instancedMesh key={`leaves-${si}`} ref={(m) => { leafRefs.current[si] = m; }}
          args={[leafGeoms[si], materials.leaf, Math.max(1, set.length)]} customDepthMaterial={materials.depth}
          frustumCulled={false} castShadow receiveShadow />
      ))}
      <instancedMesh ref={ringRef} args={[undefined, undefined, forest.trees.length]} frustumCulled={false}>
        <ringGeometry args={[0.72, 1, 20]} />
        <meshBasicMaterial transparent opacity={0.85} />
      </instancedMesh>
    </group>
  );
}
