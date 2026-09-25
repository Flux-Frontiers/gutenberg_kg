export type Preferences = {
  pace: "gentle" | "brisk";
  sensitivity: number;
  camera: "follow" | "high" | "cart";
  motion: boolean;
  detail: boolean;
  /** Leaf complexity; see LEAF_SCALE. */
  leaves: LeafDetail;
  /** Show triangles, draw calls, leaves and frame rate. */
  stats: boolean;
};

export type LeafDetail = "low" | "medium" | "high" | "ultra";

/**
 * Fraction of each book's chunks that carry a leaf. Ultra is the truthful
 * forest, one leaf per chunk (~398k); every level is the same fraction of every
 * book, so crowns stay proportional to the books.
 */
export const LEAF_SCALE: Record<LeafDetail, number> = { low: 0.1, medium: 0.25, high: 0.5, ultra: 1 };

export function readPreferences(value?: Partial<Preferences>): Preferences {
  return {
    pace: value?.pace === "brisk" ? "brisk" : "gentle",
    sensitivity: typeof value?.sensitivity === "number" && Number.isFinite(value.sensitivity)
      ? Math.max(0.5, Math.min(1.5, value.sensitivity)) : 1,
    camera: value?.camera === "high" || value?.camera === "cart" ? value.camera : "follow",
    motion: typeof value?.motion === "boolean" ? value.motion
      : !(typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches),
    detail: typeof value?.detail === "boolean" ? value.detail : true,
    // Touch devices start at Low.
    leaves: value?.leaves && value.leaves in LEAF_SCALE ? value.leaves
      : typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches ? "low" : "medium",
    stats: value?.stats === true,
  };
}
