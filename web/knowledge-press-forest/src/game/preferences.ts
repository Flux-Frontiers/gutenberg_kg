export type Preferences = {
  pace: "gentle" | "brisk";
  sensitivity: number;
  camera: "follow" | "high" | "cart";
  motion: boolean;
  detail: boolean;
};

export function readPreferences(value?: Partial<Preferences>): Preferences {
  return {
    pace: value?.pace === "brisk" ? "brisk" : "gentle",
    sensitivity: typeof value?.sensitivity === "number" && Number.isFinite(value.sensitivity)
      ? Math.max(0.5, Math.min(1.5, value.sensitivity)) : 1,
    camera: value?.camera === "high" || value?.camera === "cart" ? value.camera : "follow",
    motion: typeof value?.motion === "boolean" ? value.motion
      : !(typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches),
    detail: typeof value?.detail === "boolean" ? value.detail : true,
  };
}
