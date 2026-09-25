import { BookMarked, Compass, Map, MapPin, Moon, Settings2, Search, Sun, X } from "lucide-react";
import { useMemo } from "react";
import { groveApproach, searchTrees, treeApproach, type Forest, type Grove, type TreeSite } from "./forest";
import { QUESTS, questProgress } from "./quests";
import { SEASON_ORDER, SEASONS } from "./seasons";
import { wrapAngle, yawToward } from "./sim";
import { useGame } from "./store";

export function HUD({ forest }: { forest: Forest }) {
  const season = useGame((s) => s.season);
  const setSeason = useGame((s) => s.setSeason);
  const timeOfDay = useGame((s) => s.timeOfDay);
  const toggleTimeOfDay = useGame((s) => s.toggleTimeOfDay);
  const query = useGame((s) => s.query);
  const setQuery = useGame((s) => s.setQuery);
  const searchPick = useGame((s) => s.searchPick);
  const nearbySlug = useGame((s) => s.nearbySlug);
  const nearbyDist = useGame((s) => s.nearbyDist);
  const collect = useGame((s) => s.collect);
  const nearbyDismissed = useGame((s) => s.nearbyDismissed);
  const dismissNearby = useGame((s) => s.dismissNearby);
  const questHintHidden = useGame((s) => s.questHintHidden);
  const dismissQuestHint = useGame((s) => s.dismissQuestHint);
  const library = useGame((s) => s.library);
  const grovesVisited = useGame((s) => s.grovesVisited);
  const speed = useGame((s) => s.speed);
  const x = useGame((s) => s.x);
  const z = useGame((s) => s.z);
  const yaw = useGame((s) => s.yaw);
  const toast = useGame((s) => s.toast);
  const stats = useGame((s) => s.stats);
  const libraryOpen = useGame((s) => s.libraryOpen);
  const toggleLibrary = useGame((s) => s.toggleLibrary);
  const pause = useGame((s) => s.pause);
  const atlasOpen = useGame((s) => s.atlasOpen);
  const toggleAtlas = useGame((s) => s.toggleAtlas);
  const selectedGrove = useGame((s) => s.selectedGrove);
  const travelMode = useGame((s) => s.travelMode);
  const toggleCircuit = useGame((s) => s.toggleCircuit);

  const nearby = nearbySlug ? forest.trees.find((t) => t.book.slug === nearbySlug) : undefined;
  const showBook = Boolean(nearby && nearby.book.slug !== nearbyDismissed);
  const progress = questProgress({ library, grovesVisited, season });
  const nextQuest = QUESTS.find((q) => !q.done({ library, grovesVisited, season }));
  const selected = forest.groves.find((g) => g.genre === selectedGrove);

  // Sorted from where the cart was when the query changed; re-sorting every pose tick would reshuffle the list under the pointer.
  const results = useMemo(() => {
    const { x, z } = useGame.getState();
    return searchTrees(forest, query, x, z);
  }, [forest, query]);
  const matches = results.length;
  const picked = searchPick ? results.find((t) => t.book.slug === searchPick) : undefined;

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
            {" · "}
            {timeOfDay === "day" ? "Day" : "Night"}
            {travelMode === "circuit" ? " · ring" : ""}
            {progress.done ? ` · ${progress.done}/${progress.total}` : ""}
          </p>
          {stats ? (
            <p className="mt-1 font-mono text-[11px] text-faint tabular-nums">
              {(stats.tris / 1e6).toFixed(2)}M tris · {stats.calls} calls · {(forest.leaves.count / 1000).toFixed(0)}k leaves · {stats.fps.toFixed(0)} fps
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleTimeOfDay}
            className="grid size-11 place-items-center rounded-md border border-border bg-surface"
            aria-label={timeOfDay === "day" ? "Switch to night" : "Switch to day"}
            title={timeOfDay === "day" ? "Day · tap for night" : "Night · tap for day"}
          >
            {timeOfDay === "day" ? (
              <Sun className="size-4" strokeWidth={1.75} />
            ) : (
              <Moon className="size-4" strokeWidth={1.75} />
            )}
          </button>
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
            aria-label="Controls and settings" title="Controls and settings · Esc"
          >
            <Settings2 className="size-4" strokeWidth={1.75} />
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

      {/* Bottom-centre above the key hints, results opening upward; touch layouts move it (styles.css). */}
      <div className="search-dock pointer-events-auto z-20 mx-auto flex w-[min(100%-1.5rem,28rem)] flex-col gap-1 sm:absolute sm:bottom-9 sm:left-1/2 sm:mx-0 sm:w-[22rem] sm:-translate-x-1/2 sm:flex-col-reverse">
        <label className="flex items-center gap-2 rounded-md border border-border bg-surface/90 px-3 py-2">
          <Search className="size-4 shrink-0 text-muted" strokeWidth={1.75} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && results[0]) jumpToTree(results[0]);
              if (e.key === "Escape") e.currentTarget.blur();
            }}
            placeholder="Query the forest — freedom, fire, stoic…"
            className="min-h-7 w-full bg-transparent text-sm text-fg outline-none placeholder:text-faint"
          />
        </label>
        {query.trim() ? (
          <p className="px-1 text-xs text-muted sm:rounded-sm sm:bg-surface/80 sm:py-0.5">
            {matches} tree{matches === 1 ? "" : "s"} answering
            {picked ? ` · lantern points to ${picked.book.title}` : selected ? "" : " · lantern points to the nearest"}
          </p>
        ) : null}
        {query.trim() && matches && !picked ? (
          <ul className="max-h-[40vh] overflow-auto rounded-md border border-border bg-surface/95 sm:max-h-72">
            {results.slice(0, 30).map((t) => (
              <li key={t.book.slug}>
                <button type="button" onClick={() => jumpToTree(t)}
                  className="flex min-h-11 w-full items-center gap-3 px-3 py-1.5 text-left hover:bg-bg">
                  <span className="size-2.5 shrink-0 rounded-full" style={{ background: t.color }} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm leading-snug">{t.book.title}</span>
                    <span className="block truncate text-xs text-muted">{t.book.author} · {t.book.genreLabel}</span>
                  </span>
                  <span className="shrink-0 text-xs text-muted tabular-nums">{Math.round(Math.hypot(t.x - x, t.z - z))} m</span>
                  <span className="shrink-0 text-xs text-primary">Jump</span>
                </button>
              </li>
            ))}
            {matches > 30 ? <li className="px-3 py-2 text-xs text-faint">{matches - 30} more; narrow the query</li> : null}
          </ul>
        ) : null}
      </div>

      <div className="pointer-events-auto absolute top-36 right-3 w-28 sm:top-20 sm:w-40">
        <Minimap forest={forest} x={x} z={z} yaw={yaw} pins={query.trim() ? results : []} picked={searchPick} />
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

      <div className="book-dock pointer-events-auto absolute bottom-24 left-3 right-3 mx-auto max-w-lg sm:bottom-6 sm:left-4 sm:right-auto sm:max-w-[min(32rem,calc(50%-12rem))]">
        {showBook && nearby ? (
          <article className="relative rounded-lg border border-border bg-surface/94 p-3 pr-12 sm:p-4 sm:pr-14">
            <button
              type="button"
              onClick={dismissNearby}
              className="absolute top-1.5 right-1.5 grid size-11 place-items-center rounded-md text-muted"
              aria-label="Dismiss book"
            >
              <X className="size-5" strokeWidth={1.75} />
            </button>
            <p className="text-xs tracking-wide text-muted uppercase">{nearby.book.genreLabel}</p>
            <h2 className="font-display mt-0.5 text-xl leading-tight sm:text-2xl">{nearby.book.title}</h2>
            <p className="text-sm text-muted">{nearby.book.author}</p>
            <p className="mt-1 hidden text-xs text-faint tabular-nums sm:block">
              {nearby.book.chunks.toLocaleString()} chunks · trunk r {nearby.trunkRadius.toFixed(2)}
            </p>
            <p className="mt-2 hidden text-sm leading-relaxed text-fg/90 sm:block">{nearby.book.excerpt}</p>
            <button type="button" disabled={nearbyDist >= 6.8}
              onClick={() => collect(nearby.book.slug, nearby.book.title)}
              className="mt-3 min-h-11 rounded-md bg-primary px-4 text-sm text-primary-fg disabled:bg-bg disabled:text-muted">
              {nearbyDist < 6.8 ? "Read into the press · E" : `Move closer · ${Math.ceil(nearbyDist)} m`}
            </button>
          </article>
        ) : nextQuest && nextQuest.id !== questHintHidden ? (
          <div className="relative flex items-start gap-2 rounded-md border border-border bg-surface/80 px-3 py-2 pr-12 text-sm text-muted">
            <p className="min-w-0 flex-1">
              <span className="text-fg">{nextQuest.title}.</span> {nextQuest.hint}
            </p>
            <button
              type="button"
              onClick={() => dismissQuestHint(nextQuest.id)}
              className="absolute top-0.5 right-0.5 grid size-11 place-items-center rounded-md text-muted"
              aria-label="Dismiss hint"
            >
              <X className="size-4" strokeWidth={1.75} />
            </button>
          </div>
        ) : null}
      </div>

      <div className="season-dock pointer-events-auto absolute right-3 bottom-24 hidden flex-col gap-1 sm:flex">
        <button
          type="button"
          onClick={() => { toggleCircuit(); (document.activeElement as HTMLElement | null)?.blur(); }}
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
        WASD drive · Up/Down look · Space brake · E read · C camera · Esc settings
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

