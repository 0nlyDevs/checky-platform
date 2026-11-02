const timeFmt = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });

export function formatTime(d: Date) {
  return timeFmt.format(d);
}

/** "4 h 35", "12 min", "2 j" */
export function formatDuration(ms: number) {
  const min = Math.max(0, Math.round(ms / 60_000));
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  if (h >= 48) return `${Math.floor(h / 24)} j`;
  const rest = min % 60;
  return rest ? `${h} h ${String(rest).padStart(2, "0")}` : `${h} h`;
}

/** Today's working window (06 h to 22 h, stretched when now falls outside), in milliseconds. */
export function dayRange(now: Date) {
  const start = new Date(now);
  start.setHours(Math.min(6, now.getHours()), 0, 0, 0);
  const end = new Date(now);
  end.setHours(Math.max(22, now.getHours() + 1), 0, 0, 0);
  return { start: start.getTime(), end: end.getTime() };
}
