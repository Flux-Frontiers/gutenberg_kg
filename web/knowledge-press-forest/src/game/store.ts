import { create } from "zustand";
import type { SeasonName } from "./seasons";

const SAVE_KEY = "kpf-library-v1";
const SAVE_VERSION = 1;

type SaveBlob = {
  version: number;
  library: string[];
  grovesVisited: string[];
  season: SeasonName;
};

function loadSave(): SaveBlob {
  const defaults: SaveBlob = {
    version: SAVE_VERSION,
    library: [],
    grovesVisited: [],
    season: "summer",
  };
  if (typeof window === "undefined") return defaults;
  try {
    const raw = window.localStorage.getItem(SAVE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<SaveBlob>;
    return {
      ...defaults,
      ...parsed,
      version: SAVE_VERSION,
      library: Array.isArray(parsed.library) ? parsed.library : [],
      grovesVisited: Array.isArray(parsed.grovesVisited) ? parsed.grovesVisited : [],
      season:
        parsed.season === "spring" ||
        parsed.season === "summer" ||
        parsed.season === "autumn" ||
        parsed.season === "winter"
          ? parsed.season
          : "summer",
    };
  } catch {
    return defaults;
  }
}

function persist(s: { library: string[]; grovesVisited: string[]; season: SeasonName }) {
  try {
    const blob: SaveBlob = {
      version: SAVE_VERSION,
      library: s.library,
      grovesVisited: s.grovesVisited,
      season: s.season,
    };
    window.localStorage.setItem(SAVE_KEY, JSON.stringify(blob));
  } catch {
    /* private mode / quota */
  }
}

export type GameStore = {
  playing: boolean;
  paused: boolean;
  season: SeasonName;
  query: string;
  library: string[];
  grovesVisited: string[];
  nearbySlug: string | null;
  nearbyDist: number;
  speed: number;
  x: number;
  z: number;
  yaw: number;
  toast: string | null;
  libraryOpen: boolean;
  helpOpen: boolean;
  lastReadSlug: string | null;
  play: () => void;
  pause: (v?: boolean) => void;
  setSeason: (s: SeasonName) => void;
  setQuery: (q: string) => void;
  collect: (slug: string, title: string) => void;
  markGrove: (genre: string) => void;
  setNearby: (slug: string | null, dist: number) => void;
  setPose: (x: number, z: number, yaw: number, speed: number) => void;
  setToast: (msg: string | null) => void;
  toggleLibrary: () => void;
  toggleHelp: () => void;
  setLastRead: (slug: string | null) => void;
};

const initial = loadSave();

export const useGame = create<GameStore>((set, get) => ({
  playing: false,
  paused: false,
  season: initial.season,
  query: "",
  library: initial.library,
  grovesVisited: initial.grovesVisited,
  nearbySlug: null,
  nearbyDist: 99,
  speed: 0,
  x: 0,
  z: 0,
  yaw: 0,
  toast: null,
  libraryOpen: false,
  helpOpen: false,
  lastReadSlug: null,
  play: () => set({ playing: true, paused: false }),
  pause: (v) => set({ paused: v ?? !get().paused }),
  setSeason: (season) => {
    set({ season });
    persist({ ...get(), season });
  },
  setQuery: (query) => set({ query }),
  collect: (slug, title) => {
    const lib = get().library;
    if (lib.includes(slug)) {
      set({ lastReadSlug: slug, toast: title });
      return;
    }
    const library = [...lib, slug];
    set({ library, lastReadSlug: slug, toast: `Pressed · ${title}` });
    persist({ ...get(), library });
  },
  markGrove: (genre) => {
    const grovesVisited = get().grovesVisited;
    if (grovesVisited.includes(genre)) return;
    const next = [...grovesVisited, genre];
    set({ grovesVisited: next });
    persist({ ...get(), grovesVisited: next });
  },
  setNearby: (nearbySlug, nearbyDist) => set({ nearbySlug, nearbyDist }),
  setPose: (x, z, yaw, speed) => set({ x, z, yaw, speed }),
  setToast: (toast) => set({ toast }),
  toggleLibrary: () => set({ libraryOpen: !get().libraryOpen }),
  toggleHelp: () => set({ helpOpen: !get().helpOpen }),
  setLastRead: (lastReadSlug) => set({ lastReadSlug }),
}));
