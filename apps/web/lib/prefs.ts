/**
 * Two reading preferences kept on this device: « Mode éco » and the text size.
 *
 * Both live in `localStorage` and in a cookie of the same name (`checky:eco`, `checky:font`), so a
 * server component or the proxy can read them too. The inline script in the root layout
 * (`PREFS_SCRIPT`) applies them to `<html>` before the first paint (`data-eco`, `data-font`), so
 * nothing flashes; the CSS in globals.css does the rest (root font size, system fonts, no motion).
 *
 * Mode éco: `?eco=1` (or the older `?leger=1`) turns it on and remembers it, `?eco=0` off; with no
 * choice stored, the browser's Save-Data signal (`navigator.connection.saveData`, the same wish as
 * the `Save-Data: on` header) turns it on.
 */
import { useSyncExternalStore } from "react";

export const FONT_STEPS = [87.5, 100, 112.5, 125, 137.5] as const;
export const DEFAULT_FONT = 1;
export const ECO_KEY = "checky:eco";
export const FONT_KEY = "checky:font";

export type Prefs = { eco: boolean; ecoAuto: boolean; font: number };

/**
 * What to apply, from what this device remembers and what the URL and the browser say.
 * Self-contained on purpose: `PREFS_SCRIPT` inlines its source into the page's head.
 */
export function resolvePrefs(input: { eco: string | null; font: string | null; search: string; saveData: boolean; steps: number }): {
  eco: boolean;
  ecoAuto: boolean;
  font: number;
  remember: string | null;
} {
  const q = /[?&](eco|leger)=(1|0|true|false|on|off)\b/.exec(input.search);
  let remember: string | null = null;
  let stored = input.eco;
  if (q) {
    remember = /^(1|true|on)$/.test(q[2]) ? "1" : "0";
    stored = remember;
  }
  const eco = stored === "1" ? true : stored === "0" ? false : input.saveData;
  const n = Number.parseInt(input.font ?? "", 10);
  const font = Number.isInteger(n) && n >= 0 && n < input.steps ? n : 1;
  return { eco, ecoAuto: stored !== "1" && stored !== "0" && eco, font, remember };
}

function boot(steps: number, resolve: typeof resolvePrefs) {
  try {
    const cookie = (k: string) => {
      const m = document.cookie.match(new RegExp("(?:^|;\\s*)" + k.replace(":", "\\:") + "=([^;]*)"));
      return m ? decodeURIComponent(m[1]) : null;
    };
    const read = (k: string) => {
      try {
        return localStorage.getItem(k) ?? cookie(k);
      } catch {
        return cookie(k);
      }
    };
    const conn = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    const p = resolve({ eco: read("checky:eco"), font: read("checky:font"), search: location.search, saveData: !!conn?.saveData, steps });
    if (p.remember) {
      try {
        localStorage.setItem("checky:eco", p.remember);
      } catch {}
      document.cookie = "checky:eco=" + p.remember + "; path=/; max-age=31536000; samesite=lax";
    }
    const root = document.documentElement;
    if (p.eco) root.dataset.eco = p.ecoAuto ? "auto" : "1";
    root.dataset.font = String(p.font);
  } catch {}
}

/** Runs in `<head>` before the body paints (see app/layout.tsx). */
export const PREFS_SCRIPT = `(${boot.toString()})(${FONT_STEPS.length}, ${resolvePrefs.toString()})`;

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