function jumpToTree(t: TreeSite) {
  const s = useGame.getState();
  s.selectGrove(null);
  s.pickSearch(t.book.slug);
  s.requestJump(treeApproach(t, s.x, s.z), t.book.title);
  (document.activeElement as HTMLElement | null)?.blur();
}

function jumpHome(forest: Forest) {
  useGame.getState().selectGrove(null);
  useGame.getState().requestJump(
    { x: forest.spawn.x, z: forest.spawn.z, yaw: forest.spawn.yaw },
    "Hamlet · the press",
  );
}

function Minimap({ forest, x, z, yaw, pins, picked }: {
  forest: Forest; x: number; z: number; yaw: number; pins: TreeSite[]; picked: string | null;
}) {
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
      {pins.slice(0, 200).map((t) => {
        const c = to(t.x, t.z);
        const on = t.book.slug === picked;
        return (
          <button key={t.book.slug} type="button" onClick={() => jumpToTree(t)}
            className="absolute rounded-full border border-bg bg-primary"
            style={{ left: c.left, top: c.top, width: on ? 10 : 6, height: on ? 10 : 6, transform: "translate(-50%, -50%)", zIndex: on ? 2 : 1 }}
            title={`Jump to ${t.book.title}`} aria-label={`Jump to ${t.book.title}`} />
        );
      })}
      {picked && pins.some((t) => t.book.slug === picked) ? (() => {
        const t = pins.find((p) => p.book.slug === picked)!;
        const c = to(t.x, t.z);
        return <MapPin className="pointer-events-none absolute size-4 text-primary" strokeWidth={2}
          style={{ left: c.left, top: c.top, transform: "translate(-50%, -100%)", zIndex: 3 }} aria-hidden />;
      })() : null}
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
    <div
      className="pointer-events-auto absolute inset-0 z-30 flex items-start justify-end bg-bg/45 p-3 sm:p-6"
      onClick={toggleAtlas}
    >
      <div
        className="flex max-h-[74vh] w-full max-w-md flex-col rounded-xl border border-border bg-surface p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-display text-2xl">Grove atlas</h2>
          <button
            type="button"
            onClick={toggleAtlas}
            className="grid size-11 place-items-center rounded-md text-muted"
            aria-label="Close atlas"
          >
            <X className="size-5" strokeWidth={1.75} />
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
            onClick={() => { toggleCircuit(); useGame.getState().setAtlasOpen(false); (document.activeElement as HTMLElement | null)?.blur(); }}
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
    <div
      className="pointer-events-auto absolute inset-0 z-30 flex items-end justify-end bg-bg/45 p-3 sm:p-6"
      onClick={toggleLibrary}
    >
      <div
        className="flex max-h-[70vh] w-full max-w-md flex-col rounded-xl border border-border bg-surface p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-display text-2xl">The press</h2>
          <button
            type="button"
            onClick={toggleLibrary}
            className="grid size-11 place-items-center rounded-md text-muted"
            aria-label="Close press"
          >
            <X className="size-5" strokeWidth={1.75} />
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
