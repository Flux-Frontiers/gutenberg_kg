/**
 * Genre -> tree species. A species picks the bark texture, the leaf outline
 * and a small shift of the season's foliage colour; the crown's shape still
 * comes from the book's chunks.
 */
export type SpeciesName = "oak" | "chestnut" | "fir" | "plane" | "blackthorn";

/**
 * A leaf outline. `ovate` is the original chestnut-style leaf at a half-width.
 * `outline` is the right half from the tip (0, 1) down to the stalk (0, -1) in
 * true proportions, mirrored for the left half; `smooth` rounds it through a
 * Catmull-Rom spline, otherwise the corners stay sharp.
 */
export type LeafShape =
  | { shape: "ovate"; width: number }
  | { shape: "outline"; half: [number, number][]; smooth: boolean };

export type Species = {
  name: SpeciesName;
  /** Height / width of the bark image (textures/bark/<name>_color.jpg). */
  barkAspect: number;
  leaf: LeafShape;
  /** HSL offset applied to the season's foliage colours. */
  foliageShift: [h: number, s: number, l: number];
};

// English oak: rounded lobes, widest above the middle, small ears at the base.
const OAK_HALF: [number, number][] = [
  [0.16, 0.97], [0.27, 0.86], [0.19, 0.74], [0.4, 0.64], [0.45, 0.5], [0.26, 0.42],
  [0.47, 0.31], [0.49, 0.16], [0.29, 0.1], [0.44, -0.02], [0.42, -0.17], [0.24, -0.22],
  [0.32, -0.36], [0.27, -0.5], [0.13, -0.55], [0.18, -0.68], [0.1, -0.8], [0.03, -0.86],
];

// London plane: three broad upper lobes, two smaller outward ones, a rounded base.
const PLANE_HALF: [number, number][] = [
  [0.06, 0.84], [0.11, 0.66], [0.17, 0.46], [0.33, 0.58], [0.55, 0.72], [0.5, 0.52],
  [0.44, 0.34], [0.38, 0.24], [0.56, 0.2], [0.8, 0.12], [0.66, -0.02], [0.52, -0.16],
  [0.36, -0.26], [0.2, -0.3], [0.07, -0.26], [0.04, -0.32], [0.03, -0.75],
];

// A fir spray rather than a lone needle: slender needles either side of a stem,
// angled toward the tip, longest mid-spray.
const FIR_HALF: [number, number][] = (() => {
  const out: [number, number][] = [];
  const n = 12;
  for (let k = 0; k < n; k++) {
    const y = 0.86 - (1.62 * k) / (n - 1);
    const reach = 0.12 + 0.2 * Math.sin((Math.PI * (k + 1)) / (n + 1));
    // Flat, blunt needles: wide at the stem, a squared-off tip.
    out.push([0.05, y + 0.045], [reach, y + 0.12], [reach + 0.01, y + 0.08], [0.05, y - 0.04]);
  }
  out.push([0.04, -1]);
  return out;
})();

export const SPECIES: Species[] = [
  { name: "oak", barkAspect: 2, leaf: { shape: "outline", half: OAK_HALF, smooth: true }, foliageShift: [0, 0, 0] },
  { name: "chestnut", barkAspect: 1, leaf: { shape: "ovate", width: 0.36 }, foliageShift: [0.01, 0.04, -0.03] },
  { name: "fir", barkAspect: 1, leaf: { shape: "outline", half: FIR_HALF, smooth: false }, foliageShift: [0.05, -0.12, -0.12] },
  { name: "plane", barkAspect: 1, leaf: { shape: "outline", half: PLANE_HALF, smooth: false }, foliageShift: [-0.01, 0.02, 0.05] },
  { name: "blackthorn", barkAspect: 1, leaf: { shape: "ovate", width: 0.7 }, foliageShift: [0.02, -0.1, -0.1] },
];

// Leaf instances are scaled 1.12 wide by 1.78 tall (emitLeaves); true-proportion
// outlines are pre-widened by the inverse so they render as drawn.
const INSTANCE_ASPECT = 1.78 / 1.12;

