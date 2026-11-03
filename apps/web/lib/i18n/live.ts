import { en } from "./en";
import { fr } from "./fr";
import { mg } from "./mg";
import { setWhenWords } from "@/lib/when";

/**
 * The dictionaries and the live `t`, with no React in them, so any module can read the strings (a
 * server component gets French). The language store and the hooks are in `./index`.
 *
 * `t` reads the current language on every access: the desk imports it like a plain object
 * (`t.claims.title`, `const r = t.registre`), and `<LangScope>` remounts the desk when the
 * language changes, so every reader renders again in the new one.
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

export const DICTS: Record<Lang, Messages> = { fr, mg: merge<Messages>(fr, mg), en: merge<Messages>(fr, en) };

/** The language the live `t` answers in: French until the browser says otherwise (`./index`). */
let current: Lang = "fr";

/** The current language, outside React (formatters, plain helpers). */
export const getLang = (): Lang => current;

/** Set by the language store in `./index` only. */
export function setCurrentLang(lang: Lang) {
  current = lang;
  setWhenWords(DICTS[lang].when);
}

/** The locale for `Intl` and `toLocale*` in the current language. */
export const locale = (): string => LOCALES[current];

/** The dictionary of a language (French filling the gaps). */
export const messages = (lang: Lang): Messages => DICTS[lang];

const isDict = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/** The value at `path` in the current dictionary. */
function at(path: readonly string[]): unknown {
  let v: unknown = DICTS[current];
  for (const key of path) v = isDict(v) ? v[key] : undefined;
  return v;
}

const proxies = new Map<string, unknown>();
const fns = new Map<string, unknown>();

/**
 * A view of the dictionary at `path` that reads the current language on every access: nested
 * sections are live views too, and functions resolve in the language of the moment they are called,
 * so `const r = t.registre` or `const plural = t.claims.count` at module level stay in step.
 */
function live(path: readonly string[]): unknown {
  const id = path.join("/");
  let view = proxies.get(id);
  if (view) return view;
  const get = (key: string) => {
    const value = (at(path) as Record<string, unknown> | undefined)?.[key];
    if (isDict(value)) return live([...path, key]);
    if (typeof value !== "function") return value;
    const fid = `${id}/${key}`;
    let f = fns.get(fid);
    if (!f) {
      f = (...args: unknown[]) => (at([...path, key]) as (...a: unknown[]) => unknown)(...args);
      fns.set(fid, f);
    }
    return f;
  };
  view = new Proxy(
    {},
    {
      get: (_, key) => (typeof key === "string" ? get(key) : undefined),
      has: (_, key) => isDict(at(path)) && key in (at(path) as object),
      ownKeys: () => (isDict(at(path)) ? Reflect.ownKeys(at(path) as object) : []),
      getOwnPropertyDescriptor: (_, key) =>
        typeof key === "string" && isDict(at(path)) && key in (at(path) as object)
          ? { configurable: true, enumerable: true, writable: false, value: get(key) }
          : undefined,
    },
  );
  proxies.set(id, view);
  return view;
}

/** The strings in the current language, as a plain-looking object (see the note at the top). */
export const t = live([]) as Messages;

/**
 * An `Intl.DateTimeFormat` that follows the language: build it once at module level like before,
 * it picks the current locale at each call.
 */
export function dateFormat(options: Intl.DateTimeFormatOptions) {
  const made = new Map<Lang, Intl.DateTimeFormat>();
  const get = () => {
    let f = made.get(current);
    if (!f) {
      f = new Intl.DateTimeFormat(LOCALES[current], options);
      made.set(current, f);
    }
    return f;
  };
  return {
    format: (date?: Date | number) => get().format(date),
    formatToParts: (date?: Date | number) => get().formatToParts(date),
  };
}
