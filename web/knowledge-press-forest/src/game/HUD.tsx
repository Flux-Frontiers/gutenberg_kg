import { BookMarked, Compass, Map, Pause, Search } from "lucide-react";
import { useMemo } from "react";
import { groveApproach, type Forest, type Grove } from "./forest";
import { QUESTS, questProgress } from "./quests";
import { SEASON_ORDER, SEASONS } from "./seasons";
import { wrapAngle, yawToward } from "./sim";
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
  const atlasOpen = useGame((s) => s.atlasOpen);
  const toggleAtlas = useGame((s) => s.toggleAtlas);
  const selectedGrove = useGame((s) => s.selectedGrove);
  const travelMode = useGame((s) => s.travelMode);
  const toggleCircuit = useGame((s) => s.toggleCircuit);

  const nearby = nearbySlug ? forest.trees.find((t) => t.book.slug === nearbySlug) : undefined;
  const progress = questProgress({ library, grovesVisited, season });
  const nextQuest = QUESTS.find((q) => !q.done({ library, grovesVisited, season }));
  const selected = forest.groves.find((g) => g.genre === selectedGrove);

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

  const bearing = selected
    ? wrapAngle(yawToward(x, z, selected.x, selected.z) - yaw)
    : 0;

  return (
    <div className="pointer-events-none absolute inset-0 z-10 text-fg">
      <header className="pointer-events-auto flex items-start justify-between gap-3 p-3 sm:p-4">
        <div className="rounded-lg border border-border bg-surface/90 px-3 py-2">
          <p className="font-display text-lg leading-none">Knowledge Press</p>
          <p className="mt-1 text-xs text-muted">
            {forest.trees.length} trees · {SEASONS[season].label}
            {travelMode === "circuit" ? " · ring" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleAtlas}
            className={
              "inline-flex min-h-11 items-center gap-2 rounded-md border px-3 text-sm " +
              (atlasOpen ? "border-primary bg-primary text-primary-fg" : "border-border bg-surface")
            }
            aria-label="Open grove atlas"
          >
            <Map className="size-4" strokeWidth={1.75} />
            <span className="hidden sm:inline">Groves</span>
          </button>
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
            {selected ? "" : " · lantern points to the nearest"}
          </p>
        ) : null}
      </div>

      <div className="pointer-events-auto absolute top-20 right-3 w-28 sm:w-40">
        <Minimap forest={forest} x={x} z={z} yaw={yaw} />
        {selected ? (
          <p className="mt-1 flex items-center gap-1.5 text-xs text-muted">
            <span
              className="inline-block size-2 rounded-full"
              style={{ background: selected.color }}
            />
            <span className="truncate">{selected.label}</span>
            <span
              className="ml-auto inline-block size-0 border-x-4 border-b-[7px] border-x-transparent border-b-fg"
              style={{ transform: `rotate(${bearing}rad)` }}
              aria-hidden
            />
          </p>
        ) : (
          <p className="mt-1 text-xs text-faint">Tap a grove to jump</p>
        )}
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
        <button
          type="button"
          onClick={toggleCircuit}
          className={
            "rounded-sm px-2 py-1 text-xs " +
            (travelMode === "circuit" ? "bg-primary text-primary-fg" : "border border-border bg-surface text-muted")
          }
        >
          {travelMode === "circuit" ? "On the ring" : "Ride the ring"}
        </button>
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
        W throttle · A left · D right · E read · G groves · Q ring · H Hamlet
      </p>

      {toast ? (
        <div className="pointer-events-none absolute top-1/3 left-1/2 -translate-x-1/2 rounded-md border border-border bg-surface px-4 py-2 text-sm">
          {toast}
        </div>
      ) : null}

      {libraryOpen ? <LibraryPanel forest={forest} /> : null}
      {atlasOpen ? <AtlasPanel forest={forest} /> : null}
    </div>
  );
}

function jumpToGrove(g: Grove) {
  const wp = groveApproach(g);
  useGame.getState().selectGrove(g.genre);
  useGame.getState().requestJump({ x: wp.x, z: wp.z, yaw: wp.yaw }, `${g.label} grove`);
}

function jumpHome(forest: Forest) {
  useGame.getState().selectGrove(null);
  useGame.getState().requestJump(
    { x: forest.spawn.x, z: forest.spawn.z, yaw: forest.spawn.yaw },
    "Hamlet · the press",
  );
}

