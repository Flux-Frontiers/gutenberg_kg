import { useGame } from "./store";

export function PauseOverlay() {
  const paused = useGame((s) => s.paused);
  const pause = useGame((s) => s.pause);
  const play = useGame((s) => s.play);
  if (!paused) return null;
  return (
    <div className="absolute inset-0 z-30 grid place-items-center bg-bg/70">
      <div className="w-[min(100%-2rem,24rem)] rounded-xl border border-border bg-surface p-6">
        <h2 className="font-display text-3xl">Paused</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          A left, D right, from behind the cart. The forest keeps its season until you change it.
        </p>
        <button
          type="button"
          className="mt-5 min-h-11 w-full rounded-md bg-primary text-primary-fg"
          onClick={() => {
            pause(false);
            play();
          }}
        >
          Resume
        </button>
      </div>
    </div>
  );
}
