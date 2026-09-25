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
 * Leaf-count multiplier per complexity level. Low is the original forest; a
 * laptop held 60 fps (its refresh cap) at what is now High, so Ultra doubles it.
 */
export const LEAF_SCALE: Record<LeafDetail, number> = { low: 1, medium: 2, high: 4, ultra: 8 };

export function readPreferences(value?: Partial<Preferences>): Preferences {
  return {
    pace: value?.pace === "brisk" ? "brisk" : "gentle",
    sensitivity: typeof value?.sensitivity === "number" && Number.isFinite(value.sensitivity)
      ? Math.max(0.5, Math.min(1.5, value.sensitivity)) : 1,
    camera: value?.camera === "high" || value?.camera === "cart" ? value.camera : "follow",
    motion: typeof value?.motion === "boolean" ? value.motion
      : !(typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches),
    detail: typeof value?.detail === "boolean" ? value.detail : true,
    // Touch devices start at Low: the iPad mini was choppy at twice that.
    leaves: value?.leaves && value.leaves in LEAF_SCALE ? value.leaves
      : typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches ? "low" : "medium",
    stats: value?.stats === true,
  };
}