function Minimap({ forest, x, z, yaw }: { forest: Forest; x: number; z: number; yaw: number }) {
  const selectedGrove = useGame((s) => s.selectedGrove);
  const r = forest.worldRadius;
  const to = (wx: number, wz: number) => {
    const px = ((wx + r) / (2 * r)) * 100;
    const pz = ((wz + r) / (2 * r)) * 100;
    return { left: `${px}%`, top: `${pz}%` };
  };
  const p = to(x, z);
  return (
    <div className="relative h-28 w-28 overflow-hidden rounded-lg border border-border bg-bg/80 sm:h-40 sm:w-40">
      <Compass className="absolute top-1.5 left-1.5 size-3 text-muted" strokeWidth={1.75} />
      <button
        type="button"
        className="absolute size-2 rounded-full bg-fg/70"
        style={{ left: "50%", top: "50%", transform: "translate(-50%, -50%)" }}
        aria-label="Jump to Hamlet"
        onClick={() => jumpHome(forest)}
      />
      {forest.groves.map((g) => {
        const c = to(g.x, g.z);
        const size = Math.max(10, (g.radius / r) * 80);
        const on = selectedGrove === g.genre;
        return (
          <button
            key={g.genre}
            type="button"
            className="absolute rounded-full"
            style={{
              left: c.left,
              top: c.top,
              width: size,
              height: size,
              background: g.color,
              opacity: on ? 1 : 0.72,
              transform: "translate(-50%, -50%)",
              boxShadow: on ? `0 0 0 2px var(--color-fg)` : "none",
            }}
            title={`Jump to ${g.label}`}
            aria-label={`Jump to ${g.label}`}
            onClick={() => jumpToGrove(g)}
          />
        );
      })}
      <span
        className="pointer-events-none absolute h-0 w-0 border-x-4 border-b-8 border-x-transparent border-b-fg"
        style={{
          left: p.left,
          top: p.top,
          transform: `translate(-50%, -70%) rotate(${-yaw}rad)`,
        }}
      />
    </div>
  );
}

function AtlasPanel({ forest }: { forest: Forest }) {
  const grovesVisited = useGame((s) => s.grovesVisited);
  const selectedGrove = useGame((s) => s.selectedGrove);
  const toggleAtlas = useGame((s) => s.toggleAtlas);
  const travelMode = useGame((s) => s.travelMode);
  const toggleCircuit = useGame((s) => s.toggleCircuit);

  return (
    <div className="pointer-events-auto absolute inset-3 z-30 flex items-start justify-end sm:inset-6">
      <div className="flex max-h-[74vh] w-full max-w-md flex-col rounded-xl border border-border bg-surface p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-display text-2xl">Grove atlas</h2>
          <button type="button" onClick={toggleAtlas} className="text-sm text-muted">
            Close
          </button>
        </div>
        <p className="mt-1 text-sm text-muted">
          Jump a grove, or ride the ring. The cart stays yours — steer to hop off.
        </p>
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => jumpHome(forest)}
            className="min-h-11 flex-1 rounded-md border border-border bg-bg px-3 text-sm"
          >
            Hamlet
          </button>
          <button
            type="button"
            onClick={toggleCircuit}
            className={
              "min-h-11 flex-1 rounded-md px-3 text-sm " +
              (travelMode === "circuit" ? "bg-primary text-primary-fg" : "border border-border bg-bg")
            }
          >
            {travelMode === "circuit" ? "Stop the ring" : "Ride the ring"}
          </button>
        </div>
        <ul className="mt-3 min-h-0 flex-1 space-y-1 overflow-auto">
          {forest.groves.map((g) => {
            const visited = grovesVisited.includes(g.genre);
            const on = selectedGrove === g.genre;
            return (
              <li key={g.genre}>
                <button
                  type="button"
                  onClick={() => jumpToGrove(g)}
                  className={
                    "flex min-h-11 w-full items-center gap-3 rounded-md px-3 text-left " +
                    (on ? "bg-primary/15" : "hover:bg-bg")
                  }
                >
                  <span className="size-2.5 shrink-0 rounded-full" style={{ background: g.color }} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium leading-snug">{g.label}</span>
                    <span className="block text-xs text-muted">
                      {g.bookCount} trees{visited ? " · visited" : ""}
                    </span>
                  </span>
                  <span className="text-xs text-primary">Jump</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

function LibraryPanel({ forest }: { forest: Forest }) {
  const library = useGame((s) => s.library);
  const toggleLibrary = useGame((s) => s.toggleLibrary);
  const collected = forest.trees.filter((t) => library.includes(t.book.slug));

  return (
    <div className="pointer-events-auto absolute inset-3 z-30 flex items-end justify-end sm:inset-6">
      <div className="flex max-h-[70vh] w-full max-w-md flex-col rounded-xl border border-border bg-surface p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-display text-2xl">The press</h2>
          <button type="button" onClick={toggleLibrary} className="text-sm text-muted">
            Close
          </button>
        </div>
        <p className="mt-1 text-sm text-muted">
          {collected.length} collected of {forest.trees.length}
        </p>
        <ul className="mt-3 min-h-0 flex-1 space-y-2 overflow-auto">
          {collected.length === 0 ? (
            <li className="text-sm text-faint">Drive to a tree and press E.</li>
          ) : (
            collected.map((t) => (
              <li key={t.book.slug} className="flex items-start justify-between gap-3 border-b border-border pb-2">
                <div>
                  <p className="font-medium leading-snug">{t.book.title}</p>
                  <p className="text-xs text-muted">
                    {t.book.author} · {t.book.genreLabel}
                  </p>
                </div>
                <button
                  type="button"
                  className="shrink-0 text-xs text-primary"
                  onClick={() => {
                    const g = forest.groves.find((gr) => gr.genre === t.book.genre);
                    if (g) jumpToGrove(g);
                  }}
                >
                  Grove
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