function cubic(p0: number[], p1: number[], p2: number[], p3: number[], n: number): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, u = 1 - t;
    const f = (k: number) => u * u * u * p0[k]! + 3 * u * u * t * p1[k]! + 3 * u * t * t * p2[k]! + t * t * t * p3[k]!;
    out.push([f(0), f(1)]);
  }
  return out;
}

function catmullRom(pts: [number, number][], per: number): [number, number][] {
  const out: [number, number][] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)]!, p1 = pts[i]!, p2 = pts[i + 1]!, p3 = pts[Math.min(pts.length - 1, i + 2)]!;
    for (let s = 0; s < per; s++) {
      const t = s / per, t2 = t * t, t3 = t2 * t;
      const f = (k: number) => 0.5 * (2 * p1[k]! + (p2[k]! - p0[k]!) * t + (2 * p0[k]! - 5 * p1[k]! + 4 * p2[k]! - p3[k]!) * t2 + (3 * p1[k]! - p0[k]! - 3 * p2[k]! + p3[k]!) * t3);
      out.push([f(0), f(1)]);
    }
  }
  out.push(pts[pts.length - 1]!);
  return out;
}

/** Closed leaf polygon in instance coordinates, starting at the tip (ShapeGeometry fixes the winding). */
export function leafOutline(leaf: LeafShape): [number, number][] {
  if (leaf.shape === "ovate") {
    const k = leaf.width / 0.36;
    const right = cubic([0, 1], [0.62, 0.58], [0.48, -0.12], [0.1, -0.82], 7);
    const left = cubic([-0.1, -0.82], [-0.48, -0.12], [-0.62, 0.58], [0, 1], 7);
    return withStalk([...right, [0, -1], ...left.slice(0, -1)].map(([x, y]) => [x * k, y]));
  }
  const right = [[0, 1] as [number, number], ...leaf.half];
  // Two samples per span: ~73 triangles for the oak instead of 180, still round at leaf size.
  const half = leaf.smooth ? catmullRom(right, 2) : right;
  const bottom = half[half.length - 1]!;
  const full: [number, number][] = [...half, [0, bottom[1] - 0.02], ...half.slice(1).reverse().map(([x, y]) => [-x, y] as [number, number])];
  return withStalk(full.map(([x, y]) => [x * INSTANCE_ASPECT, y]));
}

/**
 * Give a leaf a stalk: squeeze the blade into y in [STALK_TOP, 1] and hang it
 * from a thin petiole down to y = -1, the point the instance pins to the twig.
 */
const STALK_TOP = -0.62;
const STALK_HALF_WIDTH = 0.04;
function withStalk(pts: [number, number][]): [number, number][] {
  const squeezed = pts.map(([x, y]) => [x, STALK_TOP + ((y + 1) * (1 - STALK_TOP)) / 2] as [number, number]);
  let low = 0;
  for (let i = 1; i < squeezed.length; i++) if (squeezed[i]![1] < squeezed[low]![1]) low = i;
  const y0 = squeezed[low]![1];
  return [
    ...squeezed.slice(0, low),
    [STALK_HALF_WIDTH, y0], [STALK_HALF_WIDTH, -1], [-STALK_HALF_WIDTH, -1], [-STALK_HALF_WIDTH, y0],
    ...squeezed.slice(low + 1),
  ];
}

const GENRE_SPECIES: Record<string, SpeciesName> = {
  philosophy: "oak",
  "ancient-classical": "oak",
  shakespeare: "oak",
  "sacred-texts": "oak",
  "english-literature": "chestnut",
  "american-literature": "chestnut",
  biography: "chestnut",
  drama: "chestnut",
  "science-fiction": "fir",
  "natural-history": "fir",
  travel: "fir",
  "audel-electric": "fir",
  letters: "plane",
  diaries: "plane",
  "french-literature": "plane",
  "world-literature": "plane",
  spanish: "plane",
  curiosities: "plane",
  horror: "blackthorn",
  "russian-literature": "blackthorn",
  "german-literature": "blackthorn",
};

/** Index into SPECIES; unmapped genres grow chestnut. */
export function speciesFor(genre: string): number {
  const name = GENRE_SPECIES[genre] ?? "chestnut";
  return SPECIES.findIndex((s) => s.name === name);
}
