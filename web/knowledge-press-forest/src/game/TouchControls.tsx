import { bookBySlug } from "./catalog";
import { useEffect, useRef, useState } from "react";
import { setTouchAxes, setTouchBrake } from "./input";
import { useGame } from "./store";

export function TouchControls() {
  const collect = useGame((s) => s.collect);
  const nearbySlug = useGame((s) => s.nearbySlug);
  const nearbyDist = useGame((s) => s.nearbyDist);
  const blocked = useGame((s) => s.paused || s.libraryOpen || s.atlasOpen);
  const toggleCircuit = useGame((s) => s.toggleCircuit);
  const travelMode = useGame((s) => s.travelMode);
  const pid = useRef<number | null>(null);
  const [thumb, setThumb] = useState({ x: 0, y: 0 });

  useEffect(() => {
    pid.current = null;
    setTouchAxes(0, 0);
    setTouchBrake(false);
    setThumb({ x: 0, y: 0 });
    return () => { setTouchAxes(0, 0); setTouchBrake(false); };
  }, [blocked]);

  function axesFromEvent(e: React.PointerEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const dx = (e.clientX - rect.left - rect.width / 2) / (rect.width * 0.5);
    const dy = (e.clientY - rect.top - rect.height / 2) / (rect.height * 0.5);
    const mag = Math.hypot(dx, dy);
    const scale = mag > 1 ? 1 / mag : 1;
    const x = dx * scale, y = dy * scale;
    setThumb({ x: x * 32, y: y * 32 });
    setTouchAxes(Math.abs(y) < 0.12 ? 0 : -y, Math.abs(x) < 0.12 ? 0 : -x);
  }

  function clear(e: React.PointerEvent<HTMLDivElement>) {
    if (pid.current !== e.pointerId) return;
    pid.current = null;
    setTouchAxes(0, 0);
    setThumb({ x: 0, y: 0 });
  }

  if (blocked) return null;
  return (
    <div className="touch-controls pointer-events-none absolute inset-x-0 bottom-0 z-20 items-end justify-between p-3">
      <div role="group" aria-label="Drag to drive: up forward, down reverse, left or right to steer"
        className="pointer-events-auto relative size-28 rounded-full border border-border bg-surface/80"
        style={{ touchAction: "none" }}
        onPointerDown={(e) => {
          if (pid.current !== null) return;
          pid.current = e.pointerId;
          e.currentTarget.setPointerCapture(e.pointerId);
          axesFromEvent(e);
        }}
        onPointerMove={(e) => { if (pid.current === e.pointerId) axesFromEvent(e); }}
        onPointerUp={clear} onPointerCancel={clear} onLostPointerCapture={clear}>
        <span className="absolute inset-0 m-auto size-10 rounded-full border border-primary bg-primary/50"
          style={{ transform: `translate(${thumb.x}px, ${thumb.y}px)` }} />
      </div>
      <div className="pointer-events-auto flex flex-col items-end gap-2">
        <button type="button" className="min-h-11 rounded-full border border-border bg-surface px-4 text-sm" onClick={toggleCircuit}>
          {travelMode === "circuit" ? "End tour" : "Guided tour"}
        </button>
        <div className="flex gap-2">
          <button type="button" className="min-h-14 rounded-full border border-border bg-surface px-4 text-sm"
            onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); setTouchBrake(true); }}
            onPointerUp={() => setTouchBrake(false)} onPointerCancel={() => setTouchBrake(false)} onLostPointerCapture={() => setTouchBrake(false)}>
            Brake
          </button>
          <button type="button" disabled={!nearbySlug || nearbyDist >= 6.8}
            className="min-h-14 min-w-14 rounded-full border border-border bg-primary px-4 text-sm font-medium text-primary-fg disabled:opacity-40"
            onClick={() => { if (nearbySlug && nearbyDist < 6.8) collect(nearbySlug, bookBySlug(nearbySlug)?.title ?? "Book"); }}>
            Read
          </button>
        </div>
      </div>
    </div>
  );
}
