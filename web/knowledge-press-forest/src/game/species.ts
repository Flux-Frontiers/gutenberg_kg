/**
 * Genre -> tree species. A species picks the bark texture, the leaf outline
 * and a small shift of the season's foliage colour; the crown's shape still
 * comes from the book's chunks.
 */
export type SpeciesName = "oak" | "chestnut" | "fir" | "plane" | "blackthorn";

export type Species = {
  name: SpeciesName;
  /** Height / width of the bark image (textures/bark/<name>_color.jpg). */
  barkAspect: number;
  /** Leaf outline: an ellipse of this half-width, modulated by lobes. */
  leaf: { width: number; lobes: number; depth: number };
  /** HSL offset applied to the season's foliage colours. */
  foliageShift: [h: number, s: number, l: number];
};

export const SPECIES: Species[] = [
  { name: "oak", barkAspect: 2, leaf: { width: 0.55, lobes: 9, depth: 0.16 }, foliageShift: [0, 0, 0] },
  { name: "chestnut", barkAspect: 1, leaf: { width: 0.36, lobes: 0, depth: 0 }, foliageShift: [0.01, 0.04, -0.03] },
  { name: "fir", barkAspect: 1, leaf: { width: 0.1, lobes: 0, depth: 0 }, foliageShift: [0.05, -0.12, -0.12] },
  { name: "plane", barkAspect: 1, leaf: { width: 0.9, lobes: 5, depth: 0.3 }, foliageShift: [-0.01, 0.02, 0.05] },
  { name: "blackthorn", barkAspect: 1, leaf: { width: 0.7, lobes: 0, depth: 0 }, foliageShift: [0.02, -0.1, -0.1] },
];

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
