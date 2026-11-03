import { useEffect, useSyncExternalStore } from "react";
import { DICTS, LANGS, LOCALES, getLang, setCurrentLang, type Lang, type Messages } from "./live";

export * from "./live";

/**
 * The site's language. French is the source of truth (`fr.ts`); `mg.ts` and `en.ts` override the
 * keys they know and French fills the rest. The choice lives in `localStorage` and a cookie under
 * `checky:lang`, so it survives a reload; the server always renders French, and the page switches
 * once it is in the visitor's browser.
 *
 * Two ways to read the strings: the `useT()` hook (re-renders on a switch), and the live `t` from
 * `./live`, which the desk reads like a plain object and `<LangScope>` re-renders.
 */
const KEY = "checky:lang";
const listeners = new Set<() => void>();
const isLang = (v: unknown): v is Lang => typeof v === "string" && (LANGS as readonly string[]).includes(v);

let synced = false;

function read(): Lang {
  try {
    const stored = localStorage.getItem(KEY);
    if (isLang(stored)) return stored;
  } catch {
    // storage blocked: the cookie may still say it
  }
  const cookie = document.cookie.match(/(?:^|;\s*)checky:lang=(fr|mg|en)\b/)?.[1];
  return isLang(cookie) ? cookie : "fr";
}

/**
 * Adopt the stored language, once, after hydration: the server and the first client render both
 * say French, then every subscriber switches together.
 */
function syncLang() {
  if (synced || typeof window === "undefined") return;
  synced = true;
  const stored = read();
  if (stored !== getLang()) {
    setCurrentLang(stored);
    listeners.forEach((f) => f());
  }
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  queueMicrotask(syncLang);
  const onStorage = (e: StorageEvent) => {
    if (e.key !== KEY || !isLang(e.newValue) || e.newValue === getLang()) return;
    setCurrentLang(e.newValue);
    listeners.forEach((f) => f());
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

export function setLang(lang: Lang) {
  synced = true;
  setCurrentLang(lang);
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    // the cookie below keeps the choice
  }
  document.cookie = `${KEY}=${lang}; path=/; max-age=31536000; samesite=lax`;
  listeners.forEach((f) => f());
}

export function useLang(): Lang {
  return useSyncExternalStore(subscribe, getLang, () => "fr");
}

/** The strings in the visitor's language, French where a translation is missing. */
export function useT(): Messages {
  return DICTS[useLang()];
}

/** Keeps `<html lang>` in step with the chosen language (screen readers, hyphenation). */
export function useDocumentLang() {
  const lang = useLang();
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
}

/** A date as people say it in the chosen language: « 2 novembre 2026 », « 2 November 2026 ». */
export function useDay() {
  const lang = useLang();
  return (iso: string) => {
    const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(LOCALES[lang], { day: "numeric", month: "long", year: "numeric" });
  };
}

/** A moment, to the minute: « 2 novembre 2026 à 06:00 », or « 06:00 » when it is today. */
export function useMoment() {
  const lang = useLang();
  return (iso: string) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const time = d.toLocaleTimeString(LOCALES[lang], { hour: "2-digit", minute: "2-digit" });
    if (d.toDateString() === new Date().toDateString()) return time;
    return `${d.toLocaleDateString(LOCALES[lang], { day: "numeric", month: "long" })} ${DICTS[lang].publicLayer.lang.at} ${time}`;
  };
}

