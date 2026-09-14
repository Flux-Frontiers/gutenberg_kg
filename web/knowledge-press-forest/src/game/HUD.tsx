import { BookMarked, Compass, Pause, Search } from "lucide-react";
import { useMemo } from "react";
import type { Forest } from "./forest";
import { QUESTS, questProgress } from "./quests";
import { SEASON_ORDER, SEASONS } from "./seasons";
import { useGame } from "./store";

export function HUD({ forest }: { forest: Forest }) {
  const season = useGame((s) => s.season);
  const setSeason = useGame((s) => s.setSeason);
  const query = useGame((s) => s.query);
  const setQuery = useGame((s) => s.setQuery);
  const nearbySlug = useGame((s) => s.nearbySlug);
  const library = useGame((s) => s.library);
  const grovesVisited = useGame((s) => s.grovesVisited);
  const speed = useGame((s) => s.speed);
  const x = useGame((s) => s.x);
  const z = useGame((s) => s.z);
  const yaw = useGame((s) => s.yaw);
  const toast = useGame((s) => s.toast);
  const libraryOpen = useGame((s) => s.libraryOpen);
  const toggleLibrary = useGame((s) => s.toggleLibrary);
  const pause = useGame((s) => s.pause);

  const nearby = nearbySlug ? forest.trees.find((t) => t.book.slug === nearbySlug) : undefined;
  const progress = questProgress({ library, grovesVisited, season });
  const nextQuest = QUESTS.find((q) => !q.done({ library, grovesVisited, season }));

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return 0;
    return forest.trees.filter((t) => {
      const b = t.book;
      return (
        b.title.toLowerCase().includes(q) ||
        b.author.toLowerCase().includes(q) ||
        b.genreLabel.toLowerCase().includes(q) ||
        b.tags.some((tag) => tag.includes(q)) ||
        b.excerpt.toLowerCase().includes(q)
      );
    }).length;
  }, [forest, query]);

  return (
    <div className="pointer-events-none absolute inset-0 z-10 text-fg">
      <header className="pointer-events-auto flex items-start justify-between gap-3 p-3 sm:p-4">
        <div className="rounded-lg border border-border bg-surface/90 px-3 py-2">
          <p className="font-display text-lg leading-none">Knowledge Press</p>
          <p className="mt-1 text-xs text-muted">
            {forest.trees.length} trees · {SEASONS[season].label}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => pause(true)}
            className="grid size-11 place-items-center rounded-md border border-border bg-surface"
            aria-label="Pause"
          >
            <Pause className="size-4" strokeWidth={1.75} />
          </button>
          <button
            type="button"
            onClick={toggleLibrary}
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border bg-surface px-3 text-sm"
          >
            <BookMarked className="size-4" strokeWidth={1.75} />
            <span className="tabular-nums">{library.length}</span>
          </button>
        </div>
      </header>

      <div className="pointer-events-auto mx-auto w-[min(100%-1.5rem,28rem)]">
        <label className="flex items-center gap-2 rounded-md border border-border bg-surface/90 px-3 py-2">
          <Search className="size-4 shrink-0 text-muted" strokeWidth={1.75} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Query the forest — freedom, fire, stoic…"
            className="min-h-7 w-full bg-transparent text-sm text-fg outline-none placeholder:text-faint"
          />
        </label>
        {query.trim() ? (
          <p className="mt-1 px-1 text-xs text-muted">
            {matches} tree{matches === 1 ? "" : "s"} answering
          </p>
        ) : null}
      </div>

      <div className="pointer-events-none absolute top-20 right-3 hidden w-40 sm:block">
        <Minimap forest={forest} x={x} z={z} yaw={yaw} />
      </div>

      <div className="pointer-events-auto absolute bottom-24 left-3 right-3 mx-auto max-w-lg sm:bottom-6 sm:left-4 sm:right-auto">
        {nearby ? (
          <article className="rounded-lg border border-border bg-surface/92 p-3 sm:p-4">
            <p className="text-xs tracking-wide text-muted uppercase">{nearby.book.genreLabel}</p>
            <h2 className="font-display mt-0.5 text-2xl leading-tight">{nearby.book.title}</h2>
            <p className="text-sm text-muted">{nearby.book.author}</p>
            <p className="mt-2 text-xs text-faint tabular-nums">
              {nearby.book.chunks.toLocaleString()} chunks · trunk r {nearby.trunkRadius.toFixed(2)}
            </p>
            <p className="mt-2 text-sm leading-relaxed text-fg/90">{nearby.book.excerpt}</p>
            <p className="mt-3 text-xs text-primary">E · read into the press</p>
          </article>
        ) : (
          <div className="rounded-lg border border-border bg-surface/80 px-3 py-2 text-sm text-muted">
            {nextQuest ? (
              <p>
                <span className="text-fg">{nextQuest.title}.</span> {nextQuest.hint}
              </p>
            ) : (
              <p>The press is full enough. Drive anywhere.</p>
            )}
            <p className="mt-1 text-xs text-faint">
              {progress.done}/{progress.total} impressions · {Math.round(Math.abs(speed) * 3.6) / 10} pace
            </p>
          </div>
        )}
      </div>

      <div className="pointer-events-auto absolute right-3 bottom-24 hidden flex-col gap-1 sm:flex">
        {SEASON_ORDER.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setSeason(name)}
            className={
              "rounded-sm px-2 py-1 text-xs " +
              (season === name ? "bg-primary text-primary-fg" : "border border-border bg-surface text-muted")
            }
          >
            {SEASONS[name].label}
          </button>
        ))}
      </div>

      <p className="absolute bottom-3 left-1/2 hidden -translate-x-1/2 text-xs text-faint sm:block">
        W throttle · A left · D right · E read
      </p>

      {toast ? (
        <div className="pointer-events-none absolute top-1/3 left-1/2 -translate-x-1/2 rounded-md border border-border bg-surface px-4 py-2 text-sm">
          {toast}
        </div>
      ) : null}

      {libraryOpen ? <LibraryPanel forest={forest} /> : null}
    </div>
  );
}

