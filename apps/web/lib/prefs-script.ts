/**
 * Reading preferences applied before the first paint. No React here: the root layout (a server
 * component) inlines `PREFS_SCRIPT`; the hooks live in lib/prefs.ts.
 *
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

