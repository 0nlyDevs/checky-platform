import { dateFormat } from "@/lib/i18n/live";
import { duration } from "@/lib/when";

const timeFmt = dateFormat({ hour: "2-digit", minute: "2-digit" });

export function formatTime(d: Date) {
  return timeFmt.format(d);
}

/** "4 h 35", "12 min", "2 j" (in the current language, see `t.when.duration`) */
export function formatDuration(ms: number) {
  return duration(ms / 60_000);
}

/** Today's working window (06 h to 22 h, stretched when now falls outside), in milliseconds. */
export function dayRange(now: Date) {
  const start = new Date(now);
  start.setHours(Math.min(6, now.getHours()), 0, 0, 0);
  const end = new Date(now);
  end.setHours(Math.max(22, now.getHours() + 1), 0, 0, 0);
  return { start: start.getTime(), end: end.getTime() };
}
