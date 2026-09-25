import { useEffect, useRef } from "react";
import { useGame } from "./store";

export function PauseOverlay() {
  const paused = useGame((s) => s.paused);
  const pause = useGame((s) => s.pause);
  const prefs = useGame((s) => s.preferences);
  const setPreferences = useGame((s) => s.setPreferences);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (paused) dialog.current?.showModal();
    else dialog.current?.close();
  }, [paused]);

  function resume() {
    pause(false);
    (document.activeElement as HTMLElement | null)?.blur();
  }

  return (
    <dialog ref={dialog} aria-labelledby="settings-title" onCancel={(e) => { e.preventDefault(); resume(); }}
      className="forest-settings m-auto max-h-[90dvh] w-[min(100%-2rem,30rem)] overflow-auto rounded-xl border border-border bg-surface p-6 text-fg shadow-2xl">
      <p className="text-xs tracking-[0.2em] text-primary uppercase">Take a breath</p>
      <h2 id="settings-title" className="mt-1 font-display text-3xl">Make the forest yours</h2>
      <p className="mt-2 text-sm text-muted">Your cart is parked. These settings are saved on this device.</p>
      <div className="my-5 grid gap-4 text-sm">
        <label className="flex items-center justify-between gap-4">Driving pace
          <select value={prefs.pace} onChange={(e) => setPreferences({ pace: e.target.value as typeof prefs.pace })} className="rounded-md border border-border bg-bg p-2">
            <option value="gentle">Gentle exploration</option><option value="brisk">Brisk driving</option>
          </select>
        </label>
        <label className="grid gap-2">Steering response · {prefs.sensitivity.toFixed(1)}×
          <input type="range" min="0.5" max="1.5" step="0.1" value={prefs.sensitivity} onChange={(e) => setPreferences({ sensitivity: Number(e.target.value) })} />
        </label>
        <label className="flex items-center justify-between gap-4">Camera · C
          <select value={prefs.camera} onChange={(e) => setPreferences({ camera: e.target.value as typeof prefs.camera })} className="rounded-md border border-border bg-bg p-2">
            <option value="follow">Behind the cart</option><option value="high">High view</option><option value="cart">In the cart</option>
          </select>
        </label>
        <label className="flex items-center justify-between gap-4">Wind & gentle cart motion
          <input type="checkbox" checked={prefs.motion} onChange={(e) => setPreferences({ motion: e.target.checked })} />
        </label>
        <label className="flex items-center justify-between gap-4">Leaf complexity
          <select value={prefs.leaves} onChange={(e) => setPreferences({ leaves: e.target.value as typeof prefs.leaves })} className="rounded-md border border-border bg-bg p-2">
            <option value="low">Low · 1 in 10 chunks</option><option value="medium">Medium · 1 in 4</option>
            <option value="high">High · 1 in 2</option><option value="ultra">Ultra · every chunk</option>
          </select>
        </label>
        <label className="flex items-center justify-between gap-4">Silent mode · no pop-up cards
          <input type="checkbox" checked={prefs.silent} onChange={(e) => setPreferences({ silent: e.target.checked })} />
        </label>
        <label className="flex items-center justify-between gap-4">Show geometry & frame rate
          <input type="checkbox" checked={prefs.stats} onChange={(e) => setPreferences({ stats: e.target.checked })} />
        </label>
        <label className="flex items-center justify-between gap-4">Shadows & forest floor detail
          <input type="checkbox" checked={prefs.detail} onChange={(e) => setPreferences({ detail: e.target.checked })} />
        </label>
      </div>
      <div className="rounded-md bg-bg p-3 text-sm leading-relaxed text-muted">
        <p><span className="text-fg">WASD</span> drive · <span className="text-fg">Left/Right</span> steer · <span className="text-fg">Up/Down</span> look · <span className="text-fg">Space</span> brake</p>
        <p><span className="text-fg">Shift</span> hurry · <span className="text-fg">E</span> read · <span className="text-fg">C</span> camera</p>
        <p><span className="text-fg">G</span> groves · <span className="text-fg">B</span> books · <span className="text-fg">H</span> home · <span className="text-fg">Q</span> guided tour</p>
        <p className="mt-2 text-xs">Release the throttle to stop. You can turn in place. Gamepad: left stick to drive, right stick to look, A to read, LT to brake, RT to hurry.</p>
      </div>
      <button type="button" autoFocus className="mt-5 min-h-11 w-full rounded-md bg-primary text-primary-fg" onClick={resume}>Back to the forest</button>
    </dialog>
  );
}
