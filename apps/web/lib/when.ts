/** Dates the way the desk reads them, in Madagascar time (UTC+3, no daylight saving) like app/core/dates.py. */
const EAT_MS = 3 * 3_600_000;
const DAY_MS = 86_400_000;
const pad = (n: number) => String(n).padStart(2, "0");

/** The parts of an instant on the Madagascar wall clock. */
function eat(ms: number) {
  const d = new Date(ms + EAT_MS);
  return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(), hh: d.getUTCHours(), mm: d.getUTCMinutes(), day: Math.floor((ms + EAT_MS) / DAY_MS) };
}

/** « à l'instant », « il y a 5 min », « il y a 6 h », « hier », « 28/10 », « 14/03/2023 ». */
export function relative(iso: string, now: Date): string {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return "—";
  const diff = now.getTime() - at;
  if (diff < 60_000) return "à l'instant";
  if (diff < 3_600_000) return `il y a ${Math.floor(diff / 60_000)} min`;
  const a = eat(at);
  const n = eat(now.getTime());
  if (a.day === n.day) return `il y a ${Math.floor(diff / 3_600_000)} h`;
  if (a.day === n.day - 1) return "hier";
  return a.y === n.y ? `${pad(a.d)}/${pad(a.m)}` : `${pad(a.d)}/${pad(a.m)}/${a.y}`;
}

/** « 02/11/2026 à 00:41 », for the `title` of every relative date. */
export function exact(iso: string): string {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return "—";
  const a = eat(at);
  return `${pad(a.d)}/${pad(a.m)}/${a.y} à ${pad(a.hh)}:${pad(a.mm)}`;
}

/** French count: 0 and 1 take the singular (« 0 source », « 1 source », « 2 sources »). */
export function plural(n: number, one: string, many: string): string {
  return `${n} ${n < 2 ? one : many}`;
}
