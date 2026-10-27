import { useSyncExternalStore } from "react";

/** Bitta umumiy sekundlik soat: hamma "N soniya oldin" yozuvlari bitta taymerdan yangilanadi. */
let current = Date.now();
let timer: number | null = null;
const listeners = new Set<() => void>();

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  if (timer === null) {
    current = Date.now();
    timer = window.setInterval(() => {
      current = Date.now();
      listeners.forEach((l) => l());
    }, 1000);
  }
  return () => {
    listeners.delete(cb);
    if (listeners.size === 0 && timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  };
}

/** Hozirgi vaqt (epoch ms), har soniyada yangilanadi. */
export function useNow(): number {
  return useSyncExternalStore(subscribe, () => current, () => current);
}
