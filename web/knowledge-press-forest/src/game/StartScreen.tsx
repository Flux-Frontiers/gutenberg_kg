import { BookOpen } from "lucide-react";
import { SEASON_ORDER, SEASONS, type SeasonName } from "./seasons";
import { useGame } from "./store";

export function StartScreen({
  ready,
  growing,
  onEnter,
}: {
  ready: boolean;
  growing: boolean;
  onEnter: () => void;
}) {
  const season = useGame((s) => s.season);
  const setSeason = useGame((s) => s.setSeason);
  const library = useGame((s) => s.library);

  return (
    <div className="absolute inset-0 z-20 flex flex-col bg-bg text-fg">
      <div className="pointer-events-none absolute inset-0 opacity-80 start-wash" />
      <div className="relative mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col justify-center px-5 py-10 sm:px-8">
        <p className="text-xs font-medium tracking-[0.22em] text-muted uppercase">GutenbergKG · Flux Frontiers</p>
        <h1 className="font-display mt-3 text-4xl leading-tight text-fg sm:text-6xl">
          The Knowledge Press
        </h1>
        <p className="font-display mt-1 text-xl italic text-primary sm:text-2xl">Forest</p>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-muted">
          Two hundred fifty-three public-domain books, grown as trees. Trunk is the work,
          limbs are the sections, leaves are the passages. Space colonization draws every
          branch toward the text — the canopy is the book’s shape, not a decoration.
        </p>
        <ul className="mt-6 grid gap-2 text-sm text-muted sm:grid-cols-2">
          <li className="rounded-md border border-border bg-surface px-3 py-2">W / S — throttle</li>
          <li className="rounded-md border border-border bg-surface px-3 py-2">A / D — steer</li>
          <li className="rounded-md border border-border bg-surface px-3 py-2">E — read the nearest tree</li>
          <li className="rounded-md border border-border bg-surface px-3 py-2">G — grove atlas · tap the map to jump</li>
          <li className="rounded-md border border-border bg-surface px-3 py-2">Q — ride the ring road</li>
          <li className="rounded-md border border-border bg-surface px-3 py-2">H — return to Hamlet</li>
        </ul>

        <div className="mt-7 flex flex-wrap gap-2">
          {SEASON_ORDER.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setSeason(name)}
              className={
                "rounded-sm px-3 py-2 text-sm " +
                (season === name
                  ? "bg-primary text-primary-fg"
                  : "border border-border bg-surface text-fg")
              }
            >
              {SEASONS[name].label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-sm text-faint">{SEASONS[season].blurb}</p>

        <div className="mt-8 flex flex-wrap items-center gap-4">
          <button
            type="button"
            onClick={onEnter}
            disabled={!ready}
            className="inline-flex min-h-11 items-center gap-2 rounded-md bg-primary px-6 py-3 text-base font-medium text-primary-fg disabled:opacity-50"
          >
            <BookOpen className="size-4" strokeWidth={1.75} />
            {growing ? "Growing the forest…" : "Start driving"}
          </button>
          {library.length > 0 ? (
            <p className="text-sm text-muted">
              {library.length} book{library.length === 1 ? "" : "s"} already in the press
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function seasonLabel(s: SeasonName): string {
  return SEASONS[s].label;
}
