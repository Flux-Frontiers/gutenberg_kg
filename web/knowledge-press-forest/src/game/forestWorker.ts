/// <reference lib="webworker" />
// Grows the forest off the main thread. Space colonization over ~400k chunk
// points takes a couple of seconds; here it never freezes the page. The
// worker keeps growTree's skeleton cache between requests, so a leaf-level
// change only re-places leaves.
import { getForest } from "./forest";

self.onmessage = (e: MessageEvent<{ id: number; leafScale: number }>) => {
  const forest = getForest(e.data.leafScale);
  (self as unknown as DedicatedWorkerGlobalScope).postMessage({ id: e.data.id, forest });
};
