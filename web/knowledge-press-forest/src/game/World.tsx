import { useMemo } from "react";
import { BackSide, Color } from "three";
import type { Forest } from "./forest";
import { SEASONS, type SeasonName } from "./seasons";

export function World({ forest, season }: { forest: Forest; season: SeasonName }) {
  const pal = SEASONS[season];
  const fogColor = pal.fog;
  const skyColor = useMemo(() => new Color(pal.sky), [pal.sky]);

  return (
    <>
      <color attach="background" args={[skyColor]} />
      <fogExp2 attach="fog" args={[fogColor, season === "winter" ? 0.011 : 0.015]} />
      <hemisphereLight color={pal.ambient} groundColor={pal.ground} intensity={0.78} />
      <directionalLight position={[40, 55, 18]} intensity={0.88} color={pal.sun} />
      <directionalLight position={[-30, 20, -40]} intensity={0.2} color="#8aa0b8" />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <circleGeometry args={[forest.worldRadius + 30, 64]} />
        <meshStandardMaterial color={pal.ground} roughness={0.96} metalness={0} />
      </mesh>

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
        <ringGeometry args={[46, 54, 64]} />
        <meshStandardMaterial color="#4a3b28" roughness={1} />
      </mesh>

      {forest.groves.map((g) => (
        <group key={g.genre} position={[g.x, 0, g.z]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
            <circleGeometry args={[Math.min(g.radius * 0.55, 16), 24]} />
            <meshStandardMaterial color={pal.ground} roughness={1} />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.06, 0]}>
            <ringGeometry args={[2.2, 2.7, 20]} />
            <meshBasicMaterial color={g.color} transparent opacity={0.55} />
          </mesh>
        </group>
      ))}

      <mesh position={[0, 0.55, 0]}>
        <cylinderGeometry args={[1.55, 1.85, 0.38, 8]} />
        <meshStandardMaterial color="#6a655c" roughness={0.85} />
      </mesh>
      <mesh position={[0, 0.95, 0]}>
        <boxGeometry args={[1.15, 0.52, 0.16]} />
        <meshStandardMaterial color="#d7d1c4" roughness={0.55} />
      </mesh>

      <mesh>
        <sphereGeometry args={[forest.worldRadius * 1.45, 16, 12]} />
        <meshBasicMaterial color={pal.sky} side={BackSide} />
      </mesh>
    </>
  );
}
