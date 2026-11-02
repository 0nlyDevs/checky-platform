/** Reading preferences for components: Mode éco and the text size (see lib/prefs-script.ts). */
import { useSyncExternalStore } from "react";
import { DEFAULT_FONT, ECO_KEY, FONT_KEY, FONT_STEPS } from "@/lib/prefs-script";

export { DEFAULT_FONT, FONT_STEPS } from "@/lib/prefs-script";

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((f) => f());

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  const onStorage = (e: StorageEvent) => (e.key === ECO_KEY || e.key === FONT_KEY) && onChange();
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function remember(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // the cookie keeps it
  }
  document.cookie = `${key}=${value}; path=/; max-age=31536000; samesite=lax`;
}

/** True while Mode éco is on (works outside React: sockets, polling, image loading). */
export function isEco(): boolean {
  return typeof document !== "undefined" && !!document.documentElement.dataset.eco;
}

/** Reduced motion, asked by the system or forced by Mode éco. */
export function reducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return isEco() || matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function setEco(on: boolean) {
  remember(ECO_KEY, on ? "1" : "0");
  if (on) document.documentElement.dataset.eco = "1";
  else delete document.documentElement.dataset.eco;
  notify();
}

export function fontStep(): number {
  if (typeof document === "undefined") return DEFAULT_FONT;
  const n = Number(document.documentElement.dataset.font);
  return Number.isInteger(n) && n >= 0 && n < FONT_STEPS.length ? n : DEFAULT_FONT;
}

export function setFontStep(step: number) {
  const n = Math.max(0, Math.min(FONT_STEPS.length - 1, Math.round(step)));
  remember(FONT_KEY, String(n));
  document.documentElement.dataset.font = String(n);
  notify();
}

/** Mode éco, for components. The server renders it off; the script has already set the page. */
export function useEco(): boolean {
  return useSyncExternalStore(subscribe, isEco, () => false);
}

export function useFontStep(): number {
  return useSyncExternalStore(subscribe, fontStep, () => DEFAULT_FONT);
}
