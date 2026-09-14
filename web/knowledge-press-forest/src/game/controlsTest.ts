import { setInjectedKeys, setInjectedSteer } from "./input";
import { sim } from "./sim";

export type ControlsProbe = {
  getYaw: () => number;
  getSpeed: () => number;
  setSteer?: (v: number) => void;
  setKeys?: (codes: string[]) => void;
};

declare global {
  interface Window {
    __controlsTest?: ControlsProbe;
    __gameReady?: boolean;
  }
}

export function installControlsTest() {
  if (typeof window === "undefined") return;
  window.__controlsTest = {
    getYaw: () => sim.yaw,
    getSpeed: () => sim.speed,
    setSteer: (v) => setInjectedSteer(v),
    setKeys: (codes) => {
      setInjectedSteer(null);
      setInjectedKeys(codes);
    },
  };
}
