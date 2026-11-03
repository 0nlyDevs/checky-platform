/** Dates the way the desk reads them, in Madagascar time (UTC+3, no daylight saving) like app/core/dates.py. */
const EAT_MS = 3 * 3_600_000;
const DAY_MS = 86_400_000;
const pad = (n: number) => String(n).padStart(2, "0");

/** The parts of an instant on the Madagascar wall clock. */
function eat(ms: number) {
  const d = new Date(ms + EAT_MS);
  return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(), hh: d.getUTCHours(), mm: d.getUTCMinutes(), day: Math.floor((ms + EAT_MS) / DAY_MS) };
}

/**
 * The words of relative dates and durations, in French; `fr.ts` exposes them as `t.when`, `mg.ts`
 * and `en.ts` override them, and the live dictionary (`lib/i18n/live.ts`) swaps them in here when
 * the language changes. This file stays free of imports so `node --test` can run it.
 */
export const whenFr = {
  justNow: "à l'instant",
  minutesAgo: (n: number) => `il y a ${n} min`,
  hoursAgo: (n: number) => `il y a ${n} h`,
  yesterday: "hier",
  at: "à",
  /** « 12 min », « 4 h 35 », « 2 j » */
  duration: (min: number) => {
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60);
    if (h >= 48) return `${Math.floor(h / 24)} j`;
    const rest = min % 60;
    return rest ? `${h} h ${String(rest).padStart(2, "0")}` : `${h} h`;
  },
};
export type WhenWords = { [K in keyof typeof whenFr]: (typeof whenFr)[K] extends (...a: infer A) => string ? (...a: A) => string : string };

let words: WhenWords = whenFr;

/** Called by the live dictionary when the language changes. */
export function setWhenWords(next: WhenWords) {
  words = next;
}

/** « à l'instant », « il y a 5 min », « il y a 6 h », « hier », « 28/10 », « 14/03/2023 ». */
export function relative(iso: string, now: Date): string {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return "—";
  const diff = now.getTime() - at;
  if (diff < 60_000) return words.justNow;
  if (diff < 3_600_000) return words.minutesAgo(Math.floor(diff / 60_000));
  const a = eat(at);
  const n = eat(now.getTime());
  if (a.day === n.day) return words.hoursAgo(Math.floor(diff / 3_600_000));
  if (a.day === n.day - 1) return words.yesterday;
  return a.y === n.y ? `${pad(a.d)}/${pad(a.m)}` : `${pad(a.d)}/${pad(a.m)}/${a.y}`;
}

/** « 02/11/2026 à 00:41 », for the `title` of every relative date. */
export function exact(iso: string): string {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return "—";
  const a = eat(at);
  return `${pad(a.d)}/${pad(a.m)}/${a.y} ${words.at} ${pad(a.hh)}:${pad(a.mm)}`;
}

/** French count: 0 and 1 take the singular (« 0 source », « 1 source », « 2 sources »). */
export function plural(n: number, one: string, many: string): string {
  return `${n} ${n < 2 ? one : many}`;
}

/** A duration in minutes the way the desk says it: « 12 min », « 4 h 35 », « 2 j ». */
export function duration(min: number): string {
  return words.duration(Math.max(0, Math.round(min)));
}
