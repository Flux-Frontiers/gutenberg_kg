import { useEffect, useMemo } from "react";
import { CanvasTexture, DoubleSide, LinearFilter, SRGBColorSpace } from "three";
import { groveByGenre, type Forest, type Grove, type Waypoint } from "./forest";
import { useGame } from "./store";

function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (ctx.measureText(next).width > maxWidth && cur) {
      lines.push(cur);
      cur = w;
    } else {
      cur = next;
    }
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 2);
}

function makeSignTexture(label: string, meta: string, accent: string): CanvasTexture {
  const w = 1024;
  const h = 360;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return new CanvasTexture(canvas);

  ctx.fillStyle = "#cfc6b4";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#efe8dc";
  ctx.fillRect(22, 22, w - 44, h - 44);
  ctx.fillStyle = accent;
  ctx.fillRect(22, 22, 28, h - 44);
  ctx.strokeStyle = "#3a322c";
  ctx.lineWidth = 5;
  ctx.strokeRect(14, 14, w - 28, h - 28);

  ctx.fillStyle = "#1a2030";
  // Large enough to read from the road: the label shrinks only if two lines will not fit.
  ctx.textBaseline = "top";
  let size = 104;
  let lines: string[] = [];
  for (; size >= 72; size -= 8) {
    ctx.font = `600 ${size}px "Cormorant Garamond", Georgia, "Times New Roman", serif`;
    lines = wrapLines(ctx, label, w - 120);
    if (lines.length === 1 || size * 2.1 < h - 110) break;
  }
  const startY = lines.length === 1 ? 70 : 34;
  lines.forEach((line, i) => {
    ctx.fillText(line, 68, startY + i * size * 1.02);
  });

  ctx.fillStyle = "#5a5348";
  ctx.font = '600 46px "Source Sans 3", system-ui, sans-serif';
  ctx.fillText(meta, 68, h - 82);

  const tex = new CanvasTexture(canvas);
  tex.colorSpace = SRGBColorSpace;
  tex.minFilter = LinearFilter;
  tex.magFilter = LinearFilter;
  tex.needsUpdate = true;
  return tex;
}

function Signpost({
  wp,
  grove,
  selected,
}: {
  wp: Waypoint;
  grove: Grove;
  selected: boolean;
}) {
  const tex = useMemo(
    () => makeSignTexture(grove.label, `${grove.bookCount} trees`, grove.color),
    [grove.label, grove.bookCount, grove.color],
  );
  useEffect(() => () => tex.dispose(), [tex]);

  const dist = Math.hypot(wp.x, wp.z) || 1;
  const ux = wp.x / dist;
  const uz = wp.z / dist;
  const rx = uz;
  const rz = -ux;
  const x = wp.x + rx * 1.35;
  const z = wp.z + rz * 1.35;
  const lookX = wp.x - ux * 5.5;
  const lookZ = wp.z - uz * 5.5;
  const yaw = Math.atan2(lookX - x, lookZ - z);

  return (
    <group position={[x, 0, z]} rotation={[0, yaw, 0]}>
      <mesh position={[0, 1.3, 0]}>
        <cylinderGeometry args={[0.08, 0.11, 2.6, 6]} />
        <meshStandardMaterial color="#4a3a2a" roughness={0.9} />
      </mesh>
      <mesh position={[0, 2.35, 0.07]}>
        <boxGeometry args={[3.0, 1.05, 0.08]} />
        <meshStandardMaterial
          map={tex}
          roughness={0.72}
          metalness={0}
          emissive={grove.color}
          emissiveIntensity={selected ? 0.18 : 0.04}
          side={DoubleSide}
        />
      </mesh>
      <mesh position={[0, 2.92, 0.07]}>
        <boxGeometry args={[2.7, 0.08, 0.16]} />
        <meshStandardMaterial color="#3a322c" roughness={0.85} />
      </mesh>
      <mesh position={[0, 3.05, 0.0]}>
        <octahedronGeometry args={[0.12]} />
        <meshStandardMaterial
          color={grove.color}
          emissive={grove.color}
          emissiveIntensity={selected ? 0.7 : 0.22}
        />
      </mesh>
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

/** A reading plaque: title, byline and a wrapped paragraph. */
function makePlaqueTexture(title: string, byline: string, body: string): CanvasTexture {
  const w = 1536;
  const h = 768;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return new CanvasTexture(canvas);
  ctx.fillStyle = "#3a322c";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#efe8dc";
  ctx.fillRect(18, 18, w - 36, h - 36);
  ctx.strokeStyle = "#c9a24a";
  ctx.lineWidth = 6;
  ctx.strokeRect(38, 38, w - 76, h - 76);
  ctx.textBaseline = "top";
  ctx.fillStyle = "#1a2030";
  ctx.font = 'italic 600 96px "Cormorant Garamond", Georgia, "Times New Roman", serif';
  ctx.fillText(title, 84, 70);
  ctx.fillStyle = "#8a6a22";
  ctx.font = '600 44px "Source Sans 3", system-ui, sans-serif';
  ctx.fillText(byline, 86, 180);
  ctx.fillStyle = "#2a2a2a";
  ctx.font = '400 42px "Source Sans 3", system-ui, sans-serif';
  const words = body.split(" ");
  let line = "";
  let y = 262;
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > w - 172 && line) {
      ctx.fillText(line, 86, y);
      y += 56;
      line = word;
    } else {
      line = next;
    }
  }
  if (line) ctx.fillText(line, 86, y);
  const tex = new CanvasTexture(canvas);
  tex.colorSpace = SRGBColorSpace;
  tex.minFilter = LinearFilter;
  tex.magFilter = LinearFilter;
  return tex;
}

/** The sculpture's plaque, at the plaza's edge and facing out, so it reads with the sculpture behind it. */
function KeplerPlaque() {
  const tex = useMemo(() => makePlaqueTexture("Mysterium Cosmographicum", "Johannes Kepler · 1596", KEPLER_BODY), []);
  useEffect(() => () => tex.dispose(), [tex]);
  const x = -4.2, z = 4.6;
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

function HamletSign() {
  const tex = useMemo(() => makeSignTexture("The Press", "Hamlet · the hub", "#8fad86"), []);
  useEffect(() => () => tex.dispose(), [tex]);
  return (
    // On the plaza, clear of the sculpture's plinth, facing the hub.
    <group position={[3.8, 0, 4.3]} rotation={[0, Math.atan2(-3.8, -4.3), 0]}>
      <mesh position={[0, 1.15, 0]}>
        <cylinderGeometry args={[0.08, 0.11, 2.3, 6]} />
        <meshStandardMaterial color="#4a3a2a" roughness={0.9} />
      </mesh>
      <mesh position={[0, 2.1, 0.07]}>
        <boxGeometry args={[2.6, 0.91, 0.07]} />
        <meshStandardMaterial map={tex} roughness={0.72} />
      </mesh>
    </group>
  );
}

export function Signposts({ forest }: { forest: Forest }) {
  const selectedGrove = useGame((s) => s.selectedGrove);
  return (
    <group>
      <HamletSign />
      <KeplerPlaque />
      {forest.circuit.map((wp) => {
        const grove = groveByGenre(forest, wp.genre);
        if (!grove) return null;
        return (
          <Signpost
            key={wp.genre}
            wp={wp}
            grove={grove}
            selected={selectedGrove === wp.genre}
          />
        );
      })}
    </group>
  );
}
