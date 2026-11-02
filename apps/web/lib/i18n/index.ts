"use client";

import { useEffect, useSyncExternalStore } from "react";
import { en } from "./en";
import { fr } from "./fr";
import { mg } from "./mg";

/**
 * The site's language. French is the source of truth (`fr.ts`); `mg.ts` and `en.ts` override the
 * keys they know and French fills the rest. The choice lives in `localStorage` and a cookie under
 * `checky:lang`, so it survives a reload; the server always renders French, and the page switches
 * once it is in the visitor's browser.
 */
export type Lang = "fr" | "mg" | "en";
export const LANGS: readonly Lang[] = ["fr", "mg", "en"];
export const LOCALES: Record<Lang, string> = { fr: "fr-FR", mg: "mg-MG", en: "en-GB" };

/** The French dictionary with every literal widened to `string`, so a translation can replace it. */
type Widen<T> = T extends (...args: infer A) => unknown
  ? (...args: A) => string
  : T extends string
    ? string
    : T extends readonly (infer U)[]
      ? readonly Widen<U>[]
      : T extends object
        ? { [K in keyof T]: Widen<T[K]> }
        : T;
export type Messages = Widen<typeof fr>;
type DeepPartial<T> = T extends (...args: never[]) => unknown
  ? T
  : T extends readonly unknown[]
    ? T
    : T extends object
      ? { [K in keyof T]?: DeepPartial<T[K]> }
      : T;
/** What a translation file may hold: any subset of the French keys. */
export type Overrides = DeepPartial<Messages>;

const plain = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

function merge<T>(base: T, over: unknown): T {
  if (!plain(base) || !plain(over)) return (over ?? base) as T;
  const out: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(over)) {
    if (value === undefined) continue;
    out[key] = plain(base[key]) && plain(value) ? merge(base[key], value) : value;
  }
  return out as T;
}

const DICTS: Record<Lang, Messages> = { fr, mg: merge<Messages>(fr, mg), en: merge<Messages>(fr, en) };

const KEY = "checky:lang";
const listeners = new Set<() => void>();
const isLang = (v: unknown): v is Lang => typeof v === "string" && (LANGS as readonly string[]).includes(v);

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

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  const onStorage = (e: StorageEvent) => e.key === KEY && onChange();
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

export function setLang(lang: Lang) {
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    // the cookie below keeps the choice
  }
  document.cookie = `${KEY}=${lang}; path=/; max-age=31536000; samesite=lax`;
  listeners.forEach((f) => f());
}

export function useLang(): Lang {
  return useSyncExternalStore(subscribe, read, () => "fr");
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
