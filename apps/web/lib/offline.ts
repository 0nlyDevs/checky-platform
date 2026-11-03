"use client";

/**
 * Offline, for components: whether the network is there, and how old the data on screen is.
 *
 * The service worker (public/sw.js) answers the API from its cache when the network fails and
 * marks those answers with `X-Checky-Cached-At` (when they were saved). `api()` and `publicApi()`
 * report each answer here, so the banner can say « Hors connexion · données du … ».
 */
import { useSyncExternalStore } from "react";

export const CACHED_AT_HEADER = "x-checky-cached-at";
// Answered by the service worker when it has nothing saved for a request and the network failed.
export const NOTHING_CACHED_HEADER = "x-checky-offline";

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((f) => f());

export function isOffline(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

function subscribeOnline(onChange: () => void) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

/** True while the browser has a network; the server renders online. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribeOnline,
    () => !isOffline(),
    () => true,
  );
}

// path → when the answer shown for it was saved (absent: fresh from the network).
const served = new Map<string, string>();
let missing = 0;
let oldest: string | null = null;

function recompute() {
  let min: string | null = null;
  for (const at of served.values()) if (!min || at < min) min = at;
  if (min !== oldest) {
    oldest = min;
    notify();
  }
}

/** Called for every API answer: from the cache (with its date), fresh, or nothing at all. */
export function noteAnswer(path: string, res: Response) {
  const at = res.headers.get(CACHED_AT_HEADER);
  if (res.headers.get(NOTHING_CACHED_HEADER)) {
    missing += 1;
    notify();
  } else if (at) served.set(path, at);
  else served.delete(path);
  recompute();
}

if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    served.clear();
    missing = 0;
    oldest = null;
    notify();
  });
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

/** The date of the oldest saved answer shown since the network went away (null: none). */
export function useCachedSince(): string | null {
  return useSyncExternalStore(
    subscribe,
    () => oldest,
    () => null,
  );
}

/** How many requests found nothing saved on this device. */
export function useMissing(): number {
  return useSyncExternalStore(
    subscribe,
    () => missing,
    () => 0,
  );
}
