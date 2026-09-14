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
  const h = 320;
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
  ctx.font = '600 78px "Cormorant Garamond", Georgia, "Times New Roman", serif';
  ctx.textBaseline = "top";
  const lines = wrapLines(ctx, label, w - 140);
  const startY = lines.length === 1 ? 78 : 52;
  lines.forEach((line, i) => {
    ctx.fillText(line, 72, startY + i * 88);
  });

  ctx.fillStyle = "#5a5348";
  ctx.font = '500 34px "Source Sans 3", system-ui, sans-serif';
  ctx.fillText(meta, 72, h - 78);

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
      <mesh position={[0, 1.15, 0]}>
        <cylinderGeometry args={[0.07, 0.1, 2.3, 6]} />
        <meshStandardMaterial color="#4a3a2a" roughness={0.9} />
      </mesh>
      <mesh position={[0, 2.14, 0.07]}>
        <boxGeometry args={[2.28, 0.76, 0.08]} />
        <meshStandardMaterial
          map={tex}
          roughness={0.72}
          metalness={0}
          emissive={grove.color}
          emissiveIntensity={selected ? 0.18 : 0.04}
          side={DoubleSide}
        />
      </mesh>
      <mesh position={[0, 2.42, 0.07]}>
        <boxGeometry args={[2.02, 0.08, 0.16]} />
        <meshStandardMaterial color="#3a322c" roughness={0.85} />
      </mesh>
      <mesh position={[0, 2.3, 0.0]}>
        <sphereGeometry args={[0.09, 8, 6]} />
        <meshStandardMaterial
          color={grove.color}
          emissive={grove.color}
          emissiveIntensity={selected ? 0.7 : 0.22}
        />
      </mesh>
    </group>
  );
}

function HamletSign() {
  const tex = useMemo(() => makeSignTexture("The Press", "Hamlet · the hub", "#8fad86"), []);
  useEffect(() => () => tex.dispose(), [tex]);
  return (
    <group position={[2.15, 0, 2.4]} rotation={[0, Math.atan2(-2.15, -2.4), 0]}>
      <mesh position={[0, 0.95, 0]}>
        <cylinderGeometry args={[0.08, 0.11, 1.9, 6]} />
        <meshStandardMaterial color="#4a3a2a" roughness={0.9} />
      </mesh>
      <mesh position={[0, 1.78, 0.07]}>
        <boxGeometry args={[1.7, 0.56, 0.07]} />
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
