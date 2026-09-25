/** Deterministic hash (FNV-1a) — same slug always grows the same tree. */
export function seedFromKey(key: string): number {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function fibonacciAnnulus(
  n: number,
  inner: number,
  outer: number,
): { x: number; z: number }[] {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const pts: { x: number; z: number }[] = [];
  const count = Math.max(n, 1);
  for (let i = 0; i < count; i++) {
    const t = count === 1 ? 0.5 : i / (count - 1);
    const r = inner + t * (outer - inner);
    const a = i * golden;
    pts.push({ x: r * Math.cos(a), z: r * Math.sin(a) });
  }
  return pts;
}

export function fibonacciHemisphere(n: number, radius: number): { x: number; y: number; z: number }[] {
  const pts: { x: number; y: number; z: number }[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  const need = Math.max(n, 1);
  let i = 0;
  let found = 0;
  const cap = need * 3 + 8;
  while (found < need && i < cap) {
    const y = 1 - (i / Math.max(cap - 1, 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const a = i * golden;
    const yy = Math.abs(y);
    pts.push({ x: Math.cos(a) * r * radius, y: yy * radius, z: Math.sin(a) * r * radius });
    found++;
    i++;
  }
  return pts.slice(0, need);
}
