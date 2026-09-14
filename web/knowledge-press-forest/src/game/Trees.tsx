import { useLayoutEffect, useMemo, useRef } from "react";
import { Color, DoubleSide, InstancedMesh, Object3D, Shape, ShapeGeometry } from "three";
import type { Forest } from "./forest";
import { bookMatchesQuery } from "./forest";
import { SEASONS, type SeasonName } from "./seasons";

const dummy = new Object3D();
const color = new Color();

function ovateLeafGeometry() {
  const s = new Shape();
  s.moveTo(0, 1);
  s.bezierCurveTo(0.62, 0.58, 0.48, -0.12, 0.1, -0.82);
  s.lineTo(0, -1);
  s.lineTo(-0.1, -0.82);
  s.bezierCurveTo(-0.48, -0.12, -0.62, 0.58, 0, 1);
  const g = new ShapeGeometry(s, 7);
  g.computeVertexNormals();
  return g;
}

function keepLeaf(i: number, density: number): boolean {
  if (density >= 0.999) return true;
  const h = ((i * 16807) % 2147483647) / 2147483647;
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
  const woodRef = useRef<InstancedMesh>(null);
  const leafRef = useRef<InstancedMesh>(null);
  const ringRef = useRef<InstancedMesh>(null);
  const palette = SEASONS[season];
  const q = query.trim();

  const match = useMemo(() => {
    if (!q) return null;
    const set = new Set<number>();
    forest.trees.forEach((t, i) => {
      if (bookMatchesQuery(t.book, q)) set.add(i);
    });
    return set;
  }, [forest, q]);

  useLayoutEffect(() => {
    const mesh = woodRef.current;
    if (!mesh) return;
    const { pos, quat, scale, count } = forest.wood;
    const woodCol = new Color(palette.wood);
    let wi = 0;
    for (let t = 0; t < forest.trees.length; t++) {
      const tree = forest.trees[t]!;
      const dim = match && !match.has(t);
      for (let k = 0; k < tree.woodCount; k++) {
        const i = tree.woodStart + k;
        dummy.position.set(pos[i * 3]!, pos[i * 3 + 1]!, pos[i * 3 + 2]!);
        dummy.quaternion.set(quat[i * 4]!, quat[i * 4 + 1]!, quat[i * 4 + 2]!, quat[i * 4 + 3]!);
        dummy.scale.set(scale[i * 3]!, scale[i * 3 + 1]!, scale[i * 3 + 2]!);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
        color.copy(woodCol);
        if (dim) color.multiplyScalar(0.45);
        mesh.setColorAt(i, color);
        wi++;
      }
    }
    void wi;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.count = count;
  }, [forest, palette.wood, match]);

  useLayoutEffect(() => {
    const mesh = leafRef.current;
    if (!mesh) return;
    const { pos, scale, tint, treeIndex, count } = forest.leaves;
    const foliage = palette.foliage;
    for (let i = 0; i < count; i++) {
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
      mesh.setMatrixAt(i, dummy.matrix);
      const hex = foliage[tint[i]! % foliage.length]!;
      color.set(hex);
      if (match && match.has(treeI)) color.offsetHSL(0, 0.05, 0.08);
      mesh.setColorAt(i, color);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.count = count;
  }, [forest, palette, match]);

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

  const leafGeom = useMemo(() => ovateLeafGeometry(), []);

  return (
    <group>
      <instancedMesh ref={woodRef} args={[undefined, undefined, forest.wood.count]} frustumCulled={false} castShadow={false}>
        <cylinderGeometry args={[1, 1, 1, 6]} />
        <meshStandardMaterial roughness={0.9} metalness={0.02} />
      </instancedMesh>
      <instancedMesh ref={leafRef} args={[leafGeom, undefined, forest.leaves.count]} frustumCulled={false}>
        <meshStandardMaterial roughness={0.62} metalness={0} side={DoubleSide} />
      </instancedMesh>
      <instancedMesh ref={ringRef} args={[undefined, undefined, forest.trees.length]} frustumCulled={false}>
        <ringGeometry args={[0.72, 1, 20]} />
        <meshBasicMaterial transparent opacity={0.85} />
      </instancedMesh>
    </group>
  );
}
