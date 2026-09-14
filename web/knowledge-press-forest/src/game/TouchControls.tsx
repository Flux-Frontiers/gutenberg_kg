import { bookBySlug } from "./catalog";
import { useRef } from "react";
import { setTouchAxes } from "./input";
import { useGame } from "./store";

export function TouchControls() {
  const collect = useGame((s) => s.collect);
  const nearbySlug = useGame((s) => s.nearbySlug);
  const toggleAtlas = useGame((s) => s.toggleAtlas);
  const area = useRef<HTMLDivElement>(null);
  const pid = useRef<number | null>(null);

  function axesFromEvent(e: React.PointerEvent<HTMLDivElement>) {
    const el = area.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = (e.clientX - cx) / (rect.width * 0.5);
    const dy = (e.clientY - cy) / (rect.height * 0.5);
    const mag = Math.hypot(dx, dy);
    const s = mag > 1 ? 1 / mag : 1;
    const x = dx * s;
    const y = dy * s;
    setTouchAxes(-y, -x);
  }

  function clear(e: React.PointerEvent<HTMLDivElement>) {
    if (pid.current !== e.pointerId) return;
    pid.current = null;
    setTouchAxes(0, 0);
  }

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex items-end justify-between p-3 sm:hidden">
      <div
        ref={area}
        className="pointer-events-auto relative size-28 rounded-full border border-border bg-surface/70"
        style={{ touchAction: "none" }}
        onPointerDown={(e) => {
          pid.current = e.pointerId;
          e.currentTarget.setPointerCapture(e.pointerId);
          axesFromEvent(e);
        }}
        onPointerMove={(e) => {
          if (pid.current === e.pointerId) axesFromEvent(e);
        }}
        onPointerUp={clear}
        onPointerCancel={clear}
      >
        <span className="absolute inset-0 m-auto size-10 rounded-full border border-border bg-bg/80" />
      </div>
      <div className="pointer-events-auto flex flex-col items-end gap-2">
        <button
          type="button"
          className="min-h-11 rounded-full border border-border bg-surface px-4 text-sm"
          onClick={toggleAtlas}
        >
          Groves
        </button>
        <button
          type="button"
          className="min-h-14 min-w-14 rounded-full border border-border bg-primary px-4 text-sm font-medium text-primary-fg"
          onClick={() => {
            if (nearbySlug) collect(nearbySlug, bookBySlug(nearbySlug)?.title ?? "Book");
          }}
        >
          Read
        </button>
      </div>
    </div>
  );
}
