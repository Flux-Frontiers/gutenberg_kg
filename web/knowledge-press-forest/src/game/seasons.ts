export type SeasonName = "spring" | "summer" | "autumn" | "winter";

export type Season = {
  name: SeasonName;
  label: string;
  foliage: string[];
  density: number;
  wood: string;
  sky: string;
  fog: string;
  ground: string;
  ambient: string;
  sun: string;
  blurb: string;
};

export const SEASONS: Record<SeasonName, Season> = {
  spring: {
    name: "spring",
    label: "Spring",
    foliage: ["#A8E063", "#7FD14B", "#C6F08A", "#F4D4E0", "#E8E3B0"],
    density: 1,
    wood: "#6B4A2E",
    sky: "#1a2a40",
    fog: "#1c2c42",
    ground: "#35502a",
    ambient: "#9bb8c9",
    sun: "#f0e4c4",
    blurb: "New leaves. The graph is just coming into leaf.",
  },
  summer: {
    name: "summer",
    label: "Summer",
    foliage: ["#90EE90", "#5FBF5F", "#77DD77", "#3E9B4F"],
    density: 1,
    wood: "#6B4A2E",
    sky: "#16213e",
    fog: "#1a1a2e",
    ground: "#2d4a1e",
    ambient: "#8aa4b8",
    sun: "#dfe7f2",
    blurb: "Full canopy. Every chunk is a leaf.",
  },
  autumn: {
    name: "autumn",
    label: "Autumn",
    foliage: ["#E8A33D", "#D95F30", "#B3341F", "#F0C75E", "#8C6A3F", "#6B8F3A"],
    density: 0.85,
    wood: "#5C3D24",
    sky: "#2a1a2e",
    fog: "#2a1a28",
    ground: "#3a2a18",
    ambient: "#c4a07a",
    sun: "#e8c090",
    blurb: "The press in harvest. Colour by genre still holds.",
  },
  winter: {
    name: "winter",
    label: "Winter",
    foliage: ["#8C7A5E", "#A89880", "#D7E3EA"],
    density: 0.1,
    wood: "#7A6A58",
    sky: "#101725",
    fog: "#121820",
    ground: "#2a3038",
    ambient: "#b8c4d0",
    sun: "#c5d0dc",
    blurb: "Bare wood. This is where the pipe model shows.",
  },
};

export const SEASON_ORDER: SeasonName[] = ["spring", "summer", "autumn", "winter"];
