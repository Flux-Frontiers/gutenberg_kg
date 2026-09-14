import { useEffect, useState } from "react";
import { ForestCanvas } from "./ForestCanvas";
import { HUD } from "./HUD";
import { PauseOverlay } from "./PauseOverlay";
import { StartScreen } from "./StartScreen";
import { TouchControls } from "./TouchControls";
import { installControlsTest } from "./controlsTest";
import { getForest, type Forest } from "./forest";
import { bindInput } from "./input";
import { resetSim } from "./sim";
import { useGame } from "./store";

export function ForestApp() {
  const [mounted, setMounted] = useState(false);
  const [forest, setForest] = useState<Forest | null>(null);
  const playing = useGame((s) => s.playing);
  const play = useGame((s) => s.play);
  const setToast = useGame((s) => s.setToast);
  const toast = useGame((s) => s.toast);

  useEffect(() => {
    setMounted(true);
    const unbind = bindInput();
    installControlsTest();
    const id = window.setTimeout(() => {
      const f = getForest();
      resetSim(f);
      setForest(f);
      window.__gameReady = true;
    }, 0);
    return () => {
      window.clearTimeout(id);
      unbind?.();
    };
  }, []);

  useEffect(() => {
    if (!forest) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("qa") === "1") play();
  }, [forest, play]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 2200);
    return () => window.clearTimeout(t);
  }, [toast, setToast]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const st = useGame.getState();
      if (e.code === "Escape") st.pause();
      if (e.code === "KeyL") st.toggleLibrary();
      if (e.code === "KeyG") st.toggleAtlas();
      if (e.code === "KeyQ") st.toggleCircuit();
      if (e.code === "KeyH" && forest) {
        st.selectGrove(null);
        st.requestJump(
          { x: forest.spawn.x, z: forest.spawn.z, yaw: forest.spawn.yaw },
          "Hamlet · the press",
        );
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [forest]);

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-bg text-fg" style={{ touchAction: "none" }}>
      {mounted && forest && playing ? (
        <div className="absolute inset-0">
          <ForestCanvas forest={forest} />
        </div>
      ) : (
        <div className="absolute inset-0 start-wash" />
      )}
      {playing && forest ? (
        <>
          <HUD forest={forest} />
          <TouchControls />
          <PauseOverlay />
        </>
      ) : (
        <StartScreen
          ready={Boolean(forest)}
          growing={!forest}
          onEnter={() => {
            if (forest) {
              resetSim(forest);
              play();
            }
          }}
        />
      )}
    </main>
  );
}
