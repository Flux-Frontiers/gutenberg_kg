export type TimeOfDay = "day" | "night";

export const TIME_ORDER: TimeOfDay[] = ["day", "night"];

/** Overrides applied on top of the season palette when timeOfDay is "day". Night uses the season palette as-is. */
export const DAY_OVERRIDE = {
  sky: "#bfe3f5",
  fog: "#d8ecf5",
  fogDensityScale: 0.5,
  ambient: "#ffffff",
  sun: "#fff6df",
  sunIntensity: 1.4,
  hemiIntensity: 1.05,
  groundLightness: 0.12,
};
