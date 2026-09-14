import { BOOKS } from "./catalog";

export type Quest = {
  id: string;
  title: string;
  hint: string;
  done: (s: { library: string[]; grovesVisited: string[]; season: string }) => boolean;
};

const STOIC = new Set(
  BOOKS.filter((b) => b.tags.includes("stoic") || /epictetus|aurelius|meditations|enchiridion/i.test(b.title + b.author)).map(
    (b) => b.slug,
  ),
);

export const QUESTS: Quest[] = [
  {
    id: "three",
    title: "First impressions",
    hint: "Read three trees. Drive close and press E.",
    done: (s) => s.library.length >= 3,
  },
  {
    id: "stoic",
    title: "A Stoic",
    hint: "Meditations, Epictetus, or the Enchiridion — philosophy and the classics.",
    done: (s) => s.library.some((id) => STOIC.has(id)),
  },
  {
    id: "hamlet",
    title: "The Dane",
    hint: "Shakespeare’s grove is small. Hamlet is 420 leaves on 305 limbs.",
    done: (s) => s.library.includes("hamlet"),
  },
  {
    id: "winter",
    title: "Bare wood",
    hint: "Switch to winter. The pipe model is the point.",
    done: (s) => s.season === "winter" && s.library.length >= 1,
  },
  {
    id: "wander",
    title: "Across the press",
    hint: "Visit four genre groves.",
    done: (s) => s.grovesVisited.length >= 4,
  },
];

export function questProgress(s: { library: string[]; grovesVisited: string[]; season: string }) {
  const done = QUESTS.filter((q) => q.done(s)).length;
  return { done, total: QUESTS.length };
}
