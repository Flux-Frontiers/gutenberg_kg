const GAME_KEYS = new Set([
  "KeyW",
  "KeyA",
  "KeyS",
  "KeyD",
  "ArrowUp",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "Space",
  "ShiftLeft",
  "ShiftRight",
]);

export type Actions = {
  throttle: number;
  steer: number;
  boost: boolean;
  interact: boolean;
  interactDown: boolean;
};

const keys = new Set<string>();
let injectedKeys: string[] | null = null;
let injectedSteer: number | null = null;
let touchThrottle = 0;
let touchSteer = 0;
let prevInteract = false;

function onKeyDown(e: KeyboardEvent) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const target = e.target as HTMLElement | null;
  if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
  keys.add(e.code);
  if (GAME_KEYS.has(e.code) || e.code === "KeyE") e.preventDefault();
}

function onKeyUp(e: KeyboardEvent) {
  keys.delete(e.code);
}

function onBlur() {
  keys.clear();
}

let bound = false;

export function bindInput() {
  if (bound || typeof window === "undefined") return () => undefined;
  bound = true;
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  window.addEventListener("blur", onBlur);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) keys.clear();
  });
  return () => {
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("keyup", onKeyUp);
    window.removeEventListener("blur", onBlur);
    bound = false;
    keys.clear();
  };
}

export function setInjectedKeys(codes: string[] | null) {
  injectedKeys = codes;
}

export function setInjectedSteer(v: number | null) {
  injectedSteer = v;
}

export function setTouchAxes(throttle: number, steer: number) {
  touchThrottle = throttle;
  touchSteer = steer;
}

function held(code: string): boolean {
  if (injectedKeys) return injectedKeys.includes(code);
  return keys.has(code);
}

function radialDeadzone(x: number, y: number, dz = 0.15): { x: number; y: number } {
  const m = Math.hypot(x, y);
  if (m < dz) return { x: 0, y: 0 };
  const scale = (m - dz) / (1 - dz) / m;
  return { x: x * scale, y: y * scale };
}

function pollGamepad(actions: Actions) {
  if (typeof navigator === "undefined" || !navigator.getGamepads) return;
  const pads = navigator.getGamepads();
  for (const pad of pads) {
    if (!pad) continue;
    const stick = radialDeadzone(pad.axes[0] ?? 0, pad.axes[1] ?? 0);
    // Left stick Y: -1 is up → throttle +. Steer: stick left (−x) is A / +steer.
    if (Math.abs(stick.y) > 0.02) actions.throttle += -stick.y;
    if (Math.abs(stick.x) > 0.02) actions.steer += -stick.x;
    if (pad.buttons[12]?.pressed) actions.throttle += 1;
    if (pad.buttons[13]?.pressed) actions.throttle -= 1;
    if (pad.buttons[14]?.pressed) actions.steer += 1;
    if (pad.buttons[15]?.pressed) actions.steer -= 1;
    if (pad.buttons[0]?.pressed) actions.interactDown = true;
    if (pad.buttons[7] && pad.buttons[7].value > 0.4) actions.boost = true;
  }
}

export function sampleActions(): Actions {
  const actions: Actions = {
    throttle: 0,
    steer: 0,
    boost: false,
    interact: false,
    interactDown: false,
  };

  if (held("KeyW") || held("ArrowUp")) actions.throttle += 1;
  if (held("KeyS") || held("ArrowDown")) actions.throttle -= 1;
  if (held("KeyA") || held("ArrowLeft")) actions.steer += 1;
  if (held("KeyD") || held("ArrowRight")) actions.steer -= 1;
  if (held("ShiftLeft") || held("ShiftRight")) actions.boost = true;
  if (held("KeyE") || held("Space")) actions.interactDown = true;

  actions.throttle += touchThrottle;
  actions.steer += touchSteer;

  pollGamepad(actions);

  if (injectedSteer !== null) actions.steer = injectedSteer;

  actions.throttle = Math.max(-1, Math.min(1, actions.throttle));
  actions.steer = Math.max(-1, Math.min(1, actions.steer));
  actions.interact = actions.interactDown && !prevInteract;
  prevInteract = actions.interactDown;
  return actions;
}
