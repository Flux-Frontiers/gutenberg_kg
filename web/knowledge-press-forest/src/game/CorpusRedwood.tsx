import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { BufferAttribute, BufferGeometry, CanvasTexture, Color, DoubleSide, InstancedMesh, MeshDepthMaterial, MeshStandardMaterial, Object3D, PlaneGeometry, RepeatWrapping, RGBADepthPacking, SRGBColorSpace, TextureLoader } from "three";
import { COARSE_POINTER } from "./Environment";
import { HUB_PLAQUE_DIR, HUB_PLAQUE_DIST, type Forest } from "./forest";
import type { SeasonName } from "./seasons";
import { makePlaqueTexture } from "./Signposts";

// Redwoods are evergreen: the crown keeps its colour through the year, a touch
// fresher in spring and frosted in winter.
const FOLIAGE: Record<SeasonName, string> = {
  spring: "#3d6236",
  summer: "#2f5130",
  autumn: "#35502e",
  winter: "#4a5d52",
};

/** Fir bark (CC0, public/textures/bark), warmed to a redwood's cinnamon. */
function redwoodBark() {
  const loader = new TextureLoader();
  const load = (map: string, srgb = false) => {
    const tex = loader.load(`textures/bark/fir_${map}.jpg`);
    tex.wrapS = tex.wrapT = RepeatWrapping;
    tex.anisotropy = 8;
    if (srgb) tex.colorSpace = SRGBColorSpace;
    return tex;
  };
  return new MeshStandardMaterial({ map: load("color", true), normalMap: load("normal"), color: "#e0936a", roughness: 0.95, metalness: 0 });
}

/**
 * One flat redwood spray, drawn once: a stem from the base (left) to the tip,
 * short flat needles either side, longest mid-spray. Near-white so each
 * instance's colour tints it; the transparent ground is cut away by alphaTest.
 */
function sprayTexture() {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 128;
  const ctx = c.getContext("2d")!;
  ctx.lineCap = "round";
  ctx.strokeStyle = "#c9d3ad";
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(4, 64);
  ctx.lineTo(250, 64);
  ctx.stroke();
  ctx.lineWidth = 5;
  for (let x = 10; x < 248; x += 6) {
    const t = (x - 10) / 238;
    const len = 54 * Math.sin(Math.PI * Math.min(1, 0.15 + t * 0.95)) + 6;
    for (const side of [-1, 1]) {
      const l = 78 + ((x * 7 + side * 13) % 17);
      ctx.strokeStyle = `hsl(95 30% ${l}%)`;
      ctx.beginPath();
      ctx.moveTo(x, 64);
      ctx.lineTo(x + len * 0.3, 64 + side * len);
      ctx.stroke();
    }
  }
  const tex = new CanvasTexture(c);
  tex.colorSpace = SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

function RedwoodPlaque({ forest }: { forest: Forest }) {
  const c = forest.corpusTree;
  const tex = useMemo(() => makePlaqueTexture(
    "The Corpus Redwood",
    `${c.limbs} books · ${c.totalChunks.toLocaleString("en-US")} chunks · ${Math.round(c.height)} m`,
    "One tree for the whole library. It grows by the same rule as every book tree, doubled: " +
    "3.4 m of height for each doubling of the corpus's chunks. It carries one limb per book, " +
    "the biggest books lowest, and each limb reaches toward that book's own tree in the forest. " +
    "The trunk is as thick as its limbs together: at any height its cross-section is the sum of " +
    "theirs above it. Press B to browse every book and jump to its tree.",
  ), [c.limbs, c.totalChunks, c.height]);
  useEffect(() => () => tex.dispose(), [tex]);
  const x = Math.cos(HUB_PLAQUE_DIR) * HUB_PLAQUE_DIST;
  const z = Math.sin(HUB_PLAQUE_DIR) * HUB_PLAQUE_DIST;
  return (
    <group position={[x, 0, z]} rotation={[0, Math.atan2(x, z), 0]}>
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

/** The hub's redwood: one bark mesh and one instanced draw of foliage sprays. */
export function CorpusRedwood({ forest, season }: { forest: Forest; season: SeasonName }) {
  const c = forest.corpusTree;
  const bark = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new BufferAttribute(c.bark.pos, 3));
    g.setAttribute("normal", new BufferAttribute(c.bark.normal, 3));
    g.setAttribute("uv", new BufferAttribute(c.bark.uv, 2));
    g.setIndex(new BufferAttribute(c.bark.index, 1));
    g.computeBoundingSphere();
    return g;
  }, [c]);
  const barkMat = useMemo(redwoodBark, []);
  // A unit card in the ground plane: x along the spray, z across it.
  const spray = useMemo(() => new PlaneGeometry(1, 1).rotateX(-Math.PI / 2), []);
  const sprayMap = useMemo(sprayTexture, []);
  const sprayMat = useMemo(() => new MeshStandardMaterial({ map: sprayMap, alphaTest: 0.5, side: DoubleSide, roughness: 0.85 }), [sprayMap]);
  const sprayDepth = useMemo(() => new MeshDepthMaterial({ depthPacking: RGBADepthPacking, map: sprayMap, alphaTest: 0.5, side: DoubleSide }), [sprayMap]);
  useEffect(() => () => bark.dispose(), [bark]);
  useEffect(() => () => {
    barkMat.map?.dispose();
    barkMat.normalMap?.dispose();
    barkMat.dispose();
    spray.dispose();
    sprayMap.dispose();
    sprayMat.dispose();
    sprayDepth.dispose();
  }, [barkMat, spray, sprayMap, sprayMat, sprayDepth]);

  const ref = useRef<InstancedMesh>(null);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const { pos, scale, quat, shade, count } = c.foliage;
    const o = new Object3D();
    const base = new Color(FOLIAGE[season]);
    const color = new Color();
    for (let i = 0; i < count; i++) {
      o.position.set(pos[i * 3]!, pos[i * 3 + 1]!, pos[i * 3 + 2]!);
      o.scale.set(scale[i * 3]!, scale[i * 3 + 1]!, scale[i * 3 + 2]!);
      o.quaternion.set(quat[i * 4]!, quat[i * 4 + 1]!, quat[i * 4 + 2]!, quat[i * 4 + 3]!);
      o.updateMatrix();
      mesh.setMatrixAt(i, o.matrix);
      mesh.setColorAt(i, color.copy(base).offsetHSL(0, 0, (shade[i]! - 3.5) * 0.012));
    }
    mesh.count = count;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [c, season]);

  return (
    <group>
      {/* Touch devices skip the redwood's shadows, as they do the book trees' leaves. */}
      <mesh geometry={bark} material={barkMat} castShadow={!COARSE_POINTER} receiveShadow />
      <instancedMesh ref={ref} args={[spray, sprayMat, Math.max(1, c.foliage.count)]} customDepthMaterial={sprayDepth}
        castShadow={!COARSE_POINTER} receiveShadow={!COARSE_POINTER} />
      <RedwoodPlaque forest={forest} />
    </group>
  );
}