function Minimap({ forest, x, z, yaw }: { forest: Forest; x: number; z: number; yaw: number }) {
  const r = forest.worldRadius;
  const to = (wx: number, wz: number) => {
    const px = ((wx + r) / (2 * r)) * 100;
    const pz = ((wz + r) / (2 * r)) * 100;
    return { left: `${px}%`, top: `${pz}%` };
  };
  const p = to(x, z);
  return (
    <div className="relative h-40 w-40 overflow-hidden rounded-lg border border-border bg-bg/80">
      <Compass className="absolute top-1.5 left-1.5 size-3 text-muted" strokeWidth={1.75} />
      {forest.groves.map((g) => {
        const c = to(g.x, g.z);
        const size = Math.max(8, (g.radius / r) * 80);
        return (
          <span
            key={g.genre}
            className="absolute rounded-full opacity-70"
            style={{
              left: c.left,
              top: c.top,
              width: size,
              height: size,
              background: g.color,
              transform: "translate(-50%, -50%)",
            }}
            title={g.label}
          />
        );
      })}
      <span
        className="absolute h-0 w-0 border-x-4 border-b-8 border-x-transparent border-b-fg"
        style={{
          left: p.left,
          top: p.top,
          transform: `translate(-50%, -70%) rotate(${-yaw}rad)`,
        }}
      />
    </div>
  );
}

function LibraryPanel({ forest }: { forest: Forest }) {
  const library = useGame((s) => s.library);
  const toggleLibrary = useGame((s) => s.toggleLibrary);
  const collected = forest.trees.filter((t) => library.includes(t.book.slug)).map((t) => t.book);

  return (
    <div className="pointer-events-auto absolute inset-3 z-30 flex items-end justify-end sm:inset-6">
      <div className="flex max-h-[70vh] w-full max-w-md flex-col rounded-xl border border-border bg-surface p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-display text-2xl">The press</h2>
          <button type="button" onClick={toggleLibrary} className="text-sm text-muted">
            Close
          </button>
        </div>
        <p className="mt-1 text-sm text-muted">{collected.length} collected of {forest.trees.length}</p>
        <ul className="mt-3 min-h-0 flex-1 space-y-2 overflow-auto">
          {collected.length === 0 ? (
            <li className="text-sm text-faint">Drive to a tree and press E.</li>
          ) : (
            collected.map((b) => (
              <li key={b.slug} className="border-b border-border pb-2">
                <p className="font-medium leading-snug">{b.title}</p>
                <p className="text-xs text-muted">
                  {b.author} · {b.genreLabel}
                </p>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
